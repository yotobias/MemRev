"""Write the frozen Pilot A task list and the same-PR groups.

    uv run --locked python -I pilot-a/scripts/build_clusters.py pilot-a/data pilot-a

Inputs: the SCB parquet files in the data dir (data_prep/inspect_scb.py), <data>/v33_forward_links.csv
(the revision-pair analysis, CHANGES.md 2026-11-09) and full SWE-bench from Hugging Face (edited files
come from its `patch`; 6 of the tasks are not in Verified).
Outputs: <data>/same_pr_groups.csv (all SCB tasks) and <out>/clusters.csv (base tasks only;
`related_ids` keeps all SCB links, `targets` the forward ones that form revision pairs; neither is run).
Fails loudly if the selection breaks a rule (team decisions V33, V34).
"""
import itertools, pathlib, re, sys
import pandas as pd
from datasets import load_dataset

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # python -I leaves the script dir off the path
from naming import image_for

REPOS = {"django/django", "sympy/sympy", "scikit-learn/scikit-learn"}  # team decisions V11, V12
# Rule (V33, V34): candidates = SWE-bench base tasks with at least one forward SCB link (a valid
# revision pair); a candidate is selected iff its fix edits a file in a directory where the fix of
# another candidate also edits one. Clusters are those directories (django/db/models/ joined with sql/).
CLUSTERS = {  # cluster: (directories of the fix's files, instance ids)
    "D1": (["django/db/models", "django/db/models/sql"],
           ["django__django-11555", "django__django-12209", "django__django-12589",
            "django__django-15382", "django__django-15930", "django__django-16910"]),
    "S1": (["sympy/printing"], ["sympy__sympy-14774", "sympy__sympy-14976", "sympy__sympy-15976", "sympy__sympy-16766"]),
    "S2": (["sympy/core"], ["sympy__sympy-18057", "sympy__sympy-20801"]),
    "K1": (["sklearn/utils"], ["scikit-learn__scikit-learn-10949", "scikit-learn__scikit-learn-25638"]),
    "D2": (["django/utils"], ["django__django-11276", "django__django-14792"]),
}


def same_pr_groups(data):
    """Union-find over all SCB tasks: same PR URL or byte-identical gold patch."""
    exp = pd.read_parquet(data / "SWEContextBench_Experience.parquet")
    rel = pd.read_parquet(data / "SWEContextBench_Related.parquet")
    link = pd.read_parquet(data / "SWEContextBench_Relationship.parquet")
    tasks = pd.concat([exp.assign(kind="experience"), rel.assign(kind="related")])
    tasks = tasks[["instance_id", "repo", "kind", "patch", "problem_statement"]].drop_duplicates("instance_id")

    # A task can carry several PRs (django-28147 is linked to 11383 and 11587); it then
    # joins the group of each, which can only merge groups, never split them.
    # Some "PR" URLs are /issues/ links (sklearn-13241); GitHub issues and PRs share one
    # number sequence per repo, so issues/N -> pull/N is lossless. GitHub URLs ignore case
    # (briannesbitt/Carbon vs carbon), so they are compared lowercased.
    pr = {}
    for a, b in [("related_instance_id", "related_pr_url"), ("experience_instance_id", "experience_pr_url")]:
        for iid, url in link[[a, b]].drop_duplicates().itertuples(index=False):
            pr.setdefault(iid, set()).add(re.sub(r"/issues/(\d+)$", r"/pull/\1", url.lower()))
    for t in tasks.itertuples():  # SWE-bench convention: experience id number = PR number
        if t.kind == "experience":
            own = f"https://github.com/{t.repo}/pull/{t.instance_id.rsplit('-', 1)[1]}".lower()
            if pr.setdefault(t.instance_id, {own}) != {own}:
                sys.exit(f"{t.instance_id}: Relationship PR {pr[t.instance_id]} != {own}")
    missing = set(tasks.instance_id) - set(pr)
    if missing:
        sys.exit(f"no PR URL for {sorted(missing)}")

    parent = {i: i for i in tasks.instance_id}
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    def union(members):
        members = list(members)
        for m in members[1:]:
            parent[find(m)] = find(members[0])
    tasks["pr_url"] = tasks.instance_id.map(lambda i: ";".join(sorted(pr[i])))
    by_pr = tasks.assign(url=tasks.pr_url.str.split(";")).explode("url")
    for _, g in by_pr.groupby("url"):
        union(g.instance_id)
    for _, g in tasks.groupby("patch"):
        union(g.instance_id)

    tasks["root"] = tasks.instance_id.map(find)
    def label(g):  # stable, readable group id: repo#lowest PR number in the group
        nums = sorted(int(u.rsplit("/", 1)[1]) for urls in g.pr_url for u in urls.split(";"))
        return f"{g.repo.iloc[0]}#{nums[0]}"
    names = {r: label(g) for r, g in tasks.groupby("root")}
    tasks["same_pr_group"] = tasks.root.map(names)
    tasks["group_size"] = tasks.groupby("same_pr_group").instance_id.transform("size")
    return tasks.drop(columns="root"), link


def main(data, out):
    data, out = pathlib.Path(data), pathlib.Path(out)
    tasks, link = same_pr_groups(data)
    tasks.sort_values(["same_pr_group", "instance_id"])[
        ["same_pr_group", "group_size", "instance_id", "kind", "pr_url"]
    ].to_csv(data / "same_pr_groups.csv", index=False)

    swe = load_dataset("SWE-bench/SWE-bench", split="test").to_pandas()
    related = link.groupby("experience_instance_id").related_instance_id.agg(lambda s: ";".join(sorted(set(s))))
    fwd = pd.read_csv(data / "v33_forward_links.csv")
    targets = fwd.groupby("base").related.agg(lambda s: ";".join(sorted(set(s))))
    cand = swe[swe.repo.isin(REPOS) & swe.instance_id.isin(targets.index)].set_index("instance_id")
    edited = cand.patch.map(lambda p: set(re.findall(r"^diff --git a/(\S+)", p, re.M)))
    dirs = edited.map(lambda fs: {f.rsplit("/", 1)[0] for f in fs})
    by_id = tasks.set_index("instance_id")

    errors = [f"{b}: forward link but not a candidate" for b in sorted(set(targets.index) - set(cand.index))]
    errors += [f"{b} -> {r}: not an SCB link" for b, r in fwd[["base", "related"]].itertuples(index=False)
               if r not in related.get(b, "").split(";")]
    rows = []
    for cl, (cdirs, ids) in CLUSTERS.items():
        hits = {i for i in cand.index if dirs[i] & set(cdirs)}
        for iid in ids:
            if iid not in cand.index:
                errors.append(f"{iid}: not a candidate ({sorted(REPOS)}, with a forward SCB link)"); continue
            if iid not in hits:
                errors.append(f"{iid}: edits nothing in {cdirs} (edits {sorted(edited[iid])})")
            if cand.at[iid, "image"] != image_for(iid, "experience"):
                errors.append(f"{iid}: image {cand.at[iid, 'image']} != {image_for(iid, 'experience')}")
            rows.append(dict(instance_id=iid, cluster=cl, kind="experience", image=image_for(iid, "experience"),
                             base_commit=cand.at[iid, "base_commit"], same_text=False, same_pr_group=by_id.at[iid, "same_pr_group"], role="cluster",
                             related_ids=related[iid], targets=targets[iid]))
        if hits - set(ids):  # the rule selects every candidate in the cluster's directories
            errors.append(f"{cl}: candidates editing files in {cdirs} left out: {sorted(hits - set(ids))}")
    sel = pd.DataFrame(rows)
    covered = {d for cdirs, _ in CLUSTERS.values() for d in cdirs}
    shared = dirs.explode().value_counts()  # a directory edited by two or more candidates' fixes is a cluster
    errors += [f"{d}: edited by {n} candidates but in no cluster" for d, n in shared[shared > 1].items() if d not in covered]

    if sel.instance_id.duplicated().any():
        errors.append(f"tasks in several clusters: {sorted(sel.instance_id[sel.instance_id.duplicated()])}")
    for grp, g in sel.groupby("same_pr_group"):  # one task per PR
        if len(g) > 1:
            errors.append(f"same-PR group {grp} has several selected tasks: {list(g.instance_id)}")
    ps = cand.problem_statement.str.strip()
    for a, b in itertools.combinations(sel.instance_id, 2):
        if ps[a] == ps[b]:
            errors.append(f"{a} / {b}: identical problem statement")

    if errors:
        sys.exit("selection check failed:\n  " + "\n  ".join(errors))

    sel.to_csv(out / "clusters.csv", index=False)
    print(f"wrote {out / 'clusters.csv'}: {len(sel)} tasks,", sel.groupby("cluster").size().to_dict(),
          f"{sel.targets.str.split(';').str.len().sum()} forward targets,",
          f"{len(cand) - len(sel)} of {len(cand)} candidates not selected")


if __name__ == "__main__":
    main(*sys.argv[1:3])
