"""Which SWE-ContextBench Lite tasks touch the same files/modules? Candidate
clusters for Pilot A, where shared assumptions between notes are plausible."""
import sys, re, pathlib, itertools, collections
import pandas as pd

data = pathlib.Path(sys.argv[1])
exp = pd.read_parquet(data / "SWEContextBench_Lite_Experience.parquet")
rl = pd.read_parquet(data / "SWEContextBench_Related_Lite.parquet")
rel = pd.read_parquet(data / "SWEContextBench_Relationship.parquet")
allt = pd.concat([exp.assign(kind="experience"), rl.assign(kind="related")]).drop_duplicates("instance_id")

def files(p): return set(re.findall(r"^diff --git a/(\S+) b/", p or "", re.M))
allt["files"] = allt["patch"].map(files)
allt["modules"] = allt["files"].map(lambda fs: {"/".join(f.split("/")[:2]) for f in fs})

print("tasks:", len(allt), "| by kind:", allt["kind"].value_counts().to_dict())

# same-commit pairs (within-revision sharing candidates)
same = rel.merge(rl[["instance_id", "base_commit"]], left_on="related_instance_id", right_on="instance_id") \
          .merge(exp[["instance_id", "base_commit"]], left_on="experience_instance_id", right_on="instance_id", suffixes=("_r", "_e"))
same = same[same.base_commit_r == same.base_commit_e]
print("\n== same-commit pairs (two tasks at one revision) ==", len(same))
for _, r in same.iterrows():
    fe, fr = allt.set_index("instance_id").loc[r.experience_instance_id, "files"], allt.set_index("instance_id").loc[r.related_instance_id, "files"]
    print(f"  {r.experience_instance_id:40s} {r.related_instance_id:40s} shared files: {len(fe & fr)}")

# file-level clusters per repo
print("\n== files edited by >=3 tasks (per repo) ==")
for repo, g in allt.groupby("repo"):
    cnt = collections.Counter(f for fs in g["files"] for f in fs)
    hot = [(f, c) for f, c in cnt.most_common() if c >= 3]
    if hot:
        print(f"\n{repo} ({len(g)} tasks)")
        for f, c in hot[:12]:
            ids = sorted(g[g["files"].map(lambda s: f in s)]["instance_id"])
            print(f"  {c:2d}  {f}\n      {', '.join(ids)}")

# module-level: tasks per module, modules with >=4 tasks
print("\n== modules (first two path parts) with >=4 tasks ==")
for repo, g in allt.groupby("repo"):
    cnt = collections.Counter(m for ms in g["modules"] for m in ms)
    hot = [(m, c) for m, c in cnt.most_common() if c >= 4]
    if hot:
        print(f"{repo}: " + ", ".join(f"{m} ({c})" for m, c in hot[:8]))

# how many tasks have at least one other task sharing a file
share = allt.copy()
fidx = collections.defaultdict(set)
for _, r in allt.iterrows():
    for f in r["files"]: fidx[f].add(r["instance_id"])
share["partners"] = share.apply(lambda r: len({i for f in r["files"] for i in fidx[f]} - {r["instance_id"]}), axis=1)
print("\ntasks with >=1 partner sharing an edited file:", int((share["partners"] > 0).sum()), "of", len(share))
print(share.groupby("repo")["partners"].apply(lambda s: int((s > 0).sum())).to_string())
share[["instance_id", "repo", "kind", "base_commit", "partners"]].assign(files=share["files"].map(lambda s: ";".join(sorted(s)))).to_csv(data / "lite_task_file_overlap.csv", index=False)
