"""SWE-bench Verified instance metadata (trimmed JSONL, see docs/research/swe-bench-verified.md)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_META = Path(__file__).resolve().parents[2] / "data" / "swe-bench-verified-meta.jsonl"


@dataclass(frozen=True)
class Instance:
    instance_id: str
    repository: str
    version: str
    base_commit: str


def load_instances(path: Path, repository: str) -> list[Instance]:
    """All instances of `repository` in the metadata file, in file order."""
    instances = []
    with path.open() as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            if row["repo"] == repository:
                instances.append(
                    Instance(row["instance_id"], row["repo"], str(row["version"]), row["base_commit"])
                )
    return instances
