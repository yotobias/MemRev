import copy
import csv
import fcntl
import io
import json
from pathlib import Path
import zipfile

import pytest

from memrev.handoff_io import load_bundle, write_bundle
from memrev.provenance import _json_bytes
from memrev.trajectory import build_extract_prompt
from memrev.workflow import run_workflow
from memrev.model_client import ModelCallError


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def setup(tmp_path):
    tasks = ['django__django-1', 'django__django-2']
    files = {}
    inventory = {'run_id': 'synthetic-agent-run', 'tasks': []}
    selection = io.StringIO()
    writer = csv.DictWriter(selection, fieldnames=['instance_id', 'base_commit', 'cluster', 'same_pr_group', 'same_text'])
    writer.writeheader()
    for task in tasks:
        trajectory = {'instance_id': task, 'messages': [{'role': 'user', 'content': f'Synthetic task {task}'}]}
        prompt = build_extract_prompt(trajectory, ROOT / 'pilot-a/extract_prompt.md')
        files[f'inputs/{task}/trajectory.json'] = _json_bytes(trajectory)
        files[f'prompts/{task}.txt'] = prompt.encode()
        inventory['tasks'].append({'task_id': task, 'repository': 'django/django', 'source_revision': 'a' * 40,
                                   'agent_run_id': 'synthetic-agent-run', 'trajectory': f'inputs/{task}/trajectory.json',
                                   'prompt': f'prompts/{task}.txt'})
        writer.writerow({'instance_id': task, 'base_commit': 'a' * 40, 'cluster': 'C1',
                         'same_pr_group': f'django/django#{task[-1]}', 'same_text': ''})
    files['selection.csv'] = selection.getvalue().encode()
    files['inventory.json'] = _json_bytes(inventory)
    prepared = tmp_path / 'prepared'
    write_bundle(prepared, files, {'artifact_type': 'imported_pilot_a_run'})
    config = {'workflow_version': 1, 'run_id': 'synthetic-workflow', 'max_calls': 8, 'max_attempts': 2,
              'extractor': {'provider': 'openai', 'model': 'synthetic-extractor', 'api_key_env': 'TEST_API_KEY',
                            'output_mode': 'json_schema', 'max_output_tokens': 2000, 'timeout_seconds': 30},
              'reviewer': {'provider': 'anthropic', 'model': 'synthetic-reviewer', 'api_key_env': 'TEST_OTHER_KEY',
                           'output_mode': 'json_schema', 'max_output_tokens': 2000, 'timeout_seconds': 30}}
    notes = tmp_path / 'limitations.md'
    notes.write_text('Synthetic integration fixture; not research findings.')
    return {'prepared_dir': prepared, 'config': config, 'output_dir': tmp_path / 'output', 'limitations_path': notes}


def extraction():
    return {'schema_version': 2, 'lessons': [{'advice': 'Check the input condition.', 'from_failed_step': None,
        'assumptions': [{'statement': 'Synthetic unsupported candidate.', 'symbol': None, 'file': None,
                         'predicate': 'other', 'kind': 'repo_behaviour',
                         'scope': {'inputs': None, 'config': None, 'env': None},
                         'evidence_message_indices': [], 'evidence_basis': 'no_evidence',
                         'workspace_context': 'Unknown; synthetic test.'}]}]}


class FakeClient:
    def __init__(self):
        self.requests = []

    def __call__(self, request):
        self.requests.append(copy.deepcopy(request))
        if request['stage'] == 'extract':
            content = extraction()
        else:
            form = json.loads(request['messages'][1]['content'].split('<review_form>\n')[1].split('\n</review_form>')[0])
            judgment = {'outcome': 'uncertain', 'issue_codes': ['citation_coverage_incomplete'],
                        'reason': 'The trajectory provides no evidence for this synthetic candidate.',
                        'reviewer_evidence_message_indices': []}
            content = {'lessons': []}
            for lesson in form['lessons']:
                assumptions = []
                for assumption in lesson['assumptions']:
                    rating = {**judgment, 'rubric': {key: 'uncertain' for key in form['rubric_definitions']}}
                    assumptions.append({'assumption_id': assumption['assumption_id'], 'evaluation': rating})
                content['lessons'].append({'lesson_id': lesson['lesson_id'], 'evaluation': judgment,
                                           'assumptions': assumptions})
        return {'content': json.dumps(content), 'model_id': request['model']['model'] + '-returned',
                'input_tokens': 100, 'output_tokens': 50, 'cost_usd': None, 'cost_basis': 'unknown',
                'finish_reason': 'stop', 'raw_response': {'id': 'synthetic', 'object': 'test-response'}}


def test_plan_is_offline_and_does_not_create_run(setup):
    client = FakeClient()
    plan = run_workflow(**setup, client=client)
    assert plan['minimum_calls'] == 4
    assert not client.requests
    assert not setup['output_dir'].exists()


def test_workflow_exports_all_originals_and_preserves_negative_reviews(setup):
    client = FakeClient()
    status = run_workflow(**setup, client=client, execute=True)
    assert status['complete']
    assert len(client.requests) == 4
    output = setup['output_dir']
    report = json.loads((output / 'handoff/report.json').read_text())
    assert report['assumption_evaluation_outcomes'] == {'uncertain': 2}
    assert report['validity_cells']['pending'] == 6
    assert report['pilot_b']['exported'] == 2
    assert report['research_complete'] is False
    reviews = sorted((output / 'tasks').glob('*/review.json'))
    assert all(json.loads(p.read_text())['reviewer']['type'] == 'ai' for p in reviews)
    assert all(json.loads(p.read_text())['reviewer']['independent'] is True for p in reviews)
    load_bundle(output / 'delivery')
    with zipfile.ZipFile(output / 'pilot-b-delivery.zip') as archive:
        assert archive.testzip() is None
        assert archive.read('limitations.md').decode().startswith('Synthetic')
        assert len(archive.read('handoff/pilot-b/lessons.draft.jsonl').splitlines()) == 2
    before = (output / 'pilot-b-delivery.zip').read_bytes()
    run_workflow(**setup, client=client, execute=True)
    assert len(client.requests) == 4
    assert (output / 'pilot-b-delivery.zip').read_bytes() == before


def test_smoke_then_resume_full_run_does_not_repeat_calls(setup):
    client = FakeClient()
    status = run_workflow(**setup, client=client, execute=True, task_ids=['django__django-1'])
    assert not status['complete']
    assert not (setup['output_dir'] / 'handoff').exists()
    run_workflow(**setup, client=client, execute=True)
    assert len(client.requests) == 4
    for request in client.requests:
        assert [m['role'] for m in request['messages']] == ['system', 'user']
        other = 'django__django-2' if request['task_id'].endswith('-1') else 'django__django-1'
        assert other not in request['messages'][1]['content']
        assert '31/32' not in request['messages'][1]['content']


@pytest.mark.parametrize('change', ['config', 'prepared', 'notes'])
def test_resume_rejects_changed_inputs_before_calls(setup, change):
    client = FakeClient()
    run_workflow(**setup, client=client, execute=True, task_ids=['django__django-1'])
    if change == 'config':
        setup['config']['extractor']['model'] = 'different'
    elif change == 'prepared':
        (setup['prepared_dir'] / 'prompts/django__django-2.txt').write_text('Changed')
    else:
        setup['limitations_path'].write_text('Changed notes')
    with pytest.raises((ValueError, FileExistsError)):
        run_workflow(**setup, client=client, execute=True)
    assert len(client.requests) == 2


@pytest.mark.parametrize('failure', ['json', 'truncated', 'refused', 'missing_review_id'])
def test_bad_output_is_retained_and_not_automatically_resampled(setup, failure):
    base = FakeClient()
    def client(request):
        response = base(request)
        if failure == 'json':
            response['content'] = '```json\n{}\n```'
        elif failure == 'truncated':
            response['finish_reason'] = 'length'
        elif failure == 'refused':
            response['content'] = None
        elif request['stage'] == 'review':
            response['content'] = '{"lessons": []}'
        return response
    status = run_workflow(**setup, client=client, execute=True)
    assert not status['complete']
    count = len(base.requests)
    run_workflow(**setup, client=client, execute=True)
    assert len(base.requests) == count
    assert not (setup['output_dir'] / 'pilot-b-delivery.zip').exists()
    assert list((setup['output_dir'] / 'calls').glob('*/*/*/result/response.json'))


def test_transport_retries_are_bounded_across_resume(setup):
    calls = []
    def client(request):
        calls.append(request)
        raise ModelCallError('RateLimitError', retryable=True)
    run_workflow(**setup, client=client, execute=True)
    assert len(calls) == 4
    run_workflow(**setup, client=client, execute=True)
    assert len(calls) == 4


def test_global_call_limit_includes_failed_attempts(setup):
    setup['config']['max_calls'] = 1
    client = FakeClient()
    status = run_workflow(**setup, client=client, execute=True)
    assert not status['complete']
    assert len(client.requests) == 1
    assert status['calls_started'] == 1


def test_interrupted_call_requires_explicit_retry(setup):
    def interrupted(request):
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        run_workflow(**setup, client=interrupted, execute=True, task_ids=['django__django-1'])
    client = FakeClient()
    status = run_workflow(**setup, client=client, execute=True, task_ids=['django__django-1'])
    assert 'unknown' in status['tasks']['django__django-1']['error']
    assert not client.requests
    run_workflow(**setup, client=client, execute=True, task_ids=['django__django-1'], retry_unknown=True)
    assert len(client.requests) == 2


def test_same_requested_model_rejected(setup):
    setup['config']['reviewer'] = copy.deepcopy(setup['config']['extractor'])
    with pytest.raises(ValueError, match='different'):
        run_workflow(**setup)


def test_directory_lock_prevents_concurrent_calls(setup):
    setup['output_dir'].mkdir()
    client = FakeClient()
    with (setup['output_dir'] / '.workflow.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match='Another workflow'):
            run_workflow(**setup, client=client, execute=True)
    assert not client.requests


def test_empty_extraction_completes_without_inventing_candidates(setup):
    base = FakeClient()
    def client(request):
        response = base(request)
        if request['stage'] == 'extract':
            response['content'] = '{"schema_version": 2, "lessons": []}'
        return response
    status = run_workflow(**setup, client=client, execute=True)
    assert status['complete']
    report = json.loads((setup['output_dir'] / 'handoff/report.json').read_text())
    assert report['original_lessons'] == 0
    assert report['selection']['production_tasks_missing'] == []


def test_provider_model_aliases_do_not_create_false_separate_model_claim(setup):
    setup['config']['reviewer']['provider'] = setup['config']['extractor']['provider']
    base = FakeClient()
    def client(request):
        response = base(request)
        response['model_id'] = 'same-actual-model'
        return response
    status = run_workflow(**setup, client=client, execute=True)
    assert not status['complete']
    assert all('same model' in row['error'] for row in status['tasks'].values())


def test_normal_response_after_transient_failure_is_reused(setup):
    base = FakeClient()
    failed = False
    def client(request):
        nonlocal failed
        if not failed:
            failed = True
            raise ModelCallError('ServiceUnavailableError', retryable=True)
        return base(request)
    status = run_workflow(**setup, client=client, execute=True)
    assert status['complete']
    assert status['calls_started'] == 5
    run_workflow(**setup, client=client, execute=True)
    assert len(base.requests) == 4


def test_changed_saved_response_is_detected_without_new_calls(setup):
    client = FakeClient()
    run_workflow(**setup, client=client, execute=True, task_ids=['django__django-1'])
    response_path = next((setup['output_dir'] / 'calls').glob('*/*/*/result/response.json'))
    response_path.write_text('{}')
    with pytest.raises(ValueError, match='changed artifact'):
        run_workflow(**setup, client=client, execute=True, task_ids=['django__django-1'])
    assert len(client.requests) == 2


def test_bad_prepared_identity_fails_before_any_model_call(setup):
    manifest, files = load_bundle(setup['prepared_dir'])
    inventory = json.loads(files['inventory.json'])
    inventory['tasks'][0]['source_revision'] = 'b' * 40
    files['inventory.json'] = _json_bytes(inventory)
    other = setup['prepared_dir'].parent / 'inconsistent'
    write_bundle(other, files, {'artifact_type': 'imported_pilot_a_run'})
    setup['prepared_dir'] = other
    client = FakeClient()
    with pytest.raises(ValueError, match='source'):
        run_workflow(**setup, client=client, execute=True)
    assert not client.requests


def test_existing_unrelated_directory_is_never_adopted(setup):
    setup['output_dir'].mkdir()
    old = setup['output_dir'] / 'status.json'
    old.write_text('Preserve old research result')
    with pytest.raises(FileExistsError):
        run_workflow(**setup, client=FakeClient(), execute=True)
    assert old.read_text() == 'Preserve old research result'


def test_skipped_completed_tasks_are_revalidated_before_packaging(setup):
    client = FakeClient()
    run_workflow(**setup, client=client, execute=True, task_ids=['django__django-1'])
    review = setup['output_dir'] / 'tasks/django__django-1/review.json'
    changed = json.loads(review.read_text())
    changed['reviewer']['note'] = 'Different but structurally valid review'
    review.write_text(json.dumps(changed))
    status = run_workflow(**setup, client=client, execute=True, task_ids=['django__django-2'])
    assert not status['complete']
    assert 'overwrite' in status['tasks']['django__django-1']['error']
    assert len(client.requests) == 4
