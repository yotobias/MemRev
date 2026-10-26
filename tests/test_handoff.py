"""Synthetic judgments exercise the plumbing; none are human research results."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from memrev.evaluation import build_evaluation_draft
from memrev.handoff import build_handoff, export_regrouping, compare_regrouping
from memrev.handoff_io import canonical_hash
from memrev.provenance import prepare_acquisition
from memrev.trajectory import format_transcript
from memrev.validity import validity_label


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "pilot-a/fixtures/test"
ASSESSOR = {"id": "synthetic-fixture", "type": "ai", "independent": False,
            "note": "Invented test judgments only, not a review of real behavior."}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def acquisition(tmp_path):
    package = tmp_path / "acquisition"
    prepare_acquisition(FIXTURES / "full_trajectory_example.traj.json",
                        FIXTURES / "gpt-6-high_test_lessons_102526.json",
                        FIXTURES / "gpt-6-high_test_lessons_102526.metadata.json", package)
    return package


@pytest.fixture
def scenario(tmp_path):
    """Two invented tasks in one repo, each containing the same candidate twice."""
    packages, evaluations = [], []
    for i in range(2):
        trajectory = write(tmp_path / f"trajectory-{i}.json", {"messages": [{"role": "user", "content": "Synthetic task."}]})
        assumption = {"statement": "Missing configuration returns an empty dictionary.", "symbol": "demo.load_config",
                      "file": "demo.py", "predicate": "returns", "kind": "repo_behaviour",
                      "scope": {"inputs": "missing file", "config": "default", "env": "test fixture"},
                      "evidence_basis": "unverified_assertion", "evidence_message_indices": [0],
                      "workspace_context": "Invented fixture; behavior has not been run."}
        extraction = write(tmp_path / f"extraction-{i}.json", {"schema_version": 2, "lessons": [
            {"advice": "Use load_config for optional files.", "from_failed_step": False,
             "assumptions": [assumption]},
            {"advice": "Avoid redundant missing-file handling.", "from_failed_step": None,
             "assumptions": [assumption]},
        ]})
        metadata = read(FIXTURES / "gpt-6-high_test_lessons_102526.metadata.json")
        metadata.update(extraction_run_id=f"synthetic-{i}", task_id=f"synthetic-{i}",
                        repository="django/django", source_revision=str(i + 1) * 40,
                        notes="Entirely synthetic integration fixture; SHA is not asserted to exist.")
        meta = write(tmp_path / f"metadata-{i}.json", metadata)
        package = tmp_path / f"package-{i}"
        record = prepare_acquisition(trajectory, extraction, meta, package)
        review = build_evaluation_draft(record, ASSESSOR)
        for lesson in review["lessons"]:
            lesson["evaluation"].update(outcome="usable_as_extracted", reason="Synthetic judgment.")
            for row in lesson["assumptions"]:
                row["evaluation"].update(outcome="usable_as_extracted", reason="Synthetic judgment.",
                    rubric={key: "yes" for key in row["evaluation"]["rubric"]})
        evaluations.append(write(tmp_path / f"review-{i}.json", review))
        packages.append(package)
    bundle = tmp_path / "initial"
    build_handoff(packages, bundle, evaluations=evaluations)
    validity = read(bundle / "lane-r/validity.pending.json")
    for row in validity["rows"]:
        for revision in ["C0", "C1", "Ca"]:
            row[revision].update(outcome="supported", method="manual", assessor=ASSESSOR,
                workspace=f"synthetic-{revision}", reason="Synthetic test judgment, not executed.",
                evidence=[{"reference": "fixture://invented-evidence", "sha256": "0" * 64}])
    validity_path = write(tmp_path / "validity.json", validity)
    with_validity = tmp_path / "with-validity"
    build_handoff(packages, with_validity, evaluations=evaluations, validity_path=validity_path)
    sharing = read(with_validity / "sharing/pending.json")
    sharing["reviewer"] = ASSESSOR
    for row in sharing["rows"]:
        row.update(decision="group", group_id="same-contract", reason="Synthetic equivalence judgment.",
                   key={"repository": "django/django", "symbol": "demo.load_config", "predicate": "returns",
                        "scope": {"inputs": "missing file", "config": "default", "env": "test fixture"}})
    sharing_path = write(tmp_path / "sharing.json", sharing)
    return packages, evaluations, validity_path, sharing_path


def test_no_review_is_needed_and_unknown_metadata_stays_unknown(acquisition, tmp_path):
    output = tmp_path / "handoff"
    before = (acquisition / "record.json").read_bytes()
    report = build_handoff([acquisition], output)
    assert report["original_lessons"] == 5
    assert report["original_assumptions"] == 17
    assert report["extraction_reviews"] == {"pending": 1, "human": 0, "human_ai_assisted": 0, "ai": 0}
    assert report["validity_cells"]["pending"] == 51
    assert report["sharing_decisions"]["pending"] == 17
    assert report["pilot_b"]["exported"] == 0 and report["pilot_b"]["excluded"] == 5
    assert report["research_complete"] is False and report["contract_status"] == "proposed"
    assert report["extraction_cost"]["unknown_acquisitions"] == 1
    assert (acquisition / "record.json").read_bytes() == before
    assert all(row["C0"]["outcome"] == "pending" for row in read(output / "lane-r/validity.pending.json")["rows"])
    assert (output / "pilot-b/lessons.draft.jsonl").read_text() == ""
    assert report["sharing"]["distinct_groups"] == 0


def test_completed_fixture_round_trip_and_portable_original_advice(scenario, tmp_path):
    packages, reviews, validity, sharing = scenario
    output = tmp_path / "complete"
    report = build_handoff(packages, output, evaluations=reviews, validity_path=validity, sharing_path=sharing)
    assert report["original_assumptions"] == 4
    assert report["validity_labels"] == {"repo_history": 4}
    assert report["sharing"]["distinct_groups"] == 1
    assert report["sharing"]["groups_in_multiple_tasks"] == 1
    assert report["sharing"]["groups_in_verified_distinct_prs"] == 0
    assert report["extraction_reviews"]["ai"] == 2 and not report["research_complete"]
    rows = [json.loads(line) for line in (output / "pilot-b/lessons.draft.jsonl").read_text().splitlines()]
    assert len(rows) == 4
    assert set(rows[0]) == {"lesson_id", "lesson_text", "task_id", "repository", "source_revision", "trajectory_pointer"}
    for row in rows:
        assert (output / "pilot-b" / row["trajectory_pointer"]).is_file()
        assert row["lesson_text"] in ["Use load_config for optional files.", "Avoid redundant missing-file handling."]
    manifest = read(output / "manifest.json")
    for path, digest in manifest["artifacts"].items():
        assert hashlib.sha256((output / path).read_bytes()).hexdigest() == digest
    snapshot = {str(p.relative_to(output)): p.read_bytes() for p in output.rglob("*") if p.is_file()}
    assert build_handoff(packages, output, evaluations=reviews, validity_path=validity, sharing_path=sharing) == report
    assert snapshot == {str(p.relative_to(output)): p.read_bytes() for p in output.rglob("*") if p.is_file()}
    assert build_handoff(list(reversed(packages)), output, evaluations=list(reversed(reviews)),
                         validity_path=validity, sharing_path=sharing) == report


@pytest.mark.parametrize("change", ["duplicate_package", "duplicate_review", "foreign_review", "tampered_package",
    "missing_validity", "duplicate_validity", "foreign_validity", "stale_validity", "pending_with_judgment",
    "contradicted_setup_error", "missing_evidence", "missing_assessor", "missing_sharing", "duplicate_sharing",
    "stale_sharing", "wrong_repository", "unknown_scope", "mixed_keys", "unreviewed_group", "unsupported_group"])
def test_bad_handoff_inputs_fail_before_writing(scenario, tmp_path, change):
    packages, reviews, validity_path, sharing_path = scenario
    validity, sharing = read(validity_path), read(sharing_path)
    if change == "duplicate_package": packages.append(packages[0])
    elif change == "duplicate_review": reviews.append(reviews[0])
    elif change == "foreign_review":
        value = read(reviews[0]); value["acquisition_id"] = "foreign"; write(reviews[0], value)
    elif change == "tampered_package":
        value = read(packages[0] / "record.json"); value["lessons"][0]["advice"] = "changed"; write(packages[0] / "record.json", value)
    elif change == "missing_validity": validity["rows"].pop()
    elif change == "duplicate_validity": validity["rows"].append(copy.deepcopy(validity["rows"][0]))
    elif change == "foreign_validity": validity["rows"][0]["assumption_id"] = "foreign"
    elif change == "stale_validity": validity["collection_id"] = "old"
    elif change == "pending_with_judgment": validity["rows"][0]["C0"]["outcome"] = "pending"
    elif change == "contradicted_setup_error":
        validity["rows"][0]["C0"].update(outcome="contradicted", method="execution",
            execution={"command": "synthetic", "asserted_target": "demo.load_config", "result": "setup_error", "exit_code": 1})
    elif change == "missing_evidence": validity["rows"][0]["C0"]["evidence"] = []
    elif change == "missing_assessor": validity["rows"][0]["C0"]["assessor"] = None
    elif change == "missing_sharing": sharing["rows"].pop()
    elif change == "duplicate_sharing": sharing["rows"].append(copy.deepcopy(sharing["rows"][0]))
    elif change == "stale_sharing": sharing["validity_sha256"] = "0" * 64
    elif change == "wrong_repository": sharing["rows"][0]["key"]["repository"] = "wrong/repo"
    elif change == "unknown_scope": sharing["rows"][0]["key"]["scope"]["env"] = None
    elif change == "mixed_keys": sharing["rows"][0]["key"]["symbol"] = "different.symbol"
    elif change == "unreviewed_group": reviews.clear()
    else:
        for key in ["C0", "C1"]: validity["rows"][0][key]["outcome"] = "contradicted"
    write(validity_path, validity); write(sharing_path, sharing)
    with pytest.raises(ValueError):
        build_handoff(packages, tmp_path / "bad", evaluations=reviews, validity_path=validity_path, sharing_path=sharing_path)
    assert not (tmp_path / "bad").exists()


def test_b_export_does_not_require_a_review(scenario, tmp_path):
    packages, _, _, _ = scenario
    report = build_handoff(packages, tmp_path / "unreviewed")
    assert report["pilot_b"]["exported"] == 4
    assert report["extraction_reviews"]["pending"] == 2
    assert not report["research_complete"]


def test_blind_regrouping_hides_primary_partition_and_compares_member_sets(scenario, tmp_path):
    packages, reviews, validity, sharing = scenario
    bundle = tmp_path / "complete"
    build_handoff(packages, bundle, evaluations=reviews, validity_path=validity, sharing_path=sharing)
    output = tmp_path / "sample"
    export_regrouping(bundle, output, seed="frozen-fixture-seed")
    form = read(output / "blind/regrouping.pending.json")
    assert "same-contract" not in (output / "blind/regrouping.pending.json").read_text()
    assert all(row["group_id"] is None for row in form["rows"])
    assert len(form["rows"]) == 4  # ceil(30% of one group), all members
    for row in form["rows"]:
        assert (output / "blind" / row["original"]["trajectory_pointer"]).is_file()
    form["reviewer"] = ASSESSOR
    form["gold_exposure"] = False
    for row in form["rows"]:
        row.update(group_id="different-name-same-partition", decision="group", reason="Synthetic regrouping.")
    response = write(tmp_path / "regrouped.json", form)
    report = compare_regrouping(output, response, tmp_path / "comparison")
    assert report["groups_changed"] == 0 and report["disagreement_rate"] == 0
    form["rows"][0]["group_id"] = "split-group"
    write(response, form)
    report = compare_regrouping(output, response, tmp_path / "split-comparison")
    assert report["groups_changed"] == 1 and report["disagreement_rate"] == 1
    form["rows"].pop()
    write(response, form)
    with pytest.raises(ValueError):
        compare_regrouping(output, response, tmp_path / "bad-comparison")


@pytest.mark.parametrize("c0,c1,ca,label", [
    ("supported", "supported", "pending", "repo_history"),
    ("supported", "contradicted", "pending", "repo_history_superseded"),
    ("contradicted", "supported", "undefined", "repo_history"),
    ("contradicted", "contradicted", "supported", "agent_edit_only"),
    ("contradicted", "contradicted", "contradicted", "not_supported_in_checked_workspaces"),
    ("contradicted", "contradicted", "undefined", "agent_workspace_unavailable"),
    ("pending", "supported", "supported", "pending"),
    ("inconclusive", "supported", "supported", "inconclusive"),
    ("contradicted", "contradicted", "inconclusive", "inconclusive"),
])
def test_validity_labels_keep_superseded_and_intermediate_cases_distinct(c0, c1, ca, label):
    assert validity_label({key: {"outcome": value} for key, value in zip(["C0", "C1", "Ca"], [c0, c1, ca])}) == label


def test_current_unsupported_candidates_cannot_be_grouped(scenario, tmp_path):
    packages, reviews, validity_path, sharing_path = scenario
    validity = read(validity_path)
    for key in ["C0", "C1"]:
        validity["rows"][0][key]["outcome"] = "contradicted"
    write(validity_path, validity)
    sharing = read(sharing_path)
    sharing["validity_sha256"] = canonical_hash({row["assumption_id"]: row for row in validity["rows"]})
    write(sharing_path, sharing)
    with pytest.raises(ValueError, match="repository support"):
        build_handoff(packages, tmp_path / "unsupported", evaluations=reviews,
                      validity_path=validity_path, sharing_path=sharing_path)


def test_superseded_assumptions_stay_in_sharing(scenario, tmp_path):
    packages, reviews, validity_path, sharing_path = scenario
    validity = read(validity_path)
    for row in validity["rows"]:
        row["C1"]["outcome"] = "contradicted"
    write(validity_path, validity)
    sharing = read(sharing_path)
    sharing["validity_sha256"] = canonical_hash({row["assumption_id"]: row for row in validity["rows"]})
    write(sharing_path, sharing)
    report = build_handoff(packages, tmp_path / "superseded", evaluations=reviews,
                           validity_path=validity_path, sharing_path=sharing_path)
    assert report["validity_labels"] == {"repo_history_superseded": 4}
    assert report["sharing"]["groups_in_multiple_tasks"] == 1


def test_repeated_lessons_in_one_task_do_not_count_as_cross_task_sharing(scenario, tmp_path):
    packages, reviews, _, _ = scenario
    output = tmp_path / "single"
    build_handoff(packages[:1], output, evaluations=reviews[:1])
    validity = read(output / "lane-r/validity.pending.json")
    for row in validity["rows"]:
        for key in ["C0", "C1"]:
            row[key].update(outcome="supported", method="execution", assessor=ASSESSOR, workspace="fixture-C0-or-C1",
                reason="Synthetic pass.", evidence=[{"reference": "fixture://evidence", "sha256": "0" * 64}],
                execution={"command": "not executed", "asserted_target": "demo.load_config", "result": "pass", "exit_code": 0})
    path = write(tmp_path / "single-validity.json", validity)
    build_handoff(packages[:1], tmp_path / "single-validity", evaluations=reviews[:1], validity_path=path)
    sharing = read(tmp_path / "single-validity/sharing/pending.json")
    sharing["reviewer"] = ASSESSOR
    for row in sharing["rows"]:
        row.update(decision="group", group_id="one", reason="Synthetic grouping.", key={
            "repository": "django/django", "symbol": "demo.load_config", "predicate": "returns",
            "scope": {"inputs": "missing file", "config": "default", "env": "test fixture"}})
    report = build_handoff(packages[:1], tmp_path / "single-complete", evaluations=reviews[:1], validity_path=path,
                           sharing_path=write(tmp_path / "single-sharing.json", sharing))
    assert report["sharing"]["groups_in_multiple_lessons"] == 1
    assert report["sharing"]["groups_in_multiple_tasks"] == 0


def test_changed_output_is_not_overwritten_and_tampered_bundles_cannot_be_sampled(scenario, tmp_path):
    packages, reviews, validity, sharing = scenario
    bundle = tmp_path / "output"
    build_handoff(packages, bundle, evaluations=reviews, validity_path=validity, sharing_path=sharing)
    target = bundle / "report.md"
    target.write_text("User notes must be retained.", encoding="utf-8")
    with pytest.raises(FileExistsError):
        build_handoff(packages, bundle, evaluations=reviews, validity_path=validity, sharing_path=sharing)
    assert target.read_text() == "User notes must be retained."
    with pytest.raises(ValueError, match="changed artifact"):
        export_regrouping(bundle, tmp_path / "sample", "seed")


def test_sampling_rounds_up_by_groups_and_is_reproducible(scenario, tmp_path):
    packages, reviews, validity, sharing_path = scenario
    sharing = read(sharing_path)
    for i, row in enumerate(sharing["rows"]):
        row["group_id"] = f"separate-{i}"
    write(sharing_path, sharing)
    bundle = tmp_path / "separate-groups"
    build_handoff(packages, bundle, evaluations=reviews, validity_path=validity, sharing_path=sharing_path)
    first = export_regrouping(bundle, tmp_path / "sample", "fixed")
    second = export_regrouping(bundle, tmp_path / "sample", "fixed")
    assert first == second
    assert len(first["primary_groups"]) == 2  # ceil(0.3 * 4), not 30% of occurrences
    assert len(read(tmp_path / "sample/blind/regrouping.pending.json")["rows"]) == 2


@pytest.mark.parametrize("change", ["none", "unknown_task", "wrong_revision", "wrong_repository"])
def test_production_metadata_must_match_selection_before_handoff(acquisition, tmp_path, change):
    # Entirely synthetic test artifacts: completeness is not certification of actual production provenance.
    metadata = read(acquisition / "inputs/metadata.json")
    metadata.update(purpose="pilot_a", extraction_run_id="synthetic-production-contract-test", agent_run_id="test-agent",
                    repository="django/django", source_revision="1" * 40, task_id="django__django-test")
    metadata["extractor"].update(provider="synthetic-test-provider", model_id="synthetic-test-model")
    if change == "unknown_task": metadata["task_id"] = "django__unknown"
    elif change == "wrong_revision": metadata["source_revision"] = "2" * 40
    elif change == "wrong_repository": metadata["repository"] = "django/wrong-repository"
    trajectory = {"messages": [{"role": "user", "content": "Synthetic production-contract test only."}]}
    trajectory_path = write(tmp_path / "production-trajectory.json", trajectory)
    extraction_path = write(tmp_path / "production-extraction.json", {"schema_version": 2, "lessons": []})
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("<trajectory>\n" + format_transcript(trajectory) + "</trajectory>", encoding="utf-8")
    package = tmp_path / "production"
    prepare_acquisition(trajectory_path, extraction_path, write(tmp_path / "production-metadata.json", metadata),
                        package, prompt)
    selection = tmp_path / "selection.csv"
    selection.write_text("instance_id,base_commit,cluster,same_pr_group,same_text\n"
                         "django__django-test," + "1" * 40 + ",fixture,django/django#test,False\n", encoding="utf-8")
    if change == "none":
        report = build_handoff([package], tmp_path / "production-handoff", selection_path=selection)
        assert report["selection"]["production_tasks_missing"] == []
        assert report["research_complete"] is False
        with pytest.raises(ValueError, match="separate collections"):
            build_handoff([package, acquisition], tmp_path / "mixed", selection_path=selection)
    else:
        with pytest.raises(ValueError, match="production"):
            build_handoff([package], tmp_path / "bad-production", selection_path=selection)


def test_unreviewed_or_empty_grouping_cannot_produce_a_misleading_sample(acquisition, tmp_path):
    bundle = tmp_path / "pending"
    build_handoff([acquisition], bundle)
    with pytest.raises(ValueError, match="finish primary grouping"):
        export_regrouping(bundle, tmp_path / "sample", "seed")
