"""The real check runner: runs a check inside the pair's SWE-bench Docker image (V14, ADR 0001).

Per (image, revision) it keeps one disposable container:
1. `docker info`, then the image named in the metadata's `image` column for the environment's
   instance (always S's), pulled with `--platform linux/amd64` if it is not on the machine.
2. `docker run -d ... sleep infinity`.
3. The revision's source comes from the host clone (`git archive <revision>`), because the image
   prunes every commit after its base_commit. It replaces /testbed's files, is committed inside the
   container (so each run can reset to it), and is installed into the `testbed` conda env.
4. Each run resets /testbed (`git reset --hard && git clean -fdq`), runs the check command under
   `timeout`, and classifies its output (`memrev.outcomes`).
Anything that stops steps 1-3 raises EnvironmentUnavailable. A failed setup is remembered, so the
next run at that revision fails at once. `close()` removes every container.

Settings come after `=` in `--runner docker=KEY=VALUE,...`: `docker` (binary), `meta` (metadata
JSONL), `timeout` (seconds per check run, default 900), `containers` (kept alive at once, default 4).
"""

from __future__ import annotations

import json
import shlex
import subprocess
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from memrev.check_runner import (
    Check,
    Environment,
    EnvironmentUnavailable,
    Outcome,
    RunResult,
    register_runner,
)
from memrev.outcomes import classify
from memrev.store import RunError, RunStore
from memrev.swe_bench import DEFAULT_META

PLATFORM = "linux/amd64"  # SWE-bench images are amd64 only
TESTBED = "/testbed"
ACTIVATE = "source /opt/miniconda3/bin/activate && conda activate testbed"
# How each repository's source is installed into the image's env (SWE-bench's install commands).
INSTALL = {"django/django": "python -m pip install -e ."}
DEFAULT_INSTALL = "python -m pip install -e ."
SHORT_TIMEOUT = 120  # docker info / image inspect / run / reset
SETUP_TIMEOUT = 3600  # pulling an image (~1.15 GB) or installing a revision under emulation
KILL_GRACE = 10

Process = Callable[..., subprocess.CompletedProcess]


def run_process(argv: list[str], input: bytes | None = None, timeout: float | None = None):
    """The system boundary: run a process, capturing bytes. Tests replace it."""
    return subprocess.run(argv, input=input, capture_output=True, timeout=timeout)


@dataclass(frozen=True)
class DockerSettings:
    docker: str = "docker"
    meta: Path = DEFAULT_META
    timeout: int = 900
    containers: int = 4


def _text(data: bytes | str | None) -> str:
    if data is None:
        return ""
    return data.decode(errors="replace") if isinstance(data, bytes) else data


def _tail(text: str, limit: int = 300) -> str:
    text = text.strip()
    return text if len(text) <= limit else "..." + text[-limit:]


@dataclass
class DockerCheckRunner:
    settings: DockerSettings = field(default_factory=DockerSettings)
    process: Process = run_process
    _docker_ok: bool = field(default=False, init=False, repr=False)
    _images: dict[str, str] | None = field(default=None, init=False, repr=False)
    _pulled: set[str] = field(default_factory=set, init=False, repr=False)
    _containers: OrderedDict = field(default_factory=OrderedDict, init=False, repr=False)  # (image, rev) -> id
    _failed: dict[tuple[str, str], str] = field(default_factory=dict, init=False, repr=False)

    # CheckRunner -----------------------------------------------------------

    def run(self, check: Check, revision: str, environment: Environment, run_index: int) -> RunResult:
        self._check_docker()
        image = self._image_for(environment.instance_id)
        key = (image, revision)
        container = self._container(key, environment)
        try:
            reset = self._exec(container, f"cd {TESTBED} && git reset --hard -q && git clean -fdq", SHORT_TIMEOUT)
            if reset.returncode != 0:
                return self._broken(key, f"reset failed: {_tail(_text(reset.stdout) + _text(reset.stderr))}", reset)
            script = (
                f"{{ {ACTIVATE} && cd {TESTBED} && "
                f"timeout -k {KILL_GRACE} {self.settings.timeout} bash -c {shlex.quote(check.command)}; }} 2>&1"
            )
            result = self._exec(container, script, self.settings.timeout + 2 * KILL_GRACE + SHORT_TIMEOUT)
        except subprocess.TimeoutExpired:
            self._remove(key)
            return RunResult(Outcome.HARNESS_ERROR, None, "", f"timed out after {self.settings.timeout}s")
        output, docker_error = _text(result.stdout), _text(result.stderr)
        if docker_error.startswith(("Error", "Cannot connect")):  # the docker CLI, not the check
            return self._broken(key, docker_error.strip(), result)
        outcome, detail = classify(check.command, check.asserted_target, result.returncode, output)
        return RunResult(outcome, result.returncode, output, detail)

    def close(self) -> None:
        for key in list(self._containers):
            self._remove(key)

    # Containers ------------------------------------------------------------

    def _container(self, key: tuple[str, str], environment: Environment) -> str:
        if key in self._failed:
            raise EnvironmentUnavailable(self._failed[key])
        if key in self._containers:
            self._containers.move_to_end(key)
            return self._containers[key]
        image, revision = key
        self._ensure_image(image)
        try:
            source = self._archive(environment.repository_path, revision)
            container = self._start(image)
        except EnvironmentUnavailable as exc:
            self._failed[key] = str(exc)
            raise
        self._containers[key] = container
        try:
            self._load(container, revision, source, INSTALL.get(environment.repository, DEFAULT_INSTALL))
        except EnvironmentUnavailable as exc:
            self._remove(key)
            self._failed[key] = str(exc)
            raise
        while len(self._containers) > max(1, self.settings.containers):
            self._remove(next(iter(self._containers)))
        return container

    def _broken(self, key, detail: str, result) -> RunResult:
        self._remove(key)
        return RunResult(Outcome.HARNESS_ERROR, result.returncode, _text(result.stdout) + _text(result.stderr), detail)

    def _remove(self, key) -> None:
        container = self._containers.pop(key, None)
        if container is not None:
            try:
                self.process([self.settings.docker, "rm", "-f", container], timeout=SHORT_TIMEOUT)
            except (OSError, subprocess.TimeoutExpired):
                pass

    # Steps -----------------------------------------------------------------

    def _docker(self, *args: str, input: bytes | None = None, timeout: float = SHORT_TIMEOUT, what: str):
        """Run a docker command during setup; any failure is EnvironmentUnavailable."""
        argv = [self.settings.docker, *args]
        try:
            result = self.process(argv, input=input, timeout=timeout)
        except FileNotFoundError:
            raise EnvironmentUnavailable(f"docker is not installed ({self.settings.docker} not found)") from None
        except OSError as exc:
            raise EnvironmentUnavailable(f"{what}: {exc}") from None
        except subprocess.TimeoutExpired:
            raise EnvironmentUnavailable(f"{what}: timed out after {timeout}s") from None
        return result

    def _check_docker(self) -> None:
        if self._docker_ok:
            return
        result = self._docker("info", "--format", "{{.ServerVersion}}", what="docker info")
        if result.returncode != 0:
            raise EnvironmentUnavailable(f"docker is not available: {_tail(_text(result.stderr) or _text(result.stdout))}")
        self._docker_ok = True

    def _image_for(self, instance_id: str) -> str:
        if self._images is None:
            try:
                rows = [json.loads(line) for line in self.settings.meta.read_text().splitlines() if line.strip()]
            except (OSError, ValueError) as exc:
                raise EnvironmentUnavailable(f"metadata {self.settings.meta}: {exc}") from None
            self._images = {row["instance_id"]: row["image"] for row in rows if row.get("image")}
        image = self._images.get(instance_id)
        if image is None:
            raise EnvironmentUnavailable(f"no SWE-bench image for {instance_id} in {self.settings.meta}")
        return image

    def _ensure_image(self, image: str) -> None:
        if image in self._pulled:
            return
        if self._docker("image", "inspect", image, what="docker image inspect").returncode != 0:
            pulled = self._docker("pull", "--platform", PLATFORM, image, timeout=SETUP_TIMEOUT, what=f"pull {image}")
            if pulled.returncode != 0:
                raise EnvironmentUnavailable(f"cannot pull {image}: {_tail(_text(pulled.stderr) or _text(pulled.stdout))}")
        self._pulled.add(image)

    def _archive(self, repository_path: Path, revision: str) -> bytes:
        """The revision's tracked files as a tar, from the host clone (may fetch blobs if blobless)."""
        argv = ["git", "-C", str(repository_path), "archive", "--format=tar", revision]
        try:
            result = self.process(argv, timeout=SETUP_TIMEOUT)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise EnvironmentUnavailable(f"no checkout of {revision}: {exc}") from None
        if result.returncode != 0:
            raise EnvironmentUnavailable(f"no checkout of {revision}: {_tail(_text(result.stderr))}")
        return result.stdout

    def _start(self, image: str) -> str:
        result = self._docker(
            "run", "-d", "--rm", "--platform", PLATFORM, "--label", "memrev=check-runner", image, "sleep", "infinity",
            what=f"start {image}",
        )  # fmt: skip
        if result.returncode != 0:
            raise EnvironmentUnavailable(f"cannot start {image}: {_tail(_text(result.stderr))}")
        return _text(result.stdout).strip()

    def _load(self, container: str, revision: str, source: bytes, install: str) -> None:
        """Replace /testbed's files with the revision's source, commit them, and install."""
        script = (
            "{ set -e; "
            f"find {TESTBED} -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {{}} +; "
            f"tar -x -f - -C {TESTBED}; cd {TESTBED}; git add -A; "
            f"git -c user.name=memrev -c user.email=memrev@localhost commit -q --allow-empty -m 'memrev {revision}'; "
            f"{ACTIVATE}; {install}; }} 2>&1"
        )
        result = self._docker(
            "exec", "-i", "-w", TESTBED, container, "bash", "-c", script,
            input=source, timeout=SETUP_TIMEOUT, what=f"load {revision[:12]}",
        )  # fmt: skip
        if result.returncode != 0:
            raise EnvironmentUnavailable(
                f"cannot install {revision[:12]}: {_tail(_text(result.stdout) + _text(result.stderr))}"
            )

    def _exec(self, container: str, script: str, timeout: float):
        argv = [self.settings.docker, "exec", "-w", TESTBED, "-e", "LANG=C.UTF-8", "-e", "LC_ALL=C.UTF-8",
                container, "bash", "-c", script]  # fmt: skip
        return self.process(argv, timeout=timeout)


# Registration -------------------------------------------------------------

_SETTINGS = {"docker": str, "meta": lambda v: Path(v).expanduser(), "timeout": int, "containers": int}


def parse_settings(arg: str | None) -> DockerSettings:
    """`KEY=VALUE,...` (the text after `--runner docker=`) -> settings."""
    values = {}
    for item in filter(None, (arg or "").split(",")):
        key, sep, value = item.partition("=")
        if not sep or key not in _SETTINGS:
            raise RunError(f'docker runner: bad setting "{item}" (use {", ".join(_SETTINGS)} as KEY=VALUE)')
        try:
            values[key] = _SETTINGS[key](value)
        except ValueError:
            raise RunError(f'docker runner: bad value for {key}: "{value}"') from None
    return DockerSettings(**values)


def _factory(store: RunStore, arg: str | None) -> DockerCheckRunner:
    return DockerCheckRunner(parse_settings(arg))


register_runner("docker", _factory)
