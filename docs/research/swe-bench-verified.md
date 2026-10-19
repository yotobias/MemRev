# SWE-bench Verified metadata

Checked 2026-10-19.

## Local copy (use this first)

`swe-bench-verified-meta.jsonl`, in this folder (1.9 MB, 338 lines). It holds django, sympy and scikit-learn only, sorted by (repo, created_at). Fields:
`instance_id, repo, version, base_commit, created_at, environment_setup_commit, image, log_parser, FAIL_TO_PASS, PASS_TO_PASS`.
FAIL_TO_PASS and PASS_TO_PASS are already JSON lists, not strings.

Full path: /private/tmp/claude-501/-Users-nicholaswu-Downloads-TU-Delft-2026-2027/3e95dd8e-3f10-48fd-a708-6a14355885eb/scratchpad/pilot-b-notes/swe-bench-verified-meta.jsonl
The scratchpad is temporary. If the project needs the file for good, copy it into the repo (e.g. `data/`) or re-download it.

## Where it comes from

- HF dataset ids: `SWE-bench/SWE-bench_Verified` (current org) and `princeton-nlp/SWE-bench_Verified` (older mirror). Both have 500 rows in split `test`.
- One parquet file, 6.3 MB, with no auth needed:
  `https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified/resolve/main/data/test-00000-of-00001.parquet`
- Lightest way to load it: `pyarrow.parquet.read_table(path).to_pylist()`. You can skip `datasets`, which pulls in a large dependency tree. Pyarrow is about 35 MB.
- With `datasets`: `load_dataset("SWE-bench/SWE-bench_Verified", split="test")`.
- Recommendation: commit a trimmed JSONL fixture (like the one here) and keep the downloader as a separate one-off script, so tests never hit the network.

## Schema (SWE-bench/SWE-bench_Verified, current)

`base_commit, created_at, difficulty, environment_setup_commit, eval_type, image, instance_id, log_parser, repo, version, patch, test_patch, eval_script, problem_statement, hints_text, FAIL_TO_PASS (list[str]), PASS_TO_PASS (list[str])`

The current upload has three columns the old princeton-nlp copy did not:
- `image`: the exact Docker Hub tag, e.g. `swebench/sweb.eval.x86_64.django_1776_django-11099:latest`.
- `log_parser`: e.g. `parse_log_django`, `parse_log_sympy`, `parse_log_scikit`.
- `eval_script`: the full bash script the harness runs (see swe-bench-docker.md).
The older mirror may store FAIL_TO_PASS and PASS_TO_PASS as JSON strings. Handle both: `json.loads(x) if isinstance(x, str) else x`.

## `version`

`version` is a string like "3.0" or "0.21". It is the SWE-bench environment version, not a release tag. Compare versions as strings for equality only, because "1.10" sorts before "1.2". Every instance in one (repo, version) has the same `environment_setup_commit`, which I checked across all 500. That makes the conda env, and so the environment, identical within a version.

## Counts per (repo, version)

django/django, 231 total:
| version | n | base_commit date range |
|---|---|---|
| 1.11 | 1 | 2016-11 |
| 2.2 | 1 | 2018-06 |
| 3.0 | 36 | 2019-01 .. 2019-09 |
| 3.1 | 32 | 2019-09 .. 2020-05 |
| 3.2 | 43 | 2020-05 .. 2021-01 |
| 4.0 | 36 | 2021-01 .. 2021-09 |
| 4.1 | 34 | 2021-09 .. 2022-05 |
| 4.2 | 24 | 2022-05 .. 2023-01 |
| 5.0 | 24 | 2023-01 .. 2023-07 |

Versions 1.11 and 2.2 each have a single instance, so they can never produce a pair.

sympy/sympy, 75: 1.0:5, 1.1:16, 1.2:2, 1.4:6, 1.5:10, 1.6:5, 1.7:7, 1.8:4, 1.9:5, 1.10:4, 1.11:3, 1.12:8
scikit-learn/scikit-learn, 32: 0.20:5, 0.21:8, 0.22:12, 1.3:7
Other repos: sphinx 44, matplotlib 34, astropy 22, xarray 22, pytest 19, pylint 10, requests 8, seaborn 2, flask 1.

## created_at ordering: watch out

- `created_at` is when the GitHub PR was opened (ISO 8601 with Z). It is not the base_commit date.
- In django, `created_at` order and base_commit commit-date order disagree a lot. One 3.1 instance has created_at 2017-10-27 while its base_commit is from 2019-09 or later, because the PR sat open for years. Within versions, 151 of the 229 position slots differ between the two orderings.
- For "later instance" logic, order by the base_commit committer date (`git show -s --format=%cI <sha>`) and confirm with `git merge-base --is-ancestor`. Within each django version, all 3772 ordered pairs sorted by commit date passed the ancestry check (0 failures). Every django base_commit is on `main`.
- Spec story 4 says chronological validity comes from ancestry. Keep `created_at` for display only, or record that you chose it on purpose.

## Test id formats (matter for checks and the drift guard)

- django: `test_name (module.Class)` up to 4.1. From 4.2/5.0 on, `test_name (module.Class.test_name)`, following Python 3.11 unittest output. Some ids are a docstring's first line instead, because runtests runs at verbosity 2. Example (django-16950): `"If form data is provided, a parent's auto-generated alternate key is"`. Don't try to parse those into module paths.
- sklearn: pytest node ids, `sklearn/mixture/tests/test_x.py::test_y`.
- sympy: bare function names like `test_immutable`. The file comes from the test command in `eval_script`.

## Script used

/private/tmp/claude-501/-Users-nicholaswu-Downloads-TU-Delft-2026-2027/3e95dd8e-3f10-48fd-a708-6a14355885eb/scratchpad/scripts/extract2.py
(`uv run --no-project --with pyarrow python -I extract2.py verified.parquet out.jsonl`)
