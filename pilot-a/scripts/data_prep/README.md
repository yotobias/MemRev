# Data preparation scripts (SWE-ContextBench Lite)

Historical exploration/reproducibility scripts. Current V47 selection uses `../build_clusters.py`; the obsolete Lite `clusters.py` was removed; see `../README.md`. These scripts may read gold-bearing benchmark data and are for Lane R, not blinded Lane N review.

Run from the project root; all need network. Output directory is `pilot-a/data`.

    uv run --no-project --with pandas --with pyarrow python -I pilot-a/scripts/data_prep/inspect_scb.py pilot-a/data

- `inspect_scb.py` downloads the five SWE-ContextBench parquet files from Hugging Face into
  `pilot-a/data/` and joins related tasks to experience tasks (`lite_pairs.csv`).

The two scripts below are not needed for Pilot A. They prepare the revision-pair analysis for the
pilot that follows (which claims change across revisions) and are kept here so the CSVs in
`pilot-a/data/revision_pairs/` are reproducible:

    uv run --no-project --with pandas --with pyarrow python -I pilot-a/scripts/data_prep/ancestry.py  pilot-a/data pilot-a/repos
    uv run --no-project --with pandas --with pyarrow python -I pilot-a/scripts/data_prep/ancestry2.py pilot-a/data pilot-a/repos

`ancestry.py` makes blob-less clones (`--filter=blob:none`) of the 12 repositories. On Windows the
checkout step fails for some repositories with "Filename too long"; the trees are still complete
and the statistics are correct, but prefer running inside WSL.
