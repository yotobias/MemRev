import json
from pathlib import Path
import threading
import urllib.error
import urllib.request

from http.server import ThreadingHTTPServer
import pytest

from memrev.evaluation import export_evaluation, import_evaluation
from memrev.provenance import prepare_acquisition
from memrev.review_app import make_handler


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "pilot-a/fixtures/test"
REVIEWER = {"id": "test-reviewer", "type": "human", "independent": False, "note": "Synthetic test-only evaluation."}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def review(tmp_path):
    package = tmp_path / "acquisition"
    prepare_acquisition(
        FIXTURES / "full_trajectory_example.traj.json",
        FIXTURES / "gpt-6-high_test_lessons_102526.json",
        FIXTURES / "gpt-6-high_test_lessons_102526.metadata.json", package,
    )
    form = tmp_path / "evaluation.json"
    export_evaluation(package, form, REVIEWER)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(package, form))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield package, form, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def get(url):
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read())


def post(url, body):
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def completed_evaluations(form):
    lessons, assumptions = dict(), dict()
    for lesson in form["lessons"]:
        lessons[lesson["lesson_id"]] = {"outcome": "usable_as_extracted", "issue_codes": [],
                                        "reason": "Advice matches the trajectory.", "reviewer_evidence_message_indices": []}
        for assumption in lesson["assumptions"]:
            rubric = {key: "yes" for key in assumption["evaluation"]["rubric"]}
            rubric["scope_sufficient"] = "no"
            assumptions[assumption["assumption_id"]] = {
                "outcome": "needs_repair", "issue_codes": ["dimensional_scope_unclear"],
                "reason": "Scope omits the dimensional limits.", "reviewer_evidence_message_indices": [3],
                "rubric": rubric}
    return lessons, assumptions


def test_session_shows_every_message_and_the_pending_form(review):
    package, form, url = review
    session = get(url + "/api/session")
    assert session["form"] == read(form)
    assert [message["index"] for message in session["messages"]] == list(range(78))
    assert "Message 25" not in session["messages"][25]["text"]
    assert session["messages"][25]["role"] == "tool"


def test_saved_form_imports_and_keeps_every_original(review, tmp_path):
    package, form, url = review
    original = read(form)
    check = get(url + "/api/check")
    assert check["ok"] is False and "pending" in check["error"]

    lessons, assumptions = completed_evaluations(original)
    status, result = post(url + "/api/save", {"lessons": lessons, "assumptions": assumptions})
    assert status == 200 and result == {"saved": True}

    saved = read(form)
    for before, after in zip(original["lessons"], saved["lessons"]):
        assert after["original_advice"] == before["original_advice"]
        for assumption_before, assumption_after in zip(before["assumptions"], after["assumptions"]):
            assert assumption_after["original"] == assumption_before["original"]
    assert {key: value for key, value in saved.items() if key != "lessons"} == {
        key: value for key, value in original.items() if key != "lessons"}

    check = get(url + "/api/check")
    assert check["ok"] is True
    assert check["summary"]["assumption_outcomes"]["needs_repair"] == 17

    summary = import_evaluation(package, form, tmp_path / "imported")
    assert summary["original_assumptions_evaluated"] == 17
    assert summary["lesson_outcomes"]["usable_as_extracted"] == 5


def test_save_rejects_unknown_ids_and_extra_fields_without_writing(review):
    package, form, url = review
    before = form.read_bytes()
    lessons, assumptions = completed_evaluations(read(form))

    status, result = post(url + "/api/save", {"lessons": {"not-a-lesson": next(iter(lessons.values()))}})
    assert status == 400 and "unknown IDs" in result["error"]

    first_id = next(iter(assumptions))
    tampered = dict(assumptions[first_id], original={"statement": "rewritten"})
    status, result = post(url + "/api/save", {"assumptions": {first_id: tampered}})
    assert status == 400 and "expected exactly the fields" in result["error"]
    assert form.read_bytes() == before
