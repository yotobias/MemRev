"""Gold gate: does the official fix pass its own FAIL_TO_PASS tests in the task image?

    uv run python -I pilot-a/scripts/gold_gate.py [--workers 2] [instance_id ...]

Per task, in a fresh container of its image (bash with BASH_ENV=/root/.bashrc, as
mini-swe-agent runs commands): git apply the gold `patch`, git apply the `test_patch`,
run the tests, parse per-test status. Nothing is reinstalled: agent runs and probes use
the image as it is, so the gate does too (patches touching non-Python source are flagged).

Test commands follow the benchmark that grades the task:
  experience: the official SWE-bench Lite eval_script's test line, verbatim
  related:    the SCB harness (swebench_memory/harness/run_evaluation.py): django via
              tests/runtests.py <module> -v 2 --parallel=1, else python -m pytest <file> -v
Patches are applied as written (the SCB harness rewrites e.message -> str(e); we do not).

Appends one JSON line per task to pilot-a/env/gold_gate.jsonl; full logs (gold-patched
code and test names: Lane R only) go to pilot-a/env/gold_gate_logs/.
"""
import argparse, concurrent.futures as cf, datetime, json, pathlib, re, subprocess, sys, tempfile, time
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # python -I leaves the script dir off the path
from naming import derived_tag, image_for

ROOT = pathlib.Path(__file__).resolve().parents[2]
TIMEOUT = 1800
DJANGO_STATUS = {"ok": "PASSED", "FAIL": "FAILED", "ERROR": "ERROR", "skipped": "SKIPPED",
                 "expected failure": "XFAIL", "unexpected success": "XPASS"}


def as_list(v):
    return json.loads(v) if isinstance(v, str) else list(v)


def load_tasks(ids):
    from datasets import load_dataset
    sel = pd.read_csv(ROOT / "pilot-a/clusters.csv")
    if ids:  # ids outside clusters.csv (e.g. the smoke task) get kind and image by the usual rule
        extra = [i for i in ids if i not in set(sel.instance_id)]
        ov = pd.read_csv(ROOT / "pilot-a/data/lite_task_file_overlap.csv").set_index("instance_id")
        sel = pd.concat([sel[sel.instance_id.isin(ids)], pd.DataFrame(
            [dict(instance_id=i, kind=ov.at[i, "kind"], image=image_for(i, ov.at[i, "kind"])) for i in extra])])
    lite = load_dataset("SWE-bench/SWE-bench_Lite", split="test").to_pandas().set_index("instance_id")
    scb_exp = pd.read_parquet(ROOT / "pilot-a/data/SWEContextBench_Lite_Experience.parquet").set_index("instance_id")
    scb_rel = pd.read_parquet(ROOT / "pilot-a/data/SWEContextBench_Related_Lite.parquet").set_index("instance_id")
    tasks = []
    for t in sel.itertuples():
        if t.kind == "experience":
            r = lite.loc[t.instance_id]
            s = scb_exp.loc[t.instance_id]   # SCB copy must agree with the official one
            for col in ["base_commit", "patch", "test_patch"]:
                assert r[col] == s[col], f"{t.instance_id}: official vs SCB {col} differ"
            assert as_list(r.FAIL_TO_PASS) == as_list(s.FAIL_TO_PASS), f"{t.instance_id}: F2P differ"
            lines = r.eval_script.splitlines()
            a, b = lines.index(": '>>>>> Start Test Output'"), lines.index(": '>>>>> End Test Output'")
            cmds, source = lines[a + 1:b], "swebench_lite_eval_script"
        else:
            r = scb_rel.loc[t.instance_id]
            cmds, source = scb_commands(r.repo, as_list(r.FAIL_TO_PASS) + as_list(r.PASS_TO_PASS)), "scb_harness"
        tasks.append(dict(instance_id=t.instance_id, kind=t.kind, image=t.image, repo=r.repo,
                          base_commit=r.base_commit, patch=r.patch, test_patch=r.test_patch,
                          f2p=as_list(r.FAIL_TO_PASS), p2p=as_list(r.PASS_TO_PASS),
                          test_cmds=cmds, cmd_source=source))
    return tasks


def scb_commands(repo, tests):
    files = list(dict.fromkeys(t.split("::")[0] for t in tests))
    if repo == "django/django":
        cmds = []
        for f in files:
            p = pathlib.PurePosixPath(f).parts
            mod = p[1] if p[-1] == "tests.py" else ".".join(p[1:-1] + (p[-1][:-3],))
            cmds.append(f"python tests/runtests.py {mod} -v 2 --parallel=1")
        return cmds
    if repo == "sympy/sympy":
        # Deviation from the SCB harness (which uses pytest): sympy 1.5's test helpers call
        # py.test.mark, which the image's pytest no longer provides, so collection fails.
        # Use sympy's own runner, as official SWE-bench does for sympy.
        return ["PYTHONWARNINGS='ignore::UserWarning,ignore::SyntaxWarning' bin/test -C --verbose " + " ".join(files)]
    return [f"timeout {TIMEOUT} python -m pytest {f} -v --tb=short --no-header --color=no" for f in files]


# ---------- parsing: every format is normalised to one key per test ----------

def django_key(name, cls):
    """'test_x (a.b.C)' or py3.11+ 'test_x (a.b.C.test_x)' -> 'test_x (a.b.C)'."""
    if cls.endswith("." + name):
        cls = cls[: -len(name) - 1]
    return f"{name} ({cls})"


def norm_expected(test, repo):
    if repo == "django/django":
        m = re.match(r"^(\w+) \(([\w.]+)\)$", test)
        if m:
            return django_key(*m.groups())
        f, *rest = test.split("::")          # SCB form: tests/defer/tests.py::Class::test_x
        if len(rest) >= 2 and f.endswith(".py"):
            mod = ".".join(pathlib.PurePosixPath(f).parts[1:])[:-3]
            return django_key(rest[-1], f"{mod}.{'.'.join(rest[:-1])}")
        return test                          # SWE-bench names docstring tests by their docstring line
    return test


def parse(output, repo):
    res = {}
    if repo == "django/django":
        pending = None
        for line in output.splitlines():
            m = re.match(r"^(test\w*) \(([\w.]+)\)(.*)$", line)
            if m:
                pending = django_key(m.group(1), m.group(2))
                line = m.group(3)
            if pending:
                s = re.search(r"\.\.\. (ok|FAIL|ERROR|skipped|expected failure|unexpected success)", line)
                if s:
                    st = DJANGO_STATUS[s.group(1)]
                    res[pending] = st
                    text = line[: s.start()].strip()
                    if text:                 # docstring line, the name SWE-bench gives such tests
                        res.setdefault(text, st)
                    pending = None
        return res
    current_file = None
    for line in output.splitlines():
        line = line.rstrip()
        m = re.match(r"^(sympy/\S+\.py)\[\d+\]", line)                                    # bin/test file header
        if m:
            current_file = m.group(1); continue
        m = re.match(r"^(\S.*?::.*?) (PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b", line)   # pytest -v
        if m:
            res[m.group(1).removeprefix("/testbed/")] = m.group(2); continue
        m = re.match(r"^(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS) (\S.*?::.*?)(?: - .*)?$", line)  # pytest -rA
        if m:
            res.setdefault(m.group(2).removeprefix("/testbed/"), m.group(1)); continue
        if repo == "sympy/sympy":
            m = re.match(r"^(test_\w+) (ok|F|E|f|s|X)\b", line)                            # bin/test
            if m:  # case matters: F failed, f expected failure, X unexpected pass
                st = {"ok": "PASSED", "F": "FAILED", "E": "ERROR", "f": "XFAIL", "s": "SKIPPED", "X": "XPASS"}[m.group(2)]
                res.setdefault(m.group(1), st)            # official F2P uses bare names
                if current_file:
                    res[f"{current_file}::{m.group(1)}"] = st
    return res


def lookup(results, test, repo):
    return results.get(norm_expected(test, repo), "MISSING")


# ---------- one task ----------

def gate(task, logdir):
    iid = task["instance_id"]
    started = time.time()
    non_py = sorted({l[6:] for l in task["patch"].splitlines() if l.startswith("+++ b/")
                     and not l.endswith((".py", ".pyi", ".rst", ".txt", ".md"))})
    with tempfile.TemporaryDirectory(prefix=f"gate-{iid}-") as tmp:
        tmp = pathlib.Path(tmp)
        (tmp / "patch.diff").write_text(task["patch"])
        (tmp / "test_patch.diff").write_text(task["test_patch"])
        script = ["cd /testbed", "git config --global --add safe.directory /testbed",
                  "echo '>>> apply patch'", "git apply -v /gate/patch.diff || { echo GATE_APPLY_FAILED=patch; exit 90; }",
                  "echo '>>> apply test_patch'", "git apply -v /gate/test_patch.diff || { echo GATE_APPLY_FAILED=test_patch; exit 91; }",
                  "echo '>>> python'; python --version 2>&1", "echo '>>> tests'"]
        script += [c + " 2>&1" for c in task["test_cmds"]]
        (tmp / "run.sh").write_text("\n".join(script) + "\n")
        name = f"gate-{iid.replace('__', '-')}-{int(started)}"
        cmd = ["docker", "run", "--rm", "--name", name, "-e", "BASH_ENV=/root/.bashrc",
               "-v", f"{tmp}:/gate:ro", task["image"], "bash", "/gate/run.sh"]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT + 120)
            out, code, timed_out = p.stdout + "\n--- stderr\n" + p.stderr, p.returncode, False
        except subprocess.TimeoutExpired as e:
            subprocess.run(["docker", "kill", name], capture_output=True)
            out, code, timed_out = (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""), None, True

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log = logdir / f"{iid}.{stamp}.log"
    log.write_text(f"$ {' '.join(cmd)}\n# run.sh:\n" + "\n".join(script) + "\n\n" + out)

    apply_failed = re.search(r"GATE_APPLY_FAILED=(\w+)", out)
    res = parse(out.split(">>> tests", 1)[-1], task["repo"])
    f2p = {t: lookup(res, t, task["repo"]) for t in task["f2p"]}
    p2p = {t: lookup(res, t, task["repo"]) for t in task["p2p"]}
    if timed_out:
        status = "timeout"
    elif apply_failed:
        status = f"apply_failed:{apply_failed.group(1)}"
    elif all(v == "PASSED" for v in f2p.values()):
        status = "pass"
    elif any(v == "MISSING" for v in f2p.values()) and not any(v in ("FAILED", "ERROR") for v in f2p.values()):
        status = "inconclusive"   # tests not found in output: setup/collection problem or parser gap
    else:
        status = "fail"
    pv = list(p2p.values())
    return dict(instance_id=iid, kind=task["kind"], image=task["image"], status=status,
                f2p=f2p, p2p_passed=pv.count("PASSED"), p2p_failed=sum(v in ("FAILED", "ERROR") for v in pv),
                p2p_missing=pv.count("MISSING"), p2p_total=len(pv),
                p2p_not_passed=sorted(t for t, v in p2p.items() if v != "PASSED")[:20],
                python=(re.search(r">>> python\n(Python [\d.]+)", out) or [None, None])[1],
                test_cmds=task["test_cmds"], cmd_source=task["cmd_source"], exit_code=code,
                patch_non_python_files=non_py, reinstalled=False, network=True, f2p_only=task["f2p_only"],
                seconds=round(time.time() - started, 1), log=str(log.relative_to(ROOT)),
                gated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--derived", action="store_true",
                    help="use the local pilot-a/<id>:built image (build_derived.sh) where one exists")
    ap.add_argument("--f2p-only", action="store_true",
                    help="sympy bin/test only: run just the FAIL_TO_PASS tests (-k), for slow test files")
    a = ap.parse_args()
    env = ROOT / "pilot-a/env"; logdir = env / "gold_gate_logs"; logdir.mkdir(parents=True, exist_ok=True)
    tasks = load_tasks(a.ids)
    for t in tasks:
        t["f2p_only"] = False
        if a.f2p_only and t["repo"] == "sympy/sympy":
            names = sorted({x.split("::")[-1] for x in t["f2p"]})
            t["test_cmds"] = [c + " -k " + " ".join(names) if " bin/test " in f" {c}" else c for c in t["test_cmds"]]
            t["f2p_only"] = True
    if a.derived:
        for t in tasks:
            tag = derived_tag(t["instance_id"])
            if subprocess.run(["docker", "image", "inspect", tag], capture_output=True).returncode == 0:
                t["image"] = tag
    print(f"gating {len(tasks)} tasks, {a.workers} workers", flush=True)
    with cf.ThreadPoolExecutor(a.workers) as ex, open(env / "gold_gate.jsonl", "a") as out:
        futs = {ex.submit(gate, t, logdir): t for t in tasks}
        for fut in cf.as_completed(futs):
            try:
                r = fut.result()
            except Exception as e:  # one broken task must not stop the others
                t = futs[fut]
                r = dict(instance_id=t["instance_id"], kind=t["kind"], image=t["image"], status="gate_error",
                         error=repr(e), f2p={}, p2p_passed=0, p2p_failed=0, p2p_missing=0, p2p_total=0,
                         python=None, seconds=0, patch_non_python_files=[],
                         gated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"))
            out.write(json.dumps(r) + "\n"); out.flush()
            f2p = f"{sum(v == 'PASSED' for v in r['f2p'].values())}/{len(r['f2p'])}"
            print(f"{r['instance_id']:34} {r['status']:14} F2P {f2p:6} P2P {r['p2p_passed']}/{r['p2p_total']}"
                  f" ({r['p2p_failed']} fail, {r['p2p_missing']} missing)  {r['python']}  {r['seconds']}s"
                  + (f"  NON-PY PATCH {r['patch_non_python_files']}" if r["patch_non_python_files"] else ""), flush=True)


if __name__ == "__main__":
    main()
