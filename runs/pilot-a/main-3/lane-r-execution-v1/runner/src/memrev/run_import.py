"""Snapshot an imported Lane R run and prepare full-trajectory extraction prompts."""

import argparse
import csv
import io
from pathlib import Path
import re

from memrev.handoff_io import write_bundle
from memrev.provenance import _json_bytes, _sha256
from memrev.trajectory import build_extract_prompt, parse_extraction


ROOT = Path(__file__).resolve().parents[2]


def _indexed(rows, label):
    result = dict()
    for row in rows:
        identifier = row['instance_id']
        if not re.fullmatch(r'[A-Za-z0-9_-]+', identifier) or identifier in result:
            raise ValueError(f'{label}: unsafe or duplicate task ID')
        result[identifier] = row
    return result


def prepare_run(run_dir, output_dir, selection_path=ROOT / 'pilot-a/clusters.csv',
                instances_path=ROOT / 'pilot-a/instances/main/instances.jsonl'):
    """Validate identities, preserve source bytes, and record replay limitations without executing commands."""
    source = Path(run_dir)
    meta_bytes = (source / 'run_meta.json').read_bytes()
    meta = parse_extraction(meta_bytes.decode('utf-8'))
    instance_bytes = Path(instances_path).read_bytes()
    if _sha256(instance_bytes) != meta['instances_sha256']:
        raise ValueError('run: instances hash differs from run_meta.json')
    instances = _indexed([parse_extraction(line) for line in instance_bytes.decode('utf-8').splitlines()
                          if line.strip()], 'instances')
    selection_bytes = Path(selection_path).read_bytes()
    selected = _indexed(csv.DictReader(io.StringIO(selection_bytes.decode('utf-8'))), 'selection')
    trajectory_paths = list(source.glob('*/*.traj.json'))
    trajectories = {path.parent.name: path for path in trajectory_paths}
    if len(trajectories) != len(trajectory_paths):
        raise ValueError('run: duplicate trajectories for a task')
    if set(trajectories) != set(selected) or set(instances) != set(selected):
        raise ValueError('run: trajectories, instances and selection must cover exactly the same tasks')
    if set(meta['images']) != set(selected):
        raise ValueError('run: image inventory differs from selection')
    instructions = (ROOT / 'pilot-a/extract_prompt.md').read_text(encoding='utf-8')
    files = {'run_meta.json': meta_bytes, 'instances.jsonl': instance_bytes, 'selection.csv': selection_bytes,
             'extract_prompt.md': instructions.encode('utf-8')}
    tasks = list()
    for identifier, row in sorted(selected.items()):
        instance = instances[identifier]
        repository = row['same_pr_group'].split('#', 1)[0]
        if instance['base_commit'] != row['base_commit'] or instance['repo'] != repository:
            raise ValueError(f'{identifier}: selected source/repository differs from instance')
        trajectory_path = trajectories[identifier]
        trajectory_bytes = trajectory_path.read_bytes()
        trajectory = parse_extraction(trajectory_bytes.decode('utf-8'))
        if not isinstance(trajectory, dict) or trajectory.get('instance_id') != identifier:
            raise ValueError(f'{identifier}: trajectory task mismatch')
        if not isinstance(trajectory.get('messages'), list):
            raise ValueError(f'{identifier}: expected trajectory messages')
        workspace_path = trajectory_path.parent / 'final_workspace.json'
        if not workspace_path.is_file():
            raise ValueError(f'{identifier}: missing replay report')
        workspace_bytes = workspace_path.read_bytes()
        workspace = parse_extraction(workspace_bytes.decode('utf-8'))
        image = meta['images'][identifier]
        if any(workspace.get(key) != expected for key, expected in [
                ('instance_id', identifier), ('base_commit', row['base_commit']), ('image', image['image'])]):
            raise ValueError(f'{identifier}: replay report identity mismatch')
        if instance['image_name'] != image['image'] or row['image'] != image['image']:
            raise ValueError(f'{identifier}: selected image differs from run')
        prompt = build_extract_prompt(trajectory, ROOT / 'pilot-a/extract_prompt.md')
        prefix = f'inputs/{identifier}'
        files[f'{prefix}/trajectory.json'] = trajectory_bytes
        files[f'{prefix}/final_workspace.json'] = workspace_bytes
        files[f'prompts/{identifier}.txt'] = prompt.encode('utf-8')
        tasks.append({'task_id': identifier, 'repository': repository, 'source_revision': row['base_commit'],
                      'agent_run_id': meta['run'], 'image': image,
                      'trajectory': f'{prefix}/trajectory.json', 'prompt': f'prompts/{identifier}.txt',
                      'message_count': len(trajectory['messages']), 'prompt_characters': len(prompt),
                      'exit_status': trajectory.get('info', {}).get('exit_status'),
                      'workspace': {'report': f'{prefix}/final_workspace.json', 'evidence_type': 'reported_replay',
                                    'exit_code_mismatches': workspace.get('exit_code_mismatches'),
                                    'patch_applies': workspace.get('patch_applies'),
                                    'tracked_diff_same': workspace.get('tracked_diff_same')}})
    inventory = {'run_id': meta['run'], 'agent_model': meta['model'], 'tasks': tasks,
                 'source_validity': 'not_assessed', 'commands_executed': False,
                 'workspace_note': 'Reports describe Lane R replay; no captured filesystem is included or revalidated here.'}
    files['inventory.json'] = _json_bytes(inventory)
    write_bundle(output_dir, files, {'artifact_type': 'imported_pilot_a_run', 'run_id': meta['run']})
    return inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--selection', default=ROOT / 'pilot-a/clusters.csv')
    parser.add_argument('--instances', default=ROOT / 'pilot-a/instances/main/instances.jsonl')
    args = parser.parse_args()
    result = prepare_run(args.run_dir, args.output_dir, args.selection, args.instances)
    print(f"Prepared {len(result['tasks'])} trajectories; no model or repository commands executed.")


if __name__ == '__main__':
    main()
