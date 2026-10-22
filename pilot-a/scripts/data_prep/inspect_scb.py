"""Download the SWE-ContextBench parquet files and summarise the Lite pairs."""
import sys, json, urllib.request, pathlib
import pandas as pd

out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
base = "https://huggingface.co/datasets/jiayuanz3/SWEContextBench/resolve/main/data/"
files = ["SWEContextBench_Relationship.parquet",
         "SWEContextBench_Lite_Experience.parquet",
         "SWEContextBench_Related_Lite.parquet",
         "SWEContextBench_Experience.parquet",
         "SWEContextBench_Related.parquet"]
for f in files:
    p = out / f
    if not p.exists():
        try:
            urllib.request.urlretrieve(base + f, p)
            print("downloaded", f, p.stat().st_size // 1024, "KB")
        except Exception as e:
            print("FAILED", f, e)

rel = pd.read_parquet(out / "SWEContextBench_Relationship.parquet")
print("\n== Relationship columns ==", list(rel.columns), "rows", len(rel))
print(rel.head(3).to_string())

exp = pd.read_parquet(out / "SWEContextBench_Lite_Experience.parquet")
rl = pd.read_parquet(out / "SWEContextBench_Related_Lite.parquet")
print("\n== Lite experience ==", len(exp), "rows; columns:", list(exp.columns))
print(exp["repo"].value_counts().to_string())
print("\n== Lite related ==", len(rl), "rows")
print(rl["repo"].value_counts().to_string())

# join pairs
pairs = rel.merge(rl[["instance_id", "base_commit", "created_at", "repo"]],
                  left_on="related_instance_id", right_on="instance_id", how="inner") \
           .merge(exp[["instance_id", "base_commit", "created_at"]],
                  left_on="experience_instance_id", right_on="instance_id",
                  how="inner", suffixes=("_rel", "_exp"))
print("\n== Lite pairs (related x experience) ==", len(pairs))
pairs["same_commit"] = pairs["base_commit_rel"] == pairs["base_commit_exp"]
pairs["rel_after_exp"] = pd.to_datetime(pairs["created_at_rel"]) > pd.to_datetime(pairs["created_at_exp"])
print("same base_commit:", int(pairs["same_commit"].sum()))
print("related created after experience:", int(pairs["rel_after_exp"].sum()))
print("\nper repo (pairs, distinct commits, related-later):")
g = pairs.groupby("repo").agg(pairs=("related_instance_id", "count"),
                              diff_commit=("same_commit", lambda s: int((~s).sum())),
                              later=("rel_after_exp", "sum"))
print(g.to_string())
print("\nrelated tasks with >1 experience task:",
      int((pairs.groupby("related_instance_id").size() > 1).sum()))
print("experience tasks reused by >1 related task:",
      int((pairs.groupby("experience_instance_id").size() > 1).sum()))
pairs.to_csv(out / "lite_pairs.csv", index=False)
print("\nsample pairs:")
print(pairs[["repo", "experience_instance_id", "related_instance_id", "same_commit", "rel_after_exp"]].head(12).to_string())
