"""Refine: for each usable pair count commits between the two base commits that
touch files of the older gold patch (>=1 is the fix itself), and the same for
the older task's FAIL_TO_PASS test files."""
import sys, re, subprocess, pathlib, json, ast
import pandas as pd

data = pathlib.Path(sys.argv[1]); repos = pathlib.Path(sys.argv[2])
anc = pd.read_csv(data / "lite_pairs_ancestry.csv")
exp = pd.read_parquet(data / "SWEContextBench_Lite_Experience.parquet")
rl = pd.read_parquet(data / "SWEContextBench_Related_Lite.parquet")
inst = pd.concat([exp, rl]).drop_duplicates("instance_id").set_index("instance_id")

def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True).stdout

def files(p): return sorted(set(re.findall(r"^diff --git a/(\S+) b/", p or "", re.M)))

rows = []
for _, r in anc[anc["relation"].isin(["exp->rel", "rel->exp"])].iterrows():
    o, n = inst.loc[r["older"]], inst.loc[r["newer"]]
    d = repos / o["repo"].replace("/", "__")
    pf = files(o["patch"]); tf = files(o["test_patch"])
    c_src = int(git(d, "rev-list", "--count", f'{o["base_commit"]}..{n["base_commit"]}', "--", *pf).strip() or 0) if pf else 0
    c_tst = int(git(d, "rev-list", "--count", f'{o["base_commit"]}..{n["base_commit"]}', "--", *tf).strip() or 0) if tf else 0
    # does the newer task's gold patch touch the same files as the older one?
    nf = files(n["patch"])
    rows.append(dict(repo=o["repo"], older=r["older"], newer=r["newer"], commits_between=r["commits_between"],
                     older_src_files=len(pf), commits_touching_src=c_src, commits_touching_tests=c_tst,
                     newer_patch_shares_file=len(set(pf) & set(nf)), py_version_older=o["version"], py_version_newer=n["version"]))
df = pd.DataFrame(rows); df.to_csv(data / "lite_pairs_refined.csv", index=False)
print("usable pairs", len(df))
print("pairs with >=1 later commit (beyond the fix) touching older patch files:", int((df["commits_touching_src"] > 1).sum()))
print("pairs where newer gold patch edits a file of the older patch:", int((df["newer_patch_shares_file"] > 0).sum()))
print("pairs with repo 'version' field unchanged:", int((df["py_version_older"] == df["py_version_newer"]).sum()))
print("\nbuckets by commits_between: <=100:", int((df.commits_between <= 100).sum()),
      " 101-1000:", int(((df.commits_between > 100) & (df.commits_between <= 1000)).sum()),
      " >1000:", int((df.commits_between > 1000).sum()))
print(df.sort_values(["repo", "commits_between"]).to_string(index=False))
