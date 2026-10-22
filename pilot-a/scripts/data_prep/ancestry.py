"""For every SWE-ContextBench Lite pair, check git ancestry between the two
base commits and whether the commits in between touch files changed by the
earlier task's gold patch. Uses blob-less clones (trees only)."""
import sys, re, subprocess, pathlib, concurrent.futures as cf
import pandas as pd

data = pathlib.Path(sys.argv[1]); repos = pathlib.Path(sys.argv[2]); repos.mkdir(parents=True, exist_ok=True)
rel = pd.read_parquet(data / "SWEContextBench_Relationship.parquet")
exp = pd.read_parquet(data / "SWEContextBench_Lite_Experience.parquet")
rl = pd.read_parquet(data / "SWEContextBench_Related_Lite.parquet")
cols = ["instance_id", "repo", "base_commit", "created_at", "patch", "test_patch", "FAIL_TO_PASS"]
pairs = rel.merge(rl[cols], left_on="related_instance_id", right_on="instance_id") \
           .merge(exp[cols], left_on="experience_instance_id", right_on="instance_id", suffixes=("_rel", "_exp"))
print("pairs", len(pairs))

def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)

def clone(name):
    d = repos / name.replace("/", "__")
    if not (d / ".git").exists():
        r = subprocess.run(["git", "clone", "--filter=blob:none", "--quiet", f"https://github.com/{name}.git", str(d)],
                           capture_output=True, text=True)
        print("cloned", name, r.returncode, r.stderr[-200:])
    return d

with cf.ThreadPoolExecutor(6) as ex:
    dirs = dict(zip(pairs["repo_exp"].unique(), ex.map(clone, pairs["repo_exp"].unique())))

def patch_files(p):
    return set(re.findall(r"^diff --git a/(\S+) b/", p or "", re.M))

rows = []
for _, p in pairs.iterrows():
    d = dirs[p["repo_exp"]]
    a, b = p["base_commit_exp"], p["base_commit_rel"]
    if a == b:
        rows.append(dict(pair=f'{p["experience_instance_id"]}->{p["related_instance_id"]}', repo=p["repo_exp"], relation="same", older=None, newer=None, commits_between=0, files_changed=0, overlap_older_patch=0, older_patch_files=0)); continue
    exp_is_anc = git(d, "merge-base", "--is-ancestor", a, b).returncode == 0
    rel_is_anc = git(d, "merge-base", "--is-ancestor", b, a).returncode == 0
    if exp_is_anc:
        relation, older, newer, older_id, older_patch = "exp->rel", a, b, p["experience_instance_id"], p["patch_exp"]
    elif rel_is_anc:
        relation, older, newer, older_id, older_patch = "rel->exp", b, a, p["related_instance_id"], p["patch_rel"]
    else:
        rows.append(dict(pair=f'{p["experience_instance_id"]}->{p["related_instance_id"]}', repo=p["repo_exp"], relation="unrelated/divergent", older=None, newer=None, commits_between=None, files_changed=None, overlap_older_patch=None, older_patch_files=None)); continue
    n = git(d, "rev-list", "--count", f"{older}..{newer}").stdout.strip()
    changed = set(git(d, "diff", "--name-only", older, newer).stdout.split())
    pf = patch_files(older_patch)
    rows.append(dict(pair=f'{p["experience_instance_id"]}->{p["related_instance_id"]}', repo=p["repo_exp"], relation=relation, older=older_id, newer=(p["related_instance_id"] if relation=="exp->rel" else p["experience_instance_id"]), commits_between=int(n or 0), files_changed=len(changed), overlap_older_patch=len(pf & changed), older_patch_files=len(pf)))

df = pd.DataFrame(rows); df.to_csv(data / "lite_pairs_ancestry.csv", index=False)
print("\n== relation counts ==\n", df["relation"].value_counts().to_string())
usable = df[df["relation"].isin(["exp->rel", "rel->exp"])]
print("\n== usable chronological pairs ==", len(usable))
print("commits between: median", usable["commits_between"].median(), "min", usable["commits_between"].min(), "max", usable["commits_between"].max())
print("pairs where in-between commits touch a file from the older gold patch:", int((usable["overlap_older_patch"] > 0).sum()))
print("\nper repo:")
print(usable.groupby("repo").agg(pairs=("pair", "count"), touch_patch_files=("overlap_older_patch", lambda s: int((s > 0).sum())), med_commits=("commits_between", "median")).to_string())
print("\n== all usable pairs ==")
print(usable.sort_values(["repo", "commits_between"])[["repo", "older", "newer", "commits_between", "files_changed", "overlap_older_patch", "older_patch_files"]].to_string(index=False))
