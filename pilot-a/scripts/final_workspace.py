"""Rebuild each task's final workspace from a run (Plan_v2 Section 4, parts 1 and 2).

    uv run --locked python -I pilot-a/scripts/final_workspace.py pilot-a/runs/claude-sonnet-5-5/main-3

The agent's container is gone, and its patch is a `git diff` of files it chose, so files it
created can be missing. Per task, two fresh containers of the image the run used:
  replay: every command of the trajectory re-run in order, as mini-swe-agent ran it
          (docker exec -w /testbed, the shipped env, bash -c, 60 s timeout);
  patch:  only `git apply` of the submitted patch.
Writes <run>/<id>/final_workspace.json: diff stats against base_commit for both, untracked files
after the replay (what the patch misses), whether both tracked diffs agree, and how many
replayed commands returned a different exit code than in the run (both measure how faithful
the replay is). Part 3 (re-run the agent's last verify step) waits for Lane N's segmenter.
"""
import concurrent.futures as cf, json, pathlib, re, subprocess, sys, uuid

ENV = {"PAGER": "cat", "MANPAGER": "cat", "LESS": "-R", "PIP_PROGRESS_BAR": "off",
       "TQDM_DISABLE": "1", "BASH_ENV": "/root/.bashrc"}  # minisweagent swebench.yaml, environment.env
TIMEOUT = 60


def actions_and_codes(traj):
    acts, codes = [], []
    for m in traj["messages"]:
        for tc in m.get("tool_calls") or []:
            acts.append(json.loads(tc["function"]["arguments"])["command"])
        if m.get("role") == "tool":
            c = re.search(r"<returncode>(-?\d+)</returncode>", str(m.get("content")))
            codes.append(int(c.group(1)) if c else None)
    return acts, codes


class Box:
    def __init__(self, image):
        self.name = f"pa-ws-{uuid.uuid4().hex[:8]}"
        subprocess.run(["docker", "run", "-d", "--rm", "--name", self.name, "-w", "/testbed", image,
                        "sleep", "2h"], check=True, capture_output=True)

    def sh(self, cmd, stdin=None):
        args = ["docker", "exec", "-i", "-w", "/testbed"]
        for k, v in ENV.items():
            args += ["-e", f"{k}={v}"]
        try:
            p = subprocess.run(args + [self.name, "bash", "-c", cmd], input=stdin, text=True, encoding="utf-8",
                               errors="replace", capture_output=True, timeout=TIMEOUT)
            return p.returncode, p.stdout
        except subprocess.TimeoutExpired:
            return -1, ""   # as mini-swe-agent records a timeout

    def state(self, base):
        diff = self.sh(f"git diff {base}")[1]
        # "+ - path" per file; drops the mode-only changes of the swebench commit ("0 0", binaries "- -");
        # tracked_diff_same still compares the full diffs
        files = [l.replace("\t", " ") for l in self.sh(f"git diff --numstat {base}")[1].splitlines()
                 if not l.startswith(("0\t0\t", "-\t-\t"))]
        untracked = self.sh("git status --porcelain --untracked-files=all | sed -n 's/^?? //p'")[1].split()
        return diff, files, untracked

    def close(self):
        subprocess.run(["docker", "rm", "-f", self.name], capture_output=True)


def one(run, iid, image, base, patch):
    traj = json.loads((run / iid / f"{iid}.traj.json").read_text())
    acts, codes = actions_and_codes(traj)
    rep = Box(image)
    try:
        got = [rep.sh(a)[0] for a in acts]
        r_diff, r_files, r_untracked = rep.state(base)
    finally:
        rep.close()
    pat = Box(image)
    try:
        applied = pat.sh("git apply -", stdin=patch)[0] == 0 if patch.strip() else None
        p_diff, p_files, _ = pat.state(base)
    finally:
        pat.close()
    # the submit command ends the run, so it has no recorded exit code
    comparable = len(codes) in (len(acts), len(acts) - 1)
    return dict(instance_id=iid, image=image, base_commit=base, commands=len(acts),
                exit_code_mismatches=sum(a != b for a, b in zip(got, codes)) if comparable else None,
                patch_applies=applied, patch_files=p_files, replay_files=r_files,
                tracked_diff_same=r_diff == p_diff, untracked_after_replay=r_untracked)


def main(run):
    run = pathlib.Path(run)
    meta = json.loads((run / "run_meta.json").read_text())
    insts = {json.loads(l)["instance_id"]: json.loads(l)
             for l in open(pathlib.Path(meta["instance_set"]) / "instances.jsonl")}
    preds = json.loads((run / "preds.json").read_text())
    jobs = {iid: (meta["images"][iid]["image"], insts[iid]["base_commit"], preds[iid].get("model_patch") or "")
            for iid in sorted(preds)}
    with cf.ThreadPoolExecutor(4) as ex:
        futs = {ex.submit(one, run, iid, *j): iid for iid, j in jobs.items()}
        for f in cf.as_completed(futs):
            r = f.result()
            (run / r["instance_id"] / "final_workspace.json").write_text(json.dumps(r, indent=2) + "\n")
            print(f"{r['instance_id']:34} cmds {r['commands']:3}  exit mismatches {r['exit_code_mismatches']}  "
                  f"applies {r['patch_applies']}  same {r['tracked_diff_same']}  untracked {r['untracked_after_replay']}"
                  + ("" if r["tracked_diff_same"] else f"\n    patch {r['patch_files']}\n    replay {r['replay_files']}"))


if __name__ == "__main__":
    main(sys.argv[1])
