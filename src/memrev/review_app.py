"""Local browser app for filling an extraction evaluation form quickly.

The app edits only the evaluation fields of a form made by `memrev.evaluation draft`.
Originals, definitions and reviewer attribution are never sent back by the page, so a saved
form stays importable by `memrev.evaluation import` once every row is complete.
"""

import argparse
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import webbrowser

from memrev.evaluation import PROTOCOL, _evaluate
from memrev.provenance import _json_bytes, load_acquisition
from memrev.trajectory import format_message, load_trajectory, parse_extraction


PAGE = Path(__file__).with_name("review_app.html")
LESSON_EVALUATION_FIELDS = ["outcome", "issue_codes", "reason", "reviewer_evidence_message_indices"]
ASSUMPTION_EVALUATION_FIELDS = LESSON_EVALUATION_FIELDS + ["rubric"]


def _without_duplicate_output(message):
    extra = message.get("extra") if isinstance(message, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(extra, dict) or not isinstance(extra.get("raw_output"), str) or not isinstance(content, str):
        return message
    if extra["raw_output"].strip() not in content:
        return message
    shown = dict(message)
    shown["extra"] = {key: value for key, value in extra.items() if key != "raw_output"}
    return shown


def _message_view(message, message_index):
    text = format_message(_without_duplicate_output(message), message_index)
    header, _, body = text.partition("\n\n")
    content = message.get("content") if isinstance(message, dict) else None
    preview = content if isinstance(content, str) else ""
    return {"index": message_index, "role": message.get("role", "unknown"),
            "preview": " ".join(preview.split())[:160], "text": body.rstrip()}


def load_session(package_dir, form_path):
    """Verify the acquisition and return what the page needs to show one review."""
    record = load_acquisition(package_dir)
    form = parse_extraction(Path(form_path).read_text(encoding="utf-8"))
    if form.get("acquisition_id") != record["acquisition_id"]:
        raise ValueError("form: acquisition_id does not match the package")
    trajectory = load_trajectory(Path(package_dir) / record["artifacts"]["trajectory"]["path"])
    messages = [_message_view(message, index) for index, message in enumerate(trajectory["messages"])]
    if len(messages) != record["message_count"]:
        raise ValueError("trajectory: message count does not match the record")
    return {"form": form, "messages": messages, "metadata": record["metadata"],
            "assumption_outcome_definitions": PROTOCOL["assumption_outcome_definitions"]}


def _merged_evaluation(current, submitted, fields, path):
    if not isinstance(submitted, dict) or set(submitted) != set(fields):
        raise ValueError(f"{path}: expected exactly the fields {fields}")
    merged = copy.deepcopy(current)
    for field in fields:
        merged[field] = copy.deepcopy(submitted[field])
    if "rubric" in fields and set(merged["rubric"]) != set(current["rubric"]):
        raise ValueError(f"{path}: rubric criteria cannot change")
    return merged


def apply_evaluations(form, lesson_evaluations, assumption_evaluations):
    """Copy submitted judgments into the form by ID, leaving every other field untouched."""
    updated = copy.deepcopy(form)
    for lesson in updated["lessons"]:
        lesson_id = lesson["lesson_id"]
        if lesson_id in lesson_evaluations:
            lesson["evaluation"] = _merged_evaluation(
                lesson["evaluation"], lesson_evaluations[lesson_id], LESSON_EVALUATION_FIELDS, lesson_id)
        for assumption in lesson["assumptions"]:
            assumption_id = assumption["assumption_id"]
            if assumption_id in assumption_evaluations:
                assumption["evaluation"] = _merged_evaluation(
                    assumption["evaluation"], assumption_evaluations[assumption_id],
                    ASSUMPTION_EVALUATION_FIELDS, assumption_id)
    known_lessons = {lesson["lesson_id"] for lesson in updated["lessons"]}
    known_assumptions = {assumption["assumption_id"] for lesson in updated["lessons"]
                         for assumption in lesson["assumptions"]}
    unknown = (set(lesson_evaluations) - known_lessons) | (set(assumption_evaluations) - known_assumptions)
    if unknown:
        raise ValueError(f"unknown IDs: {sorted(unknown)}")
    return updated


def save_form(form_path, form):
    path = Path(form_path)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=".review-", delete=False) as stream:
        stream.write(_json_bytes(form))
        temporary = stream.name
    os.replace(temporary, path)


def check_form(package_dir, form):
    """Run the importer's own validation without writing anything."""
    pending = sum(1 for lesson in form["lessons"] for row in [lesson] + lesson["assumptions"]
                  if row["evaluation"]["outcome"] == "pending")
    if pending:
        return {"ok": False, "error": f"{pending} rows are still pending"}
    try:
        _, summary = _evaluate(load_acquisition(package_dir), form)
    except ValueError as error:
        return {"ok": False, "error": str(error)}
    return {"ok": True, "summary": summary}


def make_handler(package_dir, form_path):
    class ReviewHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def _send(self, status, body, content_type="application/json"):
            payload = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _current_form(self):
            return parse_extraction(Path(form_path).read_text(encoding="utf-8"))

        def do_GET(self):
            try:
                if self.path == "/":
                    self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
                elif self.path == "/api/session":
                    self._send(200, load_session(package_dir, form_path))
                elif self.path == "/api/check":
                    self._send(200, check_form(package_dir, self._current_form()))
                else:
                    self._send(404, {"error": "not found"})
            except (ValueError, OSError) as error:
                self._send(500, {"error": str(error)})

        def do_POST(self):
            if self.path != "/api/save":
                self._send(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                updated = apply_evaluations(self._current_form(), body.get("lessons", {}),
                                            body.get("assumptions", {}))
                save_form(form_path, updated)
                self._send(200, {"saved": True})
            except (ValueError, OSError, json.JSONDecodeError) as error:
                self._send(400, {"error": str(error)})

    return ReviewHandler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path, help="Acquisition package directory")
    parser.add_argument("--form", required=True, type=Path, help="Form from `memrev.evaluation draft`; edited in place")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    try:
        load_session(args.package, args.form)
    except (ValueError, OSError) as error:
        parser.exit(2, f"Cannot open review: {error}\n")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.package, args.form))
    address = f"http://127.0.0.1:{args.port}/"
    print(f"Reviewing {args.form.resolve()} at {address} (Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
