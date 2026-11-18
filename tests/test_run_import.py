import csv
import hashlib
import json
from pathlib import Path

import pytest

from memrev.run_import import prepare_run


@pytest.fixture
def run(tmp_path):
    source = tmp_path / 'run'
    task = 'django__django-123'
    (source / task).mkdir(parents=True)
    instance = {'instance_id': task, 'repo': 'django/django', 'base_commit': 'a' * 40,
                'image_name': 'example:image'}
    instances = tmp_path / 'instances.jsonl'
    instances.write_text(json.dumps(instance) + '\n')
    selection = tmp_path / 'selection.csv'
    with selection.open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=['instance_id', 'base_commit', 'same_pr_group', 'image'])
        writer.writeheader()
        writer.writerow({'instance_id': task, 'base_commit': 'a' * 40,
                         'same_pr_group': 'django/django#123', 'image': 'example:image'})
    meta = {'run': 'test', 'model': 'test-model',
            'instances_sha256': hashlib.sha256(instances.read_bytes()).hexdigest(),
            'images': {task: {'image': 'example:image', 'image_id': 'sha256:test'}}}
    (source / 'run_meta.json').write_text(json.dumps(meta))
    trajectory = {'instance_id': task, 'info': {'exit_status': 'Submitted'},
                  'messages': [{'role': 'user', 'content': 'Example task'}]}
    (source / task / f'{task}.traj.json').write_text(json.dumps(trajectory))
    workspace = {'instance_id': task, 'base_commit': 'a' * 40, 'image': 'example:image',
                 'exit_code_mismatches': 0, 'tracked_diff_same': False, 'patch_applies': False}
    (source / task / 'final_workspace.json').write_text(json.dumps(workspace))
    return source, selection, instances, task


def test_prepare_snapshots_run_and_preserves_replay_caveats(run, tmp_path):
    source, selection, instances, task = run
    output = tmp_path / 'prepared'
    inventory = prepare_run(source, output, selection, instances)
    assert inventory['tasks'][0]['workspace']['tracked_diff_same'] is False
    assert inventory['tasks'][0]['workspace']['evidence_type'] == 'reported_replay'
    assert inventory['tasks'][0]['source_revision'] == 'a' * 40
    assert (output / f'inputs/{task}/trajectory.json').read_bytes() == (source / task / f'{task}.traj.json').read_bytes()
    assert 'Example task' in (output / f'prompts/{task}.txt').read_text()
    assert prepare_run(source, output, selection, instances) == inventory
    assert not (output / 'extraction.json').exists()


@pytest.mark.parametrize('change', ['hash', 'task', 'source', 'image', 'missing', 'extra', 'duplicate'])
def test_prepare_rejects_mismatched_run_before_writing(run, tmp_path, change):
    source, selection, instances, task = run
    if change == 'hash':
        instances.write_text(instances.read_text() + '\n')
    elif change in ['task', 'source', 'image']:
        path = source / task / 'final_workspace.json'
        doc = json.loads(path.read_text())
        doc[{'task': 'instance_id', 'source': 'base_commit', 'image': 'image'}[change]] = 'wrong'
        path.write_text(json.dumps(doc))
    elif change == 'missing':
        (source / task / f'{task}.traj.json').unlink()
    elif change == 'extra':
        (source / 'unexpected').mkdir()
        (source / 'unexpected/unexpected.traj.json').write_text('{}')
    else:
        (source / task / 'duplicate.traj.json').write_text('{}')
    with pytest.raises(ValueError):
        prepare_run(source, tmp_path / 'prepared', selection, instances)
    assert not (tmp_path / 'prepared').exists()


def test_prepare_refuses_changed_existing_output(run, tmp_path):
    source, selection, instances, task = run
    prepare_run(source, tmp_path / 'prepared', selection, instances)
    path = source / task / f'{task}.traj.json'
    doc = json.loads(path.read_text())
    doc['messages'][0]['content'] = 'Changed task'
    path.write_text(json.dumps(doc))
    with pytest.raises(FileExistsError):
        prepare_run(source, tmp_path / 'prepared', selection, instances)
