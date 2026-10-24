"""Write the frozen Pilot A task list and the same-PR groups.

    uv run --locked python -I pilot-a/scripts/build_clusters.py pilot-a/data pilot-a

Inputs: the SCB parquet files in the data dir (data_prep/inspect_scb.py) and SWE-bench Verified
from Hugging Face (edited files come from its `patch`).
Outputs: <data>/same_pr_groups.csv (all SCB tasks) and <out>/clusters.csv (base tasks only;
`related_ids` keeps the SCB links, which Pilot A does not run).
Fails loudly if the selection breaks a rule (CHANGES.md 2026-10-24).
"""
import itertools, pathlib, re, sys
import pandas as pd
from datasets import load_dataset

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # python -I leaves the script dir off the path
from naming import image_for

REPOS = {"django/django", "sympy/sympy", "scikit-learn/scikit-learn"}  # team decisions V11, V12
# Rule (CHANGES.md 2026-10-24): candidates = Verified base tasks with SCB related tasks; a candidate
# is selected iff it shares an edited file or sub-package of its module with another candidate.
CLUSTERS = {  # cluster: (code the cluster is defined by, instance ids)
    "D1": ("django/db/models/expressions.py", ["django__django-15161", "django__django-15382",
                                               "django__django-15930", "django__django-16082"]),
    "D2": ("django/db/models/sql/", ["django__django-10554", "django__django-11555", "django__django-14122"]),
    "D3": ("django/db/models/fields/", ["django__django-11400", "django__django-11999",
                                        "django__django-15629", "django__django-16493"]),
    "D4": ("django/db/models/base.py", ["django__django-12209", "django__django-13964"]),
    "S1": ("sympy/printing/pycode.py", ["sympy__sympy-14976", "sympy__sympy-16766", "sympy__sympy-22914"]),
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

    ver = load_dataset("SWE-bench/SWE-bench_Verified", split="test").to_pandas()
    related = link.groupby("experience_instance_id").related_instance_id.agg(lambda s: ";".join(sorted(set(s))))
    cand = ver[ver.repo.isin(REPOS) & ver.instance_id.isin(related.index)].set_index("instance_id")
    edited = cand.patch.map(lambda p: set(re.findall(r"^diff --git a/(\S+)", p, re.M)))
    by_id = tasks.set_index("instance_id")

    rows, errors = [], []
    for cl, (code, ids) in CLUSTERS.items():
        hits = {i for i in cand.index if any(f.startswith(code) for f in edited[i])}
        for iid in ids:
            if iid not in cand.index:
                errors.append(f"{iid}: not a candidate (Verified, {sorted(REPOS)}, with related tasks)"); continue
            if iid not in hits:
                errors.append(f"{iid}: edits nothing under {code} (edits {sorted(edited[iid])})")
            rows.append(dict(instance_id=iid, cluster=cl, kind="experience", image=image_for(iid, "experience"),
                             same_text=False, same_pr_group=by_id.at[iid, "same_pr_group"], role="cluster",
                             related_ids=related[iid]))
        if hits - set(ids):  # the rule selects every candidate in the cluster's code
            errors.append(f"{cl}: candidates editing {code} left out: {sorted(hits - set(ids))}")
    sel = pd.DataFrame(rows)

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
          f"{sel.related_ids.str.split(';').str.len().sum()} related tasks linked (not run)")


if __name__ == "__main__":
    main(*sys.argv[1:3])
