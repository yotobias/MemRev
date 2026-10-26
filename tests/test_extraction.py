import copy
from pathlib import Path

import pytest

from memrev.trajectory import load_extraction, load_trajectory, validate_extraction


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "pilot-a/fixtures/test"


@pytest.fixture
def trajectory():
    return load_trajectory(FIXTURES / "full_trajectory_example.traj.json")


@pytest.fixture
def extraction():
    return load_extraction(FIXTURES / "extraction_v2.json")


def test_curated_response_validates_without_changing_input(extraction, trajectory):
    original = copy.deepcopy(extraction)
    original_trajectory = copy.deepcopy(trajectory)
    assert validate_extraction(extraction, trajectory) is extraction
    assert extraction == original
    assert trajectory == original_trajectory


def test_empty_lessons_are_valid(trajectory):
    extraction = {"schema_version": 2, "lessons": []}
    assert validate_extraction(extraction, trajectory) is extraction


def test_missing_evidence_is_retained_without_validity_label(extraction, trajectory):
    assumption = extraction["lessons"][0]["assumptions"][0]
    assumption["evidence_basis"] = "no_evidence"
    assumption["evidence_message_indices"] = []
    assumption["symbol"] = None
    assumption["file"] = None
    extraction["lessons"][0]["from_failed_step"] = None
    assert validate_extraction(extraction, trajectory) is extraction
    assert "validity" not in assumption


@pytest.mark.parametrize("basis", ["execution_observation", "code_observation", "unverified_assertion"])
def test_cited_evidence_categories_are_accepted(extraction, trajectory, basis):
    extraction["lessons"][0]["assumptions"][0]["evidence_basis"] = basis
    assert validate_extraction(extraction, trajectory) is extraction


@pytest.mark.parametrize("field,value", [
    ("statement", " "),
    ("workspace_context", None),
    ("symbol", ""),
    ("file", []),
    ("predicate", "matches"),
    ("predicate", []),
    ("kind", "signature"),
    ("scope", "legacy free-text scope"),
    ("scope", {"inputs": None, "config": None}),
    ("scope", {"inputs": [], "config": None, "env": None}),
    ("evidence_basis", "unsupported"),
    ("evidence_message_indices", []),
    ("evidence_message_indices", [True]),
    ("evidence_message_indices", [-1]),
    ("evidence_message_indices", [78]),
    ("evidence_message_indices", [25.0]),
    ("evidence_message_indices", ["25"]),
    ("evidence_message_indices", [25, 25]),
])
def test_invalid_assumptions_report_field_path(extraction, trajectory, field, value):
    extraction["lessons"][0]["assumptions"][0][field] = value
    with pytest.raises(ValueError) as error:
        validate_extraction(extraction, trajectory)
    assert f"lessons[0].assumptions[0].{field}" in str(error.value)


def test_missing_evidence_must_not_have_citations(extraction, trajectory):
    extraction["lessons"][0]["assumptions"][0]["evidence_basis"] = "no_evidence"
    with pytest.raises(ValueError, match="evidence_message_indices"):
        validate_extraction(extraction, trajectory)


@pytest.mark.parametrize("field,value", [("advice", ""), ("from_failed_step", 0), ("assumptions", {})])
def test_invalid_lesson_fields(extraction, trajectory, field, value):
    extraction["lessons"][0][field] = value
    with pytest.raises(ValueError) as error:
        validate_extraction(extraction, trajectory)
    assert f"lessons[0].{field}" in str(error.value)


def test_missing_and_unexpected_fields_are_rejected(extraction, trajectory):
    assumption = extraction["lessons"][0]["assumptions"][0]
    del assumption["symbol"]
    with pytest.raises(ValueError, match="symbol"):
        validate_extraction(extraction, trajectory)
    assumption["symbol"] = None
    assumption["validity"] = "repo_history"
    with pytest.raises(ValueError, match="validity"):
        validate_extraction(extraction, trajectory)


@pytest.mark.parametrize("value", [[], {"lessons": []}, {"schema_version": True, "lessons": []}, {"schema_version": 1, "lessons": []}, {"schema_version": 2, "lessons": {}}])
def test_invalid_root_and_old_versions_are_rejected(value, trajectory):
    with pytest.raises(ValueError):
        validate_extraction(value, trajectory)


def test_legacy_response_loads_but_requires_explicit_migration(trajectory):
    extraction = {"lessons": [{"advice": "Legacy response", "assumptions": []}]}
    with pytest.raises(ValueError, match="schema_version"):
        validate_extraction(extraction, trajectory)


@pytest.mark.parametrize("text", ['```json\n{}\n```', '{"lessons": [], "lessons": []}', '{"value": NaN}', '{"value": Infinity}', '{"value": -Infinity}'])
def test_loader_rejects_invalid_or_ambiguous_json(tmp_path, text):
    path = tmp_path / "response.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        load_extraction(path)


def test_loader_preserves_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_extraction(tmp_path / "missing.json")


def test_invalid_trajectory_is_reported(extraction):
    with pytest.raises(ValueError, match="trajectory.messages"):
        validate_extraction(extraction, {"messages": None})
