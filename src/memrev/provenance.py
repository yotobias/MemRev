"""Preserve raw extraction inputs and identify occurrences for later evaluation."""

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile

from memrev.trajectory import format_transcript, parse_extraction, validate_extraction


def _json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _fields(value, fields, path):
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected an object")
    missing = set(fields) - set(value)
    extra = set(value) - set(fields)
    if missing or extra:
        raise ValueError(f"{path}: missing fields {sorted(missing)}, unexpected fields {sorted(extra)}")


def _text(value, path, nullable=True):
    if nullable and value is None:
        return
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: expected a nonempty string" + (" or null" if nullable else ""))


def _validate_metadata(metadata, trajectory, has_prompt):
    _fields(metadata, [
        "extraction_run_id", "purpose", "agent_run_id", "task_id", "repository",
        "source_revision", "extractor", "notes",
    ], "metadata")
    _text(metadata["extraction_run_id"], "metadata.extraction_run_id", nullable=False)
    if metadata["purpose"] not in ["development", "pilot_a"]:
        raise ValueError("metadata.purpose: expected development or pilot_a")
    for field in ["agent_run_id", "task_id", "repository", "source_revision", "notes"]:
        _text(metadata[field], f"metadata.{field}")
    repository = metadata["repository"]
    if repository is not None and not re.fullmatch(r"[^/\s]+/[^/\s]+", repository):
        raise ValueError("metadata.repository: expected owner/repository")
    revision = metadata["source_revision"]
    if revision is not None and not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", revision):
        raise ValueError("metadata.source_revision: expected a full Git SHA or null")
    task = trajectory.get("instance_id")
    if task is not None and metadata["task_id"] is not None and metadata["task_id"] != task:
        raise ValueError("metadata.task_id: does not match trajectory.instance_id")

    extractor = metadata["extractor"]
    _fields(extractor, [
        "method", "provider", "model_id", "reported_label", "input_tokens", "output_tokens", "cost_usd",
    ], "metadata.extractor")
    if extractor["method"] not in ["manual_browser", "api"]:
        raise ValueError("metadata.extractor.method: expected manual_browser or api")
    for field in ["provider", "model_id", "reported_label"]:
        _text(extractor[field], f"metadata.extractor.{field}")
    for field in ["input_tokens", "output_tokens"]:
        value = extractor[field]
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError(f"metadata.extractor.{field}: expected a nonnegative integer or null")
    cost = extractor["cost_usd"]
    if cost is not None and (type(cost) not in [int, float] or cost < 0 or not math.isfinite(cost)):
        raise ValueError("metadata.extractor.cost_usd: expected a finite nonnegative number or null")

    unknown = [field for field in ["agent_run_id", "task_id", "repository", "source_revision"] if metadata[field] is None]
    unknown.extend(f"extractor.{field}" for field in [
        "provider", "model_id", "input_tokens", "output_tokens", "cost_usd",
    ] if extractor[field] is None)
    if not has_prompt:
        unknown.append("prompt")
    required = {"agent_run_id", "task_id", "repository", "source_revision", "extractor.provider", "extractor.model_id", "prompt"}
    missing = sorted(required.intersection(unknown))
    if metadata["purpose"] == "pilot_a" and missing:
        raise ValueError(f"Production provenance incomplete: {', '.join(missing)}")
    return unknown


def _write_package(output_dir, frozen_files):
    output = Path(output_dir).resolve()
    if output.exists():
        for relative, expected in frozen_files.items():
            path = output / relative
            if not path.is_file() or path.read_bytes() != expected:
                raise FileExistsError(f"Refusing to overwrite changed package artifact: {path}")
        return

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".prepare-", dir=output.parent) as temporary:
        staging = Path(temporary) / "package"
        staging.mkdir()
        for relative, data in frozen_files.items():
            path = staging / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        if output.exists():
            raise FileExistsError(f"Output appeared while preparing package: {output}")
        staging.rename(output)


def prepare_acquisition(trajectory_path, extraction_path, metadata_path, output_dir, prompt_path=None):
    """Validate and snapshot one extraction; reruns preserve an existing review."""
    paths = {"trajectory": trajectory_path, "extraction": extraction_path, "metadata": metadata_path}
    if prompt_path is not None:
        paths["prompt"] = prompt_path
    snapshots = dict()
    artifacts = {"prompt": None}
    for name, supplied in paths.items():
        path = Path(supplied).resolve()
        content = path.read_bytes()
        relative = f"inputs/{name}.{'txt' if name == 'prompt' else 'json'}"
        snapshots[relative] = content
        artifacts[name] = {"path": relative, "original_path": str(path), "sha256": _sha256(content)}

    record = _build_record(snapshots, artifacts)
    snapshots["record.json"] = _json_bytes(record)
    _write_package(output_dir, snapshots)
    return record


def _build_record(snapshots, artifacts):
    data = {name: parse_extraction(snapshots[f"inputs/{name}.json"].decode("utf-8"))
            for name in ["trajectory", "extraction", "metadata"]}
    has_prompt = artifacts["prompt"] is not None

    trajectory = data["trajectory"]
    if isinstance(trajectory, list):
        trajectory = {"messages": trajectory}
    extraction = data["extraction"]
    validate_extraction(extraction, trajectory)
    metadata = data["metadata"]
    unknown = _validate_metadata(metadata, trajectory, has_prompt)
    if has_prompt:
        prompt = snapshots["inputs/prompt.txt"].decode("utf-8")
        expected = "<trajectory>\n" + format_transcript(trajectory) + "</trajectory>"
        if not prompt.endswith(expected):
            raise ValueError("prompt: does not end with the supplied trajectory in the expected format")

    identity = {
        "identity_version": 1,
        "extraction_run_id": metadata["extraction_run_id"],
        "trajectory_sha256": artifacts["trajectory"]["sha256"],
        "extraction_sha256": artifacts["extraction"]["sha256"],
    }
    identity_bytes = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    acquisition_id = "acq-" + _sha256(identity_bytes)
    lessons = copy.deepcopy(extraction["lessons"])
    for lesson_index, lesson in enumerate(lessons):
        lesson_id = f"{acquisition_id}/lesson/{lesson_index}"
        lesson["lesson_id"] = lesson_id
        lesson["raw_lesson_index"] = lesson_index
        for assumption_index, assumption in enumerate(lesson["assumptions"]):
            assumption["assumption_id"] = f"{lesson_id}/assumption/{assumption_index}"
            assumption["raw_assumption_index"] = assumption_index

    record = {
        "record_version": 1,
        "acquisition_id": acquisition_id,
        "identity": identity,
        "metadata": metadata,
        "artifacts": artifacts,
        "unknown_metadata": unknown,
        "extraction_schema_version": extraction["schema_version"],
        "message_count": len(trajectory["messages"]),
        "lessons": lessons,
    }
    return record


def load_acquisition(package_dir):
    """Verify snapshot hashes and reconstruct the record before trusting its IDs."""
    package = Path(package_dir)
    record = parse_extraction((package / "record.json").read_text(encoding="utf-8"))
    if not isinstance(record, dict) or not isinstance(record.get("artifacts"), dict):
        raise ValueError("record: expected an acquisition object with artifacts")
    artifacts = record["artifacts"]
    _fields(artifacts, ["trajectory", "extraction", "metadata", "prompt"], "record.artifacts")
    snapshots = dict()
    for name, artifact in artifacts.items():
        if name == "prompt" and artifact is None:
            continue
        _fields(artifact, ["path", "original_path", "sha256"], f"artifacts.{name}")
        relative = f"inputs/{name}.{'txt' if name == 'prompt' else 'json'}"
        if artifact["path"] != relative:
            raise ValueError(f"artifacts.{name}: unexpected snapshot path")
        _text(artifact["original_path"], f"artifacts.{name}.original_path", nullable=False)
        content = (package / relative).read_bytes()
        if _sha256(content) != artifact["sha256"]:
            raise ValueError(f"artifacts.{name}: snapshot hash mismatch")
        snapshots[relative] = content
    rebuilt = _build_record(snapshots, artifacts)
    # JSON comparison distinguishes booleans from integers, unlike Python equality.
    if json.dumps(record, sort_keys=True) != json.dumps(rebuilt, sort_keys=True):
        raise ValueError("record: does not match its acquisition snapshots")
    return rebuilt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trajectory", required=True, type=Path)
    parser.add_argument("--extraction", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--prompt", type=Path, help="Exact saved prompt used for this extraction, if known")
    args = parser.parse_args()
    try:
        record = prepare_acquisition(args.trajectory, args.extraction, args.metadata, args.output_dir, args.prompt)
    except (ValueError, OSError) as error:
        parser.exit(2, f"Cannot prepare extraction: {error}\n")
    count = sum(len(lesson["assumptions"]) for lesson in record["lessons"])
    print(f"Prepared {len(record['lessons'])} lessons and {count} assumptions in {args.output_dir.resolve()}")
    if record["unknown_metadata"]:
        print("Unknown metadata: " + ", ".join(record["unknown_metadata"]))
    print("Preparation does not establish source validity. Export an optional form with memrev.evaluation draft.")


if __name__ == "__main__":
    main()
