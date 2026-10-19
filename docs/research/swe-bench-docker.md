# SWE-bench Docker images and the test harness

Sources: SWE-bench repo v4.1.0 (`swebench/harness/test_spec/python.py`, `constants/python.py`, `log_parsers/python.py`, `grading.py`) and main (v5.0.2, which moved image code to `swebench/image_builder/`). Also the dataset's `image`/`eval_script` columns and the Docker Hub API. I pulled no images.

## Image layers and naming

The harness builds three layers:
1. base: `sweb.base.py.x86_64:latest` (Ubuntu + miniconda at /opt/miniconda3)
2. env: `sweb.env.py.x86_64.<hash>:latest`. Holds the conda env `testbed` with the deps for one (repo, version), keyed by environment_setup_commit.
3. instance: `sweb.eval.x86_64.<instance_id>:latest`. Adds the repo at base_commit in /testbed, installed into the env.

Docker Hub (namespace `swebench`) publishes the instance images only. Docker Hub does not allow `__` in names, so it is replaced with `_1776_`:
`swebench/sweb.eval.x86_64.django_1776_django-11099:latest`
The dataset's `image` column already has this exact string, so use it and don't rebuild the name yourself.
Tags seen: `latest`, `v1`, `v2`. Architecture is **amd64 only**. Compressed size for django-11099 is about 1.15 GB, more once unpacked. I found no env images on Docker Hub.

Pull and inspect one:
```
docker pull --platform linux/amd64 swebench/sweb.eval.x86_64.django_1776_django-11099:latest
docker run --rm -it --platform linux/amd64 swebench/sweb.eval.x86_64.django_1776_django-11099:latest bash
```

## Inside the container

- The repo is at `/testbed`, git-tracked, with HEAD on an extra commit "SWE-bench" made on top of base_commit after install.
- Conda: `source /opt/miniconda3/bin/activate && conda activate testbed`.
- Python per django version: 3.0–3.2 use py3.6, 4.0 uses 3.8, 4.1–4.2 use 3.9, 5.0 uses 3.11. Install is `python -m pip install -e .` (editable, pointing at /testbed). sklearn uses `pip install -v --no-use-pep517 --no-build-isolation -e .` (a C build, so slow). sympy uses `pip install -e .`.

## Important: commits after base_commit are deleted in the image

The repo setup in the instance image does this (v4.1.0 `make_repo_script_list_py`):
```
git clone -o origin --single-branch https://github.com/<repo> /testbed
git reset --hard <base_commit>
git remote remove origin
# delete tags newer than base_commit
git reflog expire --expire=now --all && git gc --prune=now --aggressive
# fails the build if any commit newer than base_commit is still reachable
```
So **target revision T is not in S's image**. `git checkout <T>` inside the container fails. To test T in the shared image (spec: "the SWE-bench Docker image shared by S and T"), bring the source in from the host:
- (a) `git -C <host clone> archive <T> | docker exec -i <c> tar -x -C /testbed` after clearing tracked files (`git -C /testbed rm -rq . && git clean -fdq`, or rsync semantics). Then re-run `pip install -e .`, which is cheap for django but recompiles for sklearn.
- (b) Bind-mount a host worktree at T over /testbed (`-v <worktree>:/testbed`). The editable install still resolves to /testbed. On macOS this is slower, and file ownership may differ.
- (c) Inside the container, `git fetch https://github.com/django/django <T>`. This needs network and is slow. Avoid.
Either S's or T's instance image works as "the shared image": inside one version both carry the same env. Pick one rule, e.g. always S's image, and record it.
After swapping the source, sanity-check with `python -c "import django; print(django.__file__, django.VERSION)"`.

## How the harness runs tests

`eval_script` (in the dataset) does: activate conda, `cd /testbed`, set locale (django 3.x), `git diff <base>`, re-run the install, `git checkout <base> <test files>`, `git apply` the test_patch, then
```
: '>>>>> Start Test Output'
<test_cmd> <test targets>
: '>>>>> End Test Output'
```
then resets the test files. The grader only reads the text between those two markers.

Test commands:
- django: `./tests/runtests.py --verbosity 2 --settings=test_sqlite --parallel 1 <labels>`. Labels are dotted, e.g. `auth_tests.test_validators`. Django 3.x also needs `LANG/LC_ALL=en_US.UTF-8`, with a `locale-gen` step first.
- sklearn and other pytest repos: `pytest -rA <files>`. The `-rA` summary lines (`PASSED path::id`) are what gets parsed.
- sympy: `PYTHONWARNINGS='ignore::UserWarning,ignore::SyntaxWarning' bin/test -C --verbose <files>`

Parsers (`swebench/harness/log_parsers/python.py`, mapped by repo, also named in the `log_parser` column) return `{test_id: PASSED|FAILED|SKIPPED|ERROR|XFAIL}`:
- `parse_log_django`: line-based. `"<id> ... ok"` means PASSED, `" ... skipped"` SKIPPED, `" ... FAIL"` or a line starting `FAIL:` FAILED, `" ... ERROR"` or `ERROR:` ERROR. It also handles an `ok` on the next line after multi-line output, plus a few instance-specific hacks. The id is everything before `" ... "`, e.g. `test_x (auth_tests.test_validators.UsernameValidatorsTests)`.
- `parse_log_pytest`: lines starting with a status word, `STATUS id`. `parse_log_scikit` = `parse_log_pytest_v2`, which also strips ANSI codes and handles the older `id STATUS` form.
- `parse_log_sympy`: parses `test_name ok|F|E` lines from bin/test --verbose.
Grading (`grading.py`): if the log contains `>>>>> Patch Apply Failed` or `>>>>> Tests Timed Out`, or lacks the start/end markers, the result is `{}` and the instance counts as failed. For Pilot B, treat this as harness failure, which means **inconclusive**, not contradicted.

## Running our own check (suggested shape for ticket 07)

```
docker run -d --name memrev-<id> --platform linux/amd64 <image> sleep infinity
docker exec memrev-<id> bash -lc 'source /opt/miniconda3/bin/activate testbed && cd /testbed && ./tests/runtests.py --verbosity 2 --settings=test_sqlite --parallel 1 <label> 2>&1'
docker rm -f memrev-<id>
```
- Give every command an outer timeout, using `timeout` inside the container or a subprocess timeout. On a timeout, kill the container.
- Collect exit code + stdout. Parse with your own copy of the django parser, or import `swebench.harness.log_parsers`. The `swebench` package pulls in many deps, so a vendored ~40-line copy is lighter.
- Repeat runs (3x per spec) can reuse one container if you reset /testbed between runs (`git reset --hard && git clean -fdq`), or use a fresh `docker run --rm` each time, which is cleaner but slower.
- A drift guard could use a small, stable label set, e.g. a few `utils_tests` / `test_utils` modules that exist across 3.0–5.0. Check per version that the labels exist.

## Apple Silicon (this Mac is arm64, Docker 28.5)

- The images are amd64 only, so pass `--platform linux/amd64` on pull and run, or set `DOCKER_DEFAULT_PLATFORM=linux/amd64`. Without it, Docker warns about the platform mismatch.
- Emulation: Docker Desktop uses Rosetta when "Use Rosetta for x86_64/amd64 emulation" is on (Settings > General), and QEMU otherwise. Rosetta is several times faster. Expect django test modules to run noticeably slower than on x86 hardware, and sklearn installs/compiles to be very slow. Set generous timeouts.
- Disk: each instance image is about 1–3 GB unpacked. Pull only the images you need, and `docker image prune` between batches.
- The Docker daemon was **not running** when I checked (`Cannot connect to the Docker daemon`). Start Docker Desktop before ticket 07/11 work. Tests should mock the docker boundary and not need a daemon.
- Under emulation, a container can crash for platform reasons (an illegal instruction, a segfault in a C extension). Count these as harness failures, which means inconclusive.
