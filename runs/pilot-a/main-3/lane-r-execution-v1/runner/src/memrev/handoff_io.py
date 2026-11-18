"""Small file helpers shared by the offline handoff stages."""

import json
from pathlib import Path
import tempfile

from memrev.provenance import _json_bytes, _sha256
from memrev.trajectory import parse_extraction


def canonical_hash(value):
    return _sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8"))


def read_json(path):
    return parse_extraction(Path(path).read_text(encoding="utf-8"))


def exact_rows(rows, identifiers, path):
    if not isinstance(rows, list):
        raise ValueError(f"{path}: expected a list")
    indexed = dict()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("assumption_id"), str):
            raise ValueError(f"{path}: missing assumption_id")
        identifier = row["assumption_id"]
        if identifier in indexed:
            raise ValueError(f"{path}: duplicate assumption_id")
        indexed[identifier] = row
    if set(indexed) != set(identifiers):
        raise ValueError(f"{path}: must cover exactly the original assumption IDs")
    return indexed


def check_version(value, field):
    if type(value.get(field)) is not int or value[field] != 1:
        raise ValueError(f"{field}: expected integer 1")


def write_bundle(output_dir, files, identity):
    """Stage a complete bundle; never overwrite a different existing artifact."""
    output = Path(output_dir).resolve()
    files = dict(files)
    manifest = {"bundle_version": 1, **identity,
                "artifacts": {name: _sha256(content) for name, content in sorted(files.items())}}
    files["manifest.json"] = _json_bytes(manifest)
    if output.exists():
        for relative, expected in files.items():
            target = output / relative
            if not target.is_file() or target.read_bytes() != expected:
                raise FileExistsError(f"Refusing to overwrite changed artifact: {target}")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".handoff-", dir=output.parent) as temporary:
        staging = Path(temporary) / "bundle"
        staging.mkdir()
        for relative, content in files.items():
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        if output.exists():
            raise FileExistsError(f"Output appeared during preparation: {output}")
        staging.rename(output)


def load_bundle(path):
    """Check every listed file; hashes detect changes, not malicious re-signing."""
    root = Path(path).resolve()
    manifest = read_json(root / "manifest.json")
    if not isinstance(manifest, dict):
        raise ValueError("bundle: expected manifest object")
    check_version(manifest, "bundle_version")
    if not isinstance(manifest.get("artifacts"), dict):
        raise ValueError("bundle: expected artifact hashes")
    files = dict()
    for relative, expected in manifest["artifacts"].items():
        if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("bundle: unsafe artifact path")
        target = (root / relative).resolve()
        if not target.is_relative_to(root):
            raise ValueError("bundle: artifact escapes package")
        content = target.read_bytes()
        if _sha256(content) != expected:
            raise ValueError(f"bundle: changed artifact {relative}")
        files[relative] = content
    return manifest, files


def json_file(files, name):
    if name not in files:
        raise ValueError(f"bundle: missing {name}")
    return parse_extraction(files[name].decode("utf-8"))
