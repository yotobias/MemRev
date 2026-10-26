import json
import hashlib
from pathlib import Path
import subprocess

import pytest

from memrev.provenance import prepare_acquisition
from memrev.trajectory import build_extract_prompt, load_trajectory


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "pilot-a/fixtures/test"


@pytest.fixture
def inputs(tmp_path):
    paths = dict()
    for name, filename in [
        ("trajectory_path", "full_trajectory_example.traj.json"),
        ("extraction_path", "gpt-6-high_test_lessons_102526.json"),
        ("metadata_path", "gpt-6-high_test_lessons_102526.metadata.json"),
    ]:
        path = tmp_path / filename
        path.write_bytes((FIXTURES / filename).read_bytes())
        paths[name] = path
    return paths


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_prepare_real_response_preserves_inputs_and_marks_review_pending(inputs, tmp_path):
    original = {key: path.read_bytes() for key, path in inputs.items()}
    output = tmp_path / "prepared"
    record = prepare_acquisition(**inputs, output_dir=output)
    assert record == load(output / "record.json")
    assert len(record["lessons"]) == 5
    assert sum(len(l["assumptions"]) for l in record["lessons"]) == 17
    assert record["metadata"]["source_revision"] is None
    assert record["metadata"]["extractor"]["cost_usd"] is None
    assert record["artifacts"]["prompt"] is None
    assert "source_revision" in record["unknown_metadata"]
    assert "prompt" in record["unknown_metadata"]
    for key, before in original.items():
        assert inputs[key].read_bytes() == before
        artifact = record["artifacts"][key.removesuffix("_path")]
        assert (output / artifact["path"]).read_bytes() == before
        assert artifact["sha256"] == hashlib.sha256(before).hexdigest()
    assert not (output / "review.json").exists()
    ids = []
    for index, lesson in enumerate(record["lessons"]):
        assert lesson["lesson_id"] == f"{record['acquisition_id']}/lesson/{index}"
        for position, assumption in enumerate(lesson["assumptions"]):
            ids.append(assumption["assumption_id"])
            assert assumption["assumption_id"] == f"{lesson['lesson_id']}/assumption/{position}"
    assert len(ids) == len(set(ids)) == 17


def test_reprepare_does_not_overwrite_human_review(inputs, tmp_path):
    output = tmp_path / "prepared"
    record = prepare_acquisition(**inputs, output_dir=output)
    saved = b'{"reason": "Human review in progress; keep this."}\n'
    (output / "evaluation.mine.json").write_bytes(saved)
    (output / "review.json").write_bytes(saved)  # Preserve older packages too.
    assert prepare_acquisition(**inputs, output_dir=output) == record
    assert (output / "evaluation.mine.json").read_bytes() == saved
    assert (output / "review.json").read_bytes() == saved


def test_ids_survive_relocation_and_metadata_correction(inputs, tmp_path):
    first = prepare_acquisition(**inputs, output_dir=tmp_path / "first")
    relocated = tmp_path / "relocated"
    relocated.mkdir()
    moved = dict()
    for key, path in inputs.items():
        target = relocated / path.name
        target.write_bytes(path.read_bytes())
        moved[key] = target
    metadata = load(moved["metadata_path"])
    metadata["notes"] = "Corrected description."
    moved["metadata_path"].write_text(json.dumps(metadata), encoding="utf-8")
    second = prepare_acquisition(**moved, output_dir=tmp_path / "second")
    assert first["acquisition_id"] == second["acquisition_id"]
    assert first["lessons"] == second["lessons"]


@pytest.mark.parametrize("change", ["run_id", "trajectory", "response"])
def test_changed_run_or_raw_bytes_create_distinct_ids(inputs, tmp_path, change):
    first = prepare_acquisition(**inputs, output_dir=tmp_path / "first")
    if change == "run_id":
        path = inputs["metadata_path"]
        metadata = load(path)
        metadata["extraction_run_id"] += "-second"
        path.write_text(json.dumps(metadata), encoding="utf-8")
    else:
        path = inputs["trajectory_path" if change == "trajectory" else "extraction_path"]
        path.write_bytes(path.read_bytes() + b"\n")
    second = prepare_acquisition(**inputs, output_dir=tmp_path / "second")
    assert first["acquisition_id"] != second["acquisition_id"]
    assert first["lessons"][0]["lesson_id"] != second["lessons"][0]["lesson_id"]
    with pytest.raises(FileExistsError):
        prepare_acquisition(**inputs, output_dir=tmp_path / "first")
    assert load(tmp_path / "first/record.json") == first


@pytest.mark.parametrize("change", ["wrong_task", "bad_sha", "boolean_tokens", "negative_cost", "production_incomplete"])
def test_bad_metadata_fails_before_writing_output(inputs, tmp_path, change):
    metadata = load(inputs["metadata_path"])
    if change == "wrong_task":
        metadata["task_id"] = "different-task"
    elif change == "bad_sha":
        metadata["source_revision"] = "unknown"
    elif change == "boolean_tokens":
        metadata["extractor"]["input_tokens"] = True
    elif change == "negative_cost":
        metadata["extractor"]["cost_usd"] = -1
    else:
        metadata["purpose"] = "pilot_a"
    inputs["metadata_path"].write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError):
        prepare_acquisition(**inputs, output_dir=tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()


def test_exact_prompt_is_snapshotted_and_mismatched_transcript_rejected(inputs, tmp_path):
    trajectory = load_trajectory(inputs["trajectory_path"])
    prompt = tmp_path / "submitted_prompt.txt"
    prompt.write_text(build_extract_prompt(trajectory, ROOT / "pilot-a/extract_prompt.md"), encoding="utf-8")
    record = prepare_acquisition(**inputs, prompt_path=prompt, output_dir=tmp_path / "valid")
    assert (tmp_path / "valid/inputs/prompt.txt").read_bytes() == prompt.read_bytes()
    assert "prompt" not in record["unknown_metadata"]
    prompt.write_text("A prompt for a different task", encoding="utf-8")
    with pytest.raises(ValueError, match="prompt"):
        prepare_acquisition(**inputs, prompt_path=prompt, output_dir=tmp_path / "invalid")


def test_modified_frozen_snapshot_prevents_reuse(inputs, tmp_path):
    output = tmp_path / "prepared"
    prepare_acquisition(**inputs, output_dir=output)
    (output / "inputs/extraction.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError, match="extraction.json"):
        prepare_acquisition(**inputs, output_dir=output)


def test_package_can_be_written_to_ignored_directory_inside_checkout(inputs, tmp_path):
    checkout = tmp_path / "checkout"
    subprocess.run(["git", "init", "--quiet", str(checkout)], check=True)
    (checkout / ".gitignore").write_text("runs/\n", encoding="utf-8")
    output = checkout / "runs/acquisitions/example"
    record = prepare_acquisition(**inputs, output_dir=output)
    assert load(output / "record.json") == record
    subprocess.run(["git", "-C", str(checkout), "check-ignore", "--quiet", "runs/acquisitions/example/record.json"], check=True)


def test_complete_production_metadata_can_be_prepared_without_claiming_validity(inputs, tmp_path):
    metadata = load(inputs["metadata_path"])
    metadata.update(purpose="pilot_a", agent_run_id="test-agent-run", repository="astropy/astropy", source_revision="a" * 40)
    metadata["extractor"].update(provider="test-provider", model_id="test-model", cost_usd=0)
    inputs["metadata_path"].write_text(json.dumps(metadata), encoding="utf-8")
    prompt = tmp_path / "submitted_prompt.txt"
    prompt.write_text(build_extract_prompt(load_trajectory(inputs["trajectory_path"]), ROOT / "pilot-a/extract_prompt.md"), encoding="utf-8")
    record = prepare_acquisition(**inputs, prompt_path=prompt, output_dir=tmp_path / "prepared")
    assert record["metadata"]["extractor"]["cost_usd"] == 0
    assert "extractor.cost_usd" not in record["unknown_metadata"]
    assert "validity" not in record
    # Completeness does not establish selected-task eligibility or SHA existence.
