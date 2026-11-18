# Frozen Lane R execution handoff

Read CONTRACT.md and work_order.json. No checks have been executed by this bundle. Use validity.pending.json as the starting return and fill receipt.template.json only after a real check.

From this extracted directory, use your existing locked environment and `export PYTHONPATH="$PWD/runner/src"`, or install dependencies from runner/ with `uv sync --locked`. Then run `python -m memrev.lane_r validate --bundle . --return-file validity.pending.json`. The first validation succeeds with scheduled work pending. The copied source is a frozen local snapshot, not a claim that the branch has been published.

Keep working returns and private evidence outside this directory. Send only the return JSON and validation summary to N; never send the private gold/check-output evidence store. The source trajectory and review limitations remain applicable; new extractions require new collection IDs.
