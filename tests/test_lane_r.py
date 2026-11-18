import json
from pathlib import Path

import pytest

from memrev.evaluation import build_evaluation_draft
from memrev.handoff import build_handoff
from memrev.handoff_io import load_bundle, write_bundle
from memrev.lane_r import prepare_execution, record_execution, validate_return, import_return
from memrev.provenance import _json_bytes, prepare_acquisition


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'pilot-a/fixtures/test'


def write(path, value):
    path.write_bytes(_json_bytes(value))
    return path


@pytest.fixture
def bundle(tmp_path):
    package = tmp_path / 'acquisition'
    metadata = json.loads((FIXTURES / 'gpt-6-high_test_lessons_102526.metadata.json').read_text())
    metadata.update(repository='astropy/astropy', source_revision='a' * 40, agent_run_id='synthetic')
    record = prepare_acquisition(FIXTURES / 'full_trajectory_example.traj.json',
                                FIXTURES / 'gpt-6-high_test_lessons_102526.json',
                                write(tmp_path / 'metadata.json', metadata), package)
    reviewer = {'id': 'synthetic', 'type': 'ai', 'independent': False, 'note': 'Synthetic test only'}
    review = build_evaluation_draft(record, reviewer)
    for lesson in review['lessons']:
        lesson['evaluation'].update(outcome='usable_as_extracted', reason='Synthetic')
        for a in lesson['assumptions']:
            a['evaluation'].update(outcome='usable_as_extracted', reason='Synthetic',
                                   rubric={k: 'yes' for k in a['evaluation']['rubric']})
    review['lessons'][0]['assumptions'][0]['evaluation'].update(
        outcome='context_only', issue_codes=['historical_observation'])
    review['lessons'][0]['assumptions'][0]['evaluation']['rubric']['repository_behaviour'] = 'no'
    handoff = tmp_path / 'handoff'
    build_handoff([package], handoff, evaluations=[write(tmp_path / 'review.json', review)])
    task_id = record['metadata']['task_id']
    prepared = tmp_path / 'prepared'
    inventory = {'tasks': [{'task_id': task_id, 'repository': record['metadata']['repository'],
                            'source_revision': record['metadata']['source_revision'],
                            'agent_run_id': record['metadata']['agent_run_id'],
                            'image': {'image': 'synthetic:image', 'image_id': 'sha256:' + '1' * 64},
                            'trajectory': 'inputs/trajectory.json'}]}
    write_bundle(prepared, {'inventory.json': _json_bytes(inventory),
                            'inputs/trajectory.json': (package / 'inputs/trajectory.json').read_bytes()},
                 {'artifact_type': 'imported_pilot_a_run'})
    output = tmp_path / 'execution'
    prepare_execution(handoff, prepared, output)
    return output


def receipt_for(bundle, tmp_path, revision='C0', result='pass', code=0):
    order = json.loads((bundle / 'work_order.json').read_text())
    job = next(row for row in order['rows'] if row['scheduled'])
    private = tmp_path / 'source'
    private.mkdir(exist_ok=True)
    for name in ['check.py', 'output.txt', 'reconstruction.json']:
        (private / name).write_text('private synthetic evidence: ' + name)
    workspace = {'workspace_version': 1, 'task_id': job['task_id'], 'revision': revision,
                 'source_revision': job['source_revision'], 'image_id': job['image']['image_id'],
                 'reconstruction': 'synthetic fixture; not executed',
                 'tracked_diff_sha256': '2' * 64, 'untracked_manifest_sha256': '3' * 64,
                 'environment_sha256': '4' * 64}
    return {'receipt_version': 1, 'collection_id': order['collection_id'],
            'assumption_id': job['assumption_id'], 'revision': revision, 'workspace': workspace,
            'assessor': {'id': 'synthetic', 'type': 'ai', 'independent': False, 'note': 'Synthetic only'},
            'reason': 'Synthetic fixture, not a real execution.',
            'command': 'python /checks/check.py', 'result': result, 'exit_code': code,
            'evidence_files': {key: str(private / name) for key, name in
                               [('check_source', 'check.py'), ('output', 'output.txt'), ('reconstruction', 'reconstruction.json')]}}


def test_prepare_preserves_denominator_and_does_not_schedule_context(bundle):
    order = json.loads((bundle / 'work_order.json').read_text())
    assert len(order['rows']) == 17
    assert not order['rows'][0]['scheduled']
    assert order['rows'][0]['initial_revisions'] == []
    assert all(row['initial_revisions'] == ['C0', 'C1'] for row in order['rows'] if row['scheduled'])
    report = validate_return(bundle, bundle / 'validity.pending.json')
    assert report['outcomes'] == {'pending': 51}
    assert report['stage_complete'] is False


def test_record_private_evidence_validate_and_import_partial_return(bundle, tmp_path):
    receipt = receipt_for(bundle, tmp_path)
    result = tmp_path / 'return.json'
    evidence = tmp_path / 'private'
    record_execution(bundle, bundle / 'validity.pending.json', write(tmp_path / 'receipt.json', receipt), result, evidence)
    report = validate_return(bundle, result, evidence)
    assert report['outcomes']['supported'] == 1
    assert report['private_evidence_verified'] is True
    contents = result.read_text()
    assert 'private synthetic evidence' not in contents
    assert str(tmp_path / 'source') not in contents
    assert 'lane-r://sha256/' in contents
    rebuilt = import_return(bundle, result, tmp_path / 'with-validity')
    assert rebuilt['validity_cells']['supported'] == 1
    assert rebuilt['research_complete'] is False
    assert json.loads((result).read_text())['rows'][1]['C0']['execution']['asserted_target']


@pytest.mark.parametrize('result,code,outcome', [('fail_on_asserted_target', 1, 'contradicted'),
                                             ('setup_error', 2, 'inconclusive'), ('timeout', None, 'inconclusive')])
def test_result_mapping_does_not_treat_environment_errors_as_contradictions(bundle, tmp_path, result, code, outcome):
    receipt = receipt_for(bundle, tmp_path, result=result, code=code)
    output = tmp_path / 'return.json'
    record_execution(bundle, bundle / 'validity.pending.json', write(tmp_path / 'receipt.json', receipt), output, tmp_path / 'private')
    assert validate_return(bundle, output)['outcomes'][outcome] == 1


@pytest.mark.parametrize('change', ['collection', 'source', 'image', 'revision', 'pass_code', 'context', 'early_ca'])
def test_receipt_rejects_identity_schedule_and_mapping_errors(bundle, tmp_path, change):
    receipt = receipt_for(bundle, tmp_path)
    if change == 'collection': receipt['collection_id'] = 'wrong'
    elif change == 'source': receipt['workspace']['source_revision'] = 'wrong'
    elif change == 'image': receipt['workspace']['image_id'] = 'sha256:' + '9' * 64
    elif change == 'revision': receipt['workspace']['revision'] = 'C1'
    elif change == 'pass_code': receipt['exit_code'] = 1
    elif change == 'context':
        receipt['assumption_id'] = json.loads((bundle / 'work_order.json').read_text())['rows'][0]['assumption_id']
    elif change == 'early_ca': receipt['revision'] = receipt['workspace']['revision'] = 'Ca'
    with pytest.raises(ValueError):
        record_execution(bundle, bundle / 'validity.pending.json', write(tmp_path / 'receipt.json', receipt),
                         tmp_path / 'bad.json', tmp_path / 'private')
    assert not (tmp_path / 'bad.json').exists()


def test_private_evidence_tampering_is_detected(bundle, tmp_path):
    receipt = receipt_for(bundle, tmp_path)
    result = tmp_path / 'return.json'
    private = tmp_path / 'private'
    record_execution(bundle, bundle / 'validity.pending.json', write(tmp_path / 'receipt.json', receipt), result, private)
    next((private / 'sha256').iterdir()).write_text('Changed')
    with pytest.raises(ValueError, match='evidence'):
        validate_return(bundle, result, private)


def test_completed_cell_cannot_be_silently_replaced(bundle, tmp_path):
    receipt = receipt_for(bundle, tmp_path)
    result = tmp_path / 'return.json'
    path = write(tmp_path / 'receipt.json', receipt)
    private = tmp_path / 'private'
    record_execution(bundle, bundle / 'validity.pending.json', path, result, private)
    receipt.update(result='fail_on_asserted_target', exit_code=1)
    with pytest.raises(ValueError, match='completed'):
        record_execution(bundle, result, write(path, receipt), tmp_path / 'changed.json', private)


def test_ca_becomes_eligible_only_after_both_source_cells_are_contradicted(bundle, tmp_path):
    previous = bundle / 'validity.pending.json'
    private = tmp_path / 'private'
    for revision in ['C0', 'C1', 'Ca']:
        receipt = receipt_for(bundle, tmp_path, revision=revision,
                              result='pass' if revision == 'Ca' else 'fail_on_asserted_target',
                              code=0 if revision == 'Ca' else 1)
        output = tmp_path / f'return-{revision}.json'
        record_execution(bundle, previous, write(tmp_path / 'receipt.json', receipt), output, private)
        previous = output
    report = validate_return(bundle, previous, private)
    assert report['outcomes']['contradicted'] == 2
    assert report['outcomes']['supported'] == 1
    result = import_return(bundle, previous, tmp_path / 'imported')
    assert result['validity_labels']['agent_edit_only'] == 1


def test_receipt_template_cannot_be_recorded_as_a_real_result(bundle, tmp_path):
    with pytest.raises((ValueError, TypeError)):
        record_execution(bundle, bundle / 'validity.pending.json', bundle / 'receipt.template.json',
                         tmp_path / 'result.json', tmp_path / 'private')
    assert not (tmp_path / 'result.json').exists()


def test_private_evidence_cannot_be_written_into_the_shared_bundle(bundle, tmp_path):
    receipt = receipt_for(bundle, tmp_path)
    with pytest.raises(ValueError, match='outside'):
        record_execution(bundle, bundle / 'validity.pending.json', write(tmp_path / 'receipt.json', receipt),
                         tmp_path / 'result.json', bundle / 'private')


def test_corrupt_previous_evidence_stops_recording_before_new_return_is_written(bundle, tmp_path):
    receipt = receipt_for(bundle, tmp_path)
    previous = tmp_path / 'first.json'
    private = tmp_path / 'private'
    record_execution(bundle, bundle / 'validity.pending.json', write(tmp_path / 'receipt.json', receipt), previous, private)
    next((private / 'sha256').iterdir()).unlink()
    receipt['revision'] = receipt['workspace']['revision'] = 'C1'
    with pytest.raises(ValueError, match='evidence'):
        record_execution(bundle, previous, write(tmp_path / 'receipt.json', receipt), tmp_path / 'second.json', private)
    assert not (tmp_path / 'second.json').exists()


def test_return_must_keep_all_original_rows(bundle, tmp_path):
    doc = json.loads((bundle / 'validity.pending.json').read_text())
    doc['rows'].pop(0)
    with pytest.raises(ValueError, match='exactly'):
        validate_return(bundle, write(tmp_path / 'incomplete.json', doc))
