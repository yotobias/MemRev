"""The Docker check runner against a stand-in for the `docker` command-line tool.

The stand-in sits at the system boundary (the process call): it answers `docker info`, `image
inspect`, `pull`, `run`, `exec` and `rm` like Docker would, and records what it was asked. `git`
calls go to the real git, so T's source really comes out of a host clone with `git archive`.
The real image is exercised by the slow seam-N2 test in test_docker_n2.py.
"""

import io
import json
import subprocess
import tarfile
from pathlib import Path

import pytest

from memrev.check_runner import Check, Environment, EnvironmentUnavailable, Outcome, make_runner
from memrev.docker_runner import DockerCheckRunner, DockerSettings

from conftest import TinyRepo

IMAGE = "swebench/sweb.eval.x86_64.tiny_1776_tiny-1:latest"
CHECK = Check("python -c 'import module; assert module.VALUE == 2'", "module.VALUE")
OK_OUTPUT = "checked\n"


class FakeDocker:
    """Answers docker commands; delegates git to the real git."""

    def __init__(self):
        self.calls: list[list[str]] = []
        self.daemon_up = True
        self.local_images: set[str] = set()
        self.pullable: set[str] = {IMAGE}
        self.install_fails = False
        self.check_result: tuple[int, str] = (0, OK_OUTPUT)
        self.check_raises: Exception | None = None
        self.daemon_error_on_check = False
        self.loaded: dict[str, dict[str, str]] = {}  # container -> {path: content} from the tar on stdin
        self.running: list[str] = []
        self.started = 0

    def __call__(self, argv, input=None, timeout=None):
        argv = list(argv)
        if argv[0] == "git":
            return subprocess.run(argv, input=input, capture_output=True, timeout=timeout)
        self.calls.append(argv)
        if not self.daemon_up:
            return self._done(argv, 1, b"", b"Cannot connect to the Docker daemon at unix:///var/run/docker.sock.")
        verb = argv[1]
        if verb == "info":
            return self._done(argv, 0, b"28.5.0\n")
        if verb == "image" and argv[2] == "inspect":
            found = argv[-1] in self.local_images
            return self._done(argv, 0 if found else 1, b"[]" if found else b"", b"" if found else b"No such image")
        if verb == "pull":
            if argv[-1] in self.pullable:
                self.local_images.add(argv[-1])
                return self._done(argv, 0, b"pulled\n")
            return self._done(argv, 1, b"", b"Error response from daemon: pull access denied")
        if verb == "run":
            self.started += 1
            container = f"c{self.started}"
            self.running.append(container)
            return self._done(argv, 0, f"{container}\n".encode())
        if verb == "rm":
            for container in argv[3:]:
                if container in self.running:
                    self.running.remove(container)
            return self._done(argv, 0)
        if verb == "exec":
            return self._exec(argv, input)
        raise AssertionError(f"unexpected docker call {argv}")

    def _exec(self, argv, input):
        container, script = next(a for a in argv if a in self.running), argv[-1]
        if input is not None:  # loading a revision's source
            with tarfile.open(fileobj=io.BytesIO(input)) as tar:
                self.loaded[container] = {
                    m.name: tar.extractfile(m).read().decode() for m in tar.getmembers() if m.isfile()
                }
            if self.install_fails:
                return self._done(argv, 1, b"ERROR: pip install failed\n")
            return self._done(argv, 0, b"installed\n")
        if "git reset --hard" in script:
            return self._done(argv, 0)
        if self.check_raises is not None:
            raise self.check_raises
        if self.daemon_error_on_check:
            return self._done(argv, 1, b"", b"Error response from daemon: container c1 is not running")
        status, output = self.check_result
        return self._done(argv, status, output.encode())

    @staticmethod
    def _done(argv, status, stdout=b"", stderr=b""):
        return subprocess.CompletedProcess(argv, status, stdout, stderr)

    def verbs(self, verb: str) -> list[list[str]]:
        return [c for c in self.calls if c[1] == verb]

    def check_execs(self) -> list[list[str]]:
        return [c for c in self.verbs("exec") if "-i" not in c and "git reset --hard" not in c[-1]]


@pytest.fixture
def docker() -> FakeDocker:
    return FakeDocker()


@pytest.fixture
def meta(tmp_path: Path) -> Path:
    path = tmp_path / "meta.jsonl"
    path.write_text(json.dumps({"instance_id": "tiny__tiny-1", "repo": "tiny/tiny", "image": IMAGE}) + "\n")
    return path


def environment(repo: TinyRepo, instance_id: str = "tiny__tiny-1") -> Environment:
    return Environment("tiny/tiny", "1.0", instance_id, repo.path)


def runner(docker, meta, **settings) -> DockerCheckRunner:
    return DockerCheckRunner(DockerSettings(meta=meta, **settings), process=docker)


# Environment unavailable ------------------------------------------------


def test_a_missing_docker_binary_makes_the_environment_unavailable(tiny_repo, meta, tmp_path):
    real = DockerCheckRunner(DockerSettings(docker=str(tmp_path / "no-such-docker"), meta=meta))

    with pytest.raises(EnvironmentUnavailable, match="docker"):
        real.run(CHECK, tiny_repo.commits[2], environment(tiny_repo), 1)


def test_a_stopped_docker_daemon_makes_the_environment_unavailable(docker, tiny_repo, meta):
    docker.daemon_up = False

    with pytest.raises(EnvironmentUnavailable, match="Cannot connect to the Docker daemon"):
        runner(docker, meta).run(CHECK, tiny_repo.commits[2], environment(tiny_repo), 1)


def test_an_instance_without_an_image_in_the_metadata_makes_the_environment_unavailable(docker, tiny_repo, meta):
    with pytest.raises(EnvironmentUnavailable, match="tiny__tiny-9"):
        runner(docker, meta).run(CHECK, tiny_repo.commits[2], environment(tiny_repo, "tiny__tiny-9"), 1)


def test_an_image_that_cannot_be_pulled_makes_the_environment_unavailable(docker, tiny_repo, meta):
    docker.pullable = set()

    with pytest.raises(EnvironmentUnavailable, match="pull access denied"):
        runner(docker, meta).run(CHECK, tiny_repo.commits[2], environment(tiny_repo), 1)

    assert docker.verbs("pull") == [["docker", "pull", "--platform", "linux/amd64", IMAGE]]
    assert docker.verbs("run") == []


def test_a_revision_missing_from_the_host_clone_makes_the_environment_unavailable(docker, tiny_repo, meta):
    with pytest.raises(EnvironmentUnavailable, match="dead" * 10):
        runner(docker, meta).run(CHECK, "dead" * 10, environment(tiny_repo), 1)

    assert docker.verbs("run") == []


def test_a_revision_that_does_not_install_makes_the_environment_unavailable_without_retrying(
    docker, tiny_repo, meta
):
    docker.install_fails = True
    real = runner(docker, meta)

    for index in (1, 2):
        with pytest.raises(EnvironmentUnavailable, match="pip install failed"):
            real.run(CHECK, tiny_repo.commits[2], environment(tiny_repo), index)

    assert len(docker.verbs("run")) == 1
    assert docker.running == []  # the broken container is removed at once


# Running a check ----------------------------------------------------------


def test_a_check_runs_in_the_pairs_image_on_the_requested_revisions_source(docker, tiny_repo, meta):
    result = runner(docker, meta).run(CHECK, tiny_repo.commits[1], environment(tiny_repo), 1)

    assert result.outcome is Outcome.PASS
    assert (result.exit_status, result.output) == (0, OK_OUTPUT)
    assert docker.verbs("pull") == [["docker", "pull", "--platform", "linux/amd64", IMAGE]]
    (run,) = docker.verbs("run")
    assert run[:3] == ["docker", "run", "-d"] and "--platform" in run and run[run.index("--platform") + 1] == "linux/amd64"
    assert IMAGE in run
    assert docker.loaded["c1"] == {"module.py": "VALUE = 1\n"}  # T's source, from git archive on the host
    (check_exec,) = docker.check_execs()
    assert "/testbed" in check_exec and "conda activate testbed" in check_exec[-1]


def test_an_image_already_on_the_machine_is_not_pulled(docker, tiny_repo, meta):
    docker.local_images.add(IMAGE)

    runner(docker, meta).run(CHECK, tiny_repo.commits[1], environment(tiny_repo), 1)

    assert docker.verbs("pull") == []


def test_a_failing_check_is_classified_from_its_output(docker, tiny_repo, meta):
    docker.check_result = (1, 'Traceback (most recent call last):\n  File "<string>", line 1\nAssertionError\n')

    result = runner(docker, meta).run(CHECK, tiny_repo.commits[2], environment(tiny_repo), 1)

    assert result.outcome is Outcome.FAIL_ON_TARGET
    assert result.exit_status == 1
    assert "AssertionError" in result.detail


def test_runs_at_one_revision_reuse_one_container_and_reset_it_before_each_run(docker, tiny_repo, meta):
    real = runner(docker, meta)

    for index in (1, 2, 3):
        real.run(CHECK, tiny_repo.commits[2], environment(tiny_repo), index)

    assert len(docker.verbs("run")) == 1
    assert len(docker.loaded) == 1
    resets = [c for c in docker.verbs("exec") if "git reset --hard" in c[-1]]
    assert len(resets) >= 3


def test_each_revision_gets_its_own_container_and_close_removes_them_all(docker, tiny_repo, meta):
    real = runner(docker, meta)

    real.run(CHECK, tiny_repo.commits[0], environment(tiny_repo), 1)
    real.run(CHECK, tiny_repo.commits[2], environment(tiny_repo), 1)
    real.run(CHECK, tiny_repo.commits[0], environment(tiny_repo), 2)

    assert docker.loaded == {"c1": {"module.py": "VALUE = 0\n"}, "c2": {"module.py": "VALUE = 2\n"}}
    assert docker.running == ["c1", "c2"]
    real.close()
    assert docker.running == []


def test_the_least_recently_used_container_is_removed_beyond_the_container_limit(docker, tiny_repo, meta):
    real = runner(docker, meta, containers=2)

    for commit in tiny_repo.commits:
        real.run(CHECK, commit, environment(tiny_repo), 1)

    assert docker.running == ["c2", "c3"]


def test_a_check_that_hangs_is_a_harness_error_and_its_container_is_replaced(docker, tiny_repo, meta):
    docker.check_raises = subprocess.TimeoutExpired("docker", 60)
    real = runner(docker, meta, timeout=1)

    result = real.run(CHECK, tiny_repo.commits[2], environment(tiny_repo), 1)

    assert result.outcome is Outcome.HARNESS_ERROR
    assert result.exit_status is None
    assert "timed out" in result.detail
    assert docker.running == []
    docker.check_raises = None
    assert real.run(CHECK, tiny_repo.commits[2], environment(tiny_repo), 2).outcome is Outcome.PASS
    assert len(docker.verbs("run")) == 2


def test_a_container_that_died_is_a_harness_error(docker, tiny_repo, meta):
    docker.daemon_error_on_check = True

    result = runner(docker, meta).run(CHECK, tiny_repo.commits[2], environment(tiny_repo), 1)

    assert result.outcome is Outcome.HARNESS_ERROR
    assert "is not running" in result.detail


# Registration -----------------------------------------------------------


def test_the_docker_runner_is_registered_and_takes_settings_after_the_equals_sign(meta, tmp_path):
    from memrev import cli  # noqa: F401  (the command-line tool registers the docker runner)

    real = make_runner(None, f"docker=docker=/opt/docker,meta={meta},timeout=60,containers=2")

    assert isinstance(real, DockerCheckRunner)
    assert real.settings == DockerSettings(docker="/opt/docker", meta=meta, timeout=60, containers=2)


def test_drift_with_docker_unavailable_drops_the_pair_as_environment_unavailable(cli, run_dir, tmp_path):
    from test_checks import Pipeline

    pipeline = Pipeline(cli, run_dir, tmp_path)

    result = pipeline.memrev(
        "drift", "--runner", f"docker=docker={tmp_path / 'no-such-docker'}", "--sanity", str(pipeline.sanity)
    )

    assert result.exit_code == 0, result.err
    assert "2 dropped" in result.out
    reason, detail = pipeline.exclusions("drift")[f"pair {pipeline.pair1}"]
    assert reason == "environment unavailable"
    assert "docker" in detail
