"""Write the frozen Pilot A task list and the same-PR groups.

    uv run python -I pilot-a/scripts/build_clusters.py pilot-a/data pilot-a

Inputs (in data dir): the SCB parquet files (pilot-a/pilot-a/scripts/data_prep/inspect_scb.py) and
lite_task_file_overlap.csv (pilot-a/pilot-a/scripts/data_prep/clusters.py).
Outputs: <data>/same_pr_groups.csv (all 399 Lite tasks) and <out>/clusters.csv.
Fails loudly if the selection breaks any rule of pilot-a/plan/Kickoff.md Section 5.
"""
import itertools, pathlib, re, sys
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # python -I leaves the script dir off the path
from naming import image_for

# pilot-a/plan/Kickoff.md Section 5. Short repo name -> full id prefix.
PREFIX = {"sklearn": "scikit-learn__scikit-learn", "matplotlib": "matplotlib__matplotlib",
          "sympy": "sympy__sympy", "requests": "psf__requests", "django": "django__django"}
CLUSTERS = {  # cluster: (repo, files the cluster is defined by, experience ids, related ids)
    "K1": ("sklearn", ["sklearn/utils/validation.py"], [10949], [12622, 15093, 25637]),
    "M1": ("matplotlib", ["lib/matplotlib/widgets.py"], [22711], [22482, 22686]),
    "S1": ("sympy", ["sympy/sets/sets.py", "sympy/sets/fancysets.py"], [16988], [16342, 16946]),
    "R1": ("requests", ["requests/models.py", "requests/utils.py"], [2148, 3362], [3359]),
    "D1": ("django", ["django/db/models/query_utils.py", "django/db/models/sql/query.py"],
           [14016, 14017, 16910], [21204, 34570, 35356]),
}
SAME_TEXT = [("matplotlib__matplotlib-22686", "matplotlib__matplotlib-22711"),
             ("psf__requests-3359", "psf__requests-3362")]


def same_pr_groups(data):
    """Union-find over Lite tasks: same PR URL or byte-identical gold patch."""
    exp = pd.read_parquet(data / "SWEContextBench_Lite_Experience.parquet")
    rel = pd.read_parquet(data / "SWEContextBench_Related_Lite.parquet")
    link = pd.read_parquet(data / "SWEContextBench_Relationship.parquet")
    tasks = pd.concat([exp.assign(kind="experience"), rel.assign(kind="related")])
    tasks = tasks[["instance_id", "repo", "kind", "patch", "problem_statement"]].drop_duplicates("instance_id")

    # A task can carry several PRs (django-28147 is linked to 11383 and 11587); it then
    # joins the group of each, which can only merge groups, never split them.
    # Some "PR" URLs are /issues/ links (sklearn-13241); GitHub issues and PRs share one
    # number sequence per repo, so issues/N -> pull/N is lossless.
    pr = {}
    for a, b in [("related_instance_id", "related_pr_url"), ("experience_instance_id", "experience_pr_url")]:
        for iid, url in link[[a, b]].drop_duplicates().itertuples(index=False):
            pr.setdefault(iid, set()).add(re.sub(r"/issues/(\d+)$", r"/pull/\1", url))
    for t in tasks.itertuples():  # SWE-bench convention: experience id number = PR number
        if t.kind == "experience":
            own = f"https://github.com/{t.repo}/pull/{t.instance_id.rsplit('-', 1)[1]}"
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
    return tasks.drop(columns="root")


def main(data, out):
    data, out = pathlib.Path(data), pathlib.Path(out)
    tasks = same_pr_groups(data)
    tasks.sort_values(["same_pr_group", "instance_id"])[
        ["same_pr_group", "group_size", "instance_id", "kind", "pr_url"]
    ].to_csv(data / "same_pr_groups.csv", index=False)

    overlap = pd.read_csv(data / "lite_task_file_overlap.csv").set_index("instance_id")
    by_id = tasks.set_index("instance_id")
    rows, errors = [], []
    for cl, (short, files, exp_ids, rel_ids) in CLUSTERS.items():
        for kind, nums in [("experience", exp_ids), ("related", rel_ids)]:
            for n in nums:
                iid = f"{PREFIX[short]}-{n}"
                if iid not in overlap.index:
                    errors.append(f"{iid}: not a Lite task"); continue
                if overlap.at[iid, "kind"] != kind:
                    errors.append(f"{iid}: plan says {kind}, overlap csv says {overlap.at[iid, 'kind']}")
                edited = set(str(overlap.at[iid, "files"]).split(";"))
                if not edited & set(files):
                    errors.append(f"{iid}: edits none of {files} (edits {sorted(edited)})")
                rows.append(dict(instance_id=iid, cluster=cl, kind=kind, image=image_for(iid, kind),
                                 same_text=False, same_pr_group=by_id.at[iid, "same_pr_group"],
                                 role="cluster"))
    sel = pd.DataFrame(rows)

    # Same-PR rule: at most one selected task per group.
    for grp, g in sel.groupby("same_pr_group"):
        if len(g) > 1:
            errors.append(f"same-PR group {grp} has several selected tasks: {list(g.instance_id)}")

    # same_text: exactly the two listed pairs share issue text.
    ps = by_id.problem_statement.str.strip()
    for a, b in itertools.combinations(sel.instance_id, 2):
        same = ps[a] == ps[b]
        listed = (a, b) in SAME_TEXT or (b, a) in SAME_TEXT
        if same != listed:
            errors.append(f"{a} / {b}: identical text={same}, listed same_text={listed}")
    sel.loc[sel.instance_id.isin([i for p in SAME_TEXT for i in p]), "same_text"] = True

    if errors:
        sys.exit("selection check failed:\n  " + "\n  ".join(errors))

    sel.to_csv(out / "clusters.csv", index=False)
    print(f"wrote {out / 'clusters.csv'}: {len(sel)} tasks,",
          sel.groupby("cluster").size().to_dict(), sel.kind.value_counts().to_dict())
    print("\nsame-PR siblings left out of the selection:")
    for t in sel.itertuples():
        sib = tasks[(tasks.same_pr_group == t.same_pr_group) & (tasks.instance_id != t.instance_id)]
        if len(sib):
            print(f"  {t.instance_id:32} {t.same_pr_group:28} drops {', '.join(sib.instance_id)}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
