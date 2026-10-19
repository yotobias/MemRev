"""The hand-written django fixture bank that ships with the repo."""

import json
import os
from pathlib import Path

import pytest

from memrev.store import RunStore

FIXTURE_BANK = Path(__file__).resolve().parents[1] / "fixtures" / "django" / "lessons.jsonl"
SCHEMA_FIELDS = {"lesson_id", "lesson_text", "task_id", "repository", "source_revision", "trajectory_pointer"}


def test_fixture_bank_has_at_least_ten_django_lessons_in_the_schema():
    records = [json.loads(line) for line in FIXTURE_BANK.read_text().splitlines() if line.strip()]

    assert len(records) >= 10
    assert all(set(r) == SCHEMA_FIELDS for r in records)
    assert {r["repository"] for r in records} == {"django/django"}
    assert len({r["lesson_id"] for r in records}) == len(records)


@pytest.mark.skipif(
    not os.environ.get("MEMREV_DJANGO_REPO"),
    reason="set MEMREV_DJANGO_REPO to a local django clone to check the fixture SHAs",
)
def test_fixture_bank_imports_cleanly_against_a_django_clone(cli, run_dir):
    django = os.environ["MEMREV_DJANGO_REPO"]
    assert cli("--run", str(run_dir), "init", "--repo", f"django/django={django}").exit_code == 0

    result = cli("--run", str(run_dir), "import", str(FIXTURE_BANK))

    assert ", 0 rejected" in result.out, result.err
    store = RunStore.open(run_dir)
    assert len(store.lessons()) >= 10
    assert store.exclusions() == []
