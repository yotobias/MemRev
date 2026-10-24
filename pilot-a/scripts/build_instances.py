"""Write a mini-swe-agent instance directory: pilot-a/instances/<set>/instances.jsonl

    uv run python -I pilot-a/scripts/build_instances.py main              # the tasks in clusters.csv
    uv run python -I pilot-a/scripts/build_instances.py smoke <id> [...]  # named SWE-ContextBench tasks

Where a local derived image pilot-a/<owner>.<repo>-<n>:built exists (build_derived.sh;
decision of 2026-10-22 in pilot-a/CHANGES.md), image_name points to it instead of the
original image; clusters.csv keeps the original name.

mini-swe-agent reads only instance_id, problem_statement (the prompt) and image_name.
Everything derived from the fix or its tests (patch, test_patch, hints_text, FAIL_TO_PASS,
PASS_TO_PASS) is left out, so the file is safe for Lane N to open.
"""
import json, pathlib, subprocess, sys
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # python -I leaves the script dir off the path
from naming import derived_tag, image_for

ROOT = pathlib.Path(__file__).resolve().parents[2]
KEEP = ["instance_id", "repo", "base_commit", "problem_statement", "created_at", "version",
        "environment_setup_commit", "image_name"]
FORBIDDEN = {"patch", "test_patch", "hints_text", "FAIL_TO_PASS", "PASS_TO_PASS"}


def main(set_name, ids):
    data = ROOT / "pilot-a/data"
    scb = pd.concat([pd.read_parquet(data / "SWEContextBench_Experience.parquet").assign(kind="experience"),
                      pd.read_parquet(data / "SWEContextBench_Related.parquet").assign(kind="related")]
                     ).drop_duplicates("instance_id").set_index("instance_id", drop=False)
    if set_name == "main" and not ids:
        sel = pd.read_csv(ROOT / "pilot-a/clusters.csv")
        images = dict(zip(sel.instance_id, sel.image))
        ids = list(sel.instance_id)
    else:
        unknown = [i for i in ids if i not in scb.index]
        if unknown:
            sys.exit(f"not SWE-ContextBench tasks: {unknown}")
        images = {i: image_for(i, scb.at[i, "kind"]) for i in ids}
    for i in ids:
        derived = derived_tag(i)
        if subprocess.run(["docker", "image", "inspect", derived], capture_output=True).returncode == 0:
            images[i] = derived

    out = ROOT / "pilot-a/instances" / set_name
    if (out / "instances.jsonl").exists():
        sys.exit(f"{out}/instances.jsonl exists; instance sets are never overwritten")
    out.mkdir(parents=True)
    rows = []
    for i in ids:
        r = scb.loc[i].to_dict()
        r["image_name"] = images[i]
        r["created_at"] = str(r["created_at"])
        row = {k: r[k] for k in KEEP}
        assert not FORBIDDEN & row.keys()
        rows.append(row)
    with open(out / "instances.jsonl", "w", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    print(f"wrote {out / 'instances.jsonl'}: {len(rows)} instances; fields {KEEP}")
    for row in rows:
        if row["image_name"].startswith("pilot-a/"):
            print(f"  derived image: {row['instance_id']} -> {row['image_name']}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
