"""Freeze Lane R work orders and record/validate returns. Never runs a repository check."""

import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import re
import tempfile

from memrev.handoff import build_handoff
from memrev.handoff_io import canonical_hash, check_version, json_file, load_bundle, read_json, write_bundle
from memrev.provenance import _fields, _json_bytes, _sha256, _text
from memrev.validity import REVISIONS, pending_cell, validate_validity
from memrev.workflow_io import write_file


PROFILE = 'pilot-a-lane-r-execution-v1'
ROLES = ['workspace', 'check_source', 'output', 'reconstruction', 'execution_record']
RESULTS = {'pass': 'supported', 'fail_on_asserted_target': 'contradicted',
           **{key: 'inconclusive' for key in ['setup_error', 'out_of_scope', 'flaky', 'timeout', 'unresolved']}}
ROOT = Path(__file__).resolve().parents[2]


def prepare_execution(handoff_dir, prepared_dir, output_dir):
    handoff_manifest, handoff = load_bundle(handoff_dir)
    prepared_manifest, prepared = load_bundle(prepared_dir)
    if prepared_manifest.get('artifact_type') != 'imported_pilot_a_run':
        raise ValueError('Expected imported trajectory bundle')
    collection = json_file(handoff, 'collection.json')
    collection_id = collection['collection_id']
    if collection_id != 'collection-' + canonical_hash(collection['identity']):
        raise ValueError('Collection identity mismatch')
    inventory = json_file(prepared, 'inventory.json')
    tasks = {task['task_id']: task for task in inventory['tasks']}
    if len(tasks) != len(inventory['tasks']):
        raise ValueError('Duplicate prepared tasks')
    rows = []
    for candidate in collection['candidates']:
        task = tasks.get(candidate['task_id'])
        if task is None or any(candidate[key] != task[key] for key in
                               ['repository', 'source_revision', 'agent_run_id']):
            raise ValueError('Candidate source/run does not match prepared task')
        if _sha256(handoff[candidate['trajectory_pointer']]) != _sha256(prepared[task['trajectory']]):
            raise ValueError('Candidate trajectory differs from prepared trajectory')
        scheduled = (candidate['original']['kind'] == 'repo_behaviour' and candidate['evaluation'] is not None
                     and candidate['evaluation']['outcome'] == 'usable_as_extracted')
        rows.append({'assumption_id': candidate['assumption_id'], 'task_id': candidate['task_id'],
                     'source_revision': candidate['source_revision'], 'image': task['image'],
                     'statement': candidate['original']['statement'], 'scope': candidate['original']['scope'],
                     'trajectory_pointer': 'handoff/' + candidate['trajectory_pointer'],
                     'scheduled': scheduled, 'initial_revisions': ['C0', 'C1'] if scheduled else [],
                     'Ca_when': 'C0 and C1 are both contradicted' if scheduled else None,
                     'reason': 'Usable repository candidate' if scheduled else 'Retained in denominator; not eligible for this execution schedule'})
    order = {'work_order_version': 1, 'profile': PROFILE, 'collection_id': collection_id,
             'status': 'producer_frozen', 'purpose': collection['purpose'], 'rows': rows,
             'initial_assessments': 2 * sum(row['scheduled'] for row in rows),
             'instructions': 'Use C0/C1 first; Ca only after both are contradicted. Preserve unscheduled rows as pending. '
                             'Evidence and official fixes stay private on R. No check was executed by preparation.'}
    pending = json_file(handoff, 'lane-r/validity.pending.json')
    candidates = {row['assumption_id']: row for row in collection['candidates']}
    validate_validity(pending, collection_id, candidates)
    files = {f'handoff/{name}': data for name, data in handoff.items()}
    files.update({f'prepared/{name}': data for name, data in prepared.items()})
    files.update({'handoff/manifest.json': _json_bytes(handoff_manifest),
                  'prepared/manifest.json': _json_bytes(prepared_manifest),
                  'work_order.json': _json_bytes(order), 'validity.pending.json': _json_bytes(pending),
                  'CONTRACT.md': (ROOT / 'pilot-a/LANE_R_CONTRACT.md').read_bytes()})
    # Ship a fixed, reviewable CLI snapshot so R is not blocked by an unpushed branch.
    for path in sorted((ROOT / 'src/memrev').iterdir()):
        if path.is_file() and path.suffix in ['.py', '.json']:
            files['runner/src/memrev/' + path.name] = path.read_bytes()
    for name in ['pyproject.toml', 'uv.lock', '.python-version', 'pilot-a/LANE_R_CONTRACT.md']:
        files['runner/' + name] = (ROOT / name).read_bytes()
    files['README.md'] = (
        '# Frozen Lane R execution handoff\n\n'
        'Read CONTRACT.md and work_order.json. No checks have been executed by this bundle. '
        'Use validity.pending.json as the starting return and fill receipt.template.json only after a real check.\n\n'
        'From this extracted directory, use your existing locked environment and '
        '`export PYTHONPATH="$PWD/runner/src"`, or install dependencies from runner/ with `uv sync --locked`. '
        'Then run `python -m memrev.lane_r validate --bundle . --return-file validity.pending.json`. '
        'The first validation succeeds with scheduled work pending. The copied source is a frozen local snapshot, '
        'not a claim that the branch has been published.\n\n'
        'Keep working returns and private evidence outside this directory. Send only the return JSON and validation '
        'summary to N; never send the private gold/check-output evidence store. The source trajectory and review '
        'limitations remain applicable; new extractions require new collection IDs.\n').encode()
    job = next((row for row in rows if row['scheduled']), None)
    if job is not None:
        template = {'receipt_version': 1, 'collection_id': collection_id, 'assumption_id': job['assumption_id'],
                    'revision': 'C0', 'workspace': {
                        'workspace_version': 1, 'task_id': job['task_id'], 'revision': 'C0',
                        'source_revision': job['source_revision'], 'image_id': job['image']['image_id'],
                        'reconstruction': None, 'tracked_diff_sha256': None,
                        'untracked_manifest_sha256': None, 'environment_sha256': None},
                    'assessor': {'id': None, 'type': 'ai', 'independent': False,
                                 'note': 'Fill in actual authorship, assessment process and prior exposure.'},
                    'reason': None, 'command': None, 'result': None, 'exit_code': None,
                    'evidence_files': {'check_source': None, 'output': None, 'reconstruction': None}}
        files['receipt.template.json'] = _json_bytes(template)
    write_bundle(output_dir, files, {'artifact_type': PROFILE, 'collection_id': collection_id})
    return order


def _load_order(bundle_dir):
    manifest, files = load_bundle(bundle_dir)
    if manifest.get('artifact_type') != PROFILE:
        raise ValueError('Expected Lane R execution bundle')
    order = json_file(files, 'work_order.json')
    if order['profile'] != PROFILE or order['collection_id'] != manifest['collection_id']:
        raise ValueError('Execution profile identity mismatch')
    return order, {row['assumption_id']: row for row in order['rows']}


def _workspace_id(workspace):
    return f"lane-r:{workspace['task_id']}:{workspace['revision']}:sha256:{_sha256(_json_bytes(workspace))}"


def _validate_workspace(workspace, job, revision):
    _fields(workspace, ['workspace_version', 'task_id', 'revision', 'source_revision', 'image_id',
                        'reconstruction', 'tracked_diff_sha256', 'untracked_manifest_sha256', 'environment_sha256'], 'workspace')
    check_version(workspace, 'workspace_version')
    if any(workspace[key] != expected for key, expected in [('task_id', job['task_id']), ('revision', revision),
            ('source_revision', job['source_revision']), ('image_id', job['image']['image_id'])]):
        raise ValueError('Workspace task/revision/source/image mismatch')
    _text(workspace['reconstruction'], 'workspace.reconstruction', nullable=False)
    for key in ['tracked_diff_sha256', 'untracked_manifest_sha256', 'environment_sha256']:
        if not isinstance(workspace[key], str) or not re.fullmatch(r'[0-9a-f]{64}', workspace[key]):
            raise ValueError(f'workspace.{key}: expected SHA-256')


def validate_return(bundle_dir, return_path, evidence_root=None):
    order, jobs = _load_order(bundle_dir)
    document = read_json(return_path)
    rows = validate_validity(document, order['collection_id'], jobs)
    counts = Counter()
    remaining = []
    for identifier, row in rows.items():
        job = jobs[identifier]
        ca_needed = all(row[revision]['outcome'] == 'contradicted' for revision in ['C0', 'C1'])
        for revision in REVISIONS:
            cell = row[revision]
            counts[cell['outcome']] += 1
            required = job['scheduled'] and (revision != 'Ca' or ca_needed)
            if required and cell['outcome'] == 'pending':
                remaining.append({'assumption_id': identifier, 'revision': revision})
            if cell['outcome'] == 'pending':
                continue
            if not job['scheduled']:
                raise ValueError('Unscheduled context/ineligible rows must remain pending under this profile')
            if revision == 'Ca' and not ca_needed:
                raise ValueError('Ca is scheduled only after C0 and C1 are contradicted')
            if cell['outcome'] == 'undefined':
                continue  # Explicit unavailable-Ca declaration, checked by the base contract.
            if cell['method'] != 'execution':
                raise ValueError('This profile records executions; non-execution judgments need a separately agreed profile')
            if cell['execution']['asserted_target'] != job['statement']:
                raise ValueError('asserted_target must preserve the original statement')
            prefix = f"lane-r:{job['task_id']}:{revision}:sha256:"
            if not cell['workspace'].startswith(prefix) or not re.fullmatch(r'[0-9a-f]{64}', cell['workspace'][len(prefix):]):
                raise ValueError('Invalid workspace identity for this task/revision')
            artifacts = {}
            for item in cell['evidence']:
                match = re.fullmatch(r'lane-r://sha256/([0-9a-f]{64})/([a-z_]+)', item['reference'])
                if match is None or match[1] != item['sha256'] or match[2] in artifacts:
                    raise ValueError('Invalid or duplicate private evidence reference')
                artifacts[match[2]] = item['sha256']
            if set(artifacts) != set(ROLES) or artifacts['workspace'] != cell['workspace'][len(prefix):]:
                raise ValueError('Evidence must identify workspace, check source, output, reconstruction and execution record')
            if evidence_root is not None:
                loaded = {}
                for role, digest in artifacts.items():
                    path = Path(evidence_root) / 'sha256' / digest
                    if not path.is_file() or _sha256(path.read_bytes()) != digest:
                        raise ValueError('Missing or changed private evidence: ' + role)
                    loaded[role] = path
                workspace = read_json(loaded['workspace'])
                _validate_workspace(workspace, job, revision)
                if _workspace_id(workspace) != cell['workspace']:
                    raise ValueError('Workspace manifest identity mismatch')
                audit = read_json(loaded['execution_record'])
                expected = _audit(order['collection_id'], identifier, revision, cell, artifacts)
                if audit != expected:
                    raise ValueError('Private execution record differs from shared outcome')
    return {'profile': PROFILE, 'collection_id': order['collection_id'], 'outcomes': dict(counts),
            'remaining_scheduled_cells': remaining, 'stage_complete': not remaining,
            'private_evidence_verified': evidence_root is not None, 'research_complete': False,
            'note': 'Validation checks identity and declarations, not whether the check proves the scientific claim.'}


def _audit(collection_id, identifier, revision, cell, artifacts):
    return {'execution_record_version': 1, 'collection_id': collection_id, 'assumption_id': identifier,
            'revision': revision, 'execution': cell['execution'], 'assessor': cell['assessor'],
            'reason': cell['reason'], 'workspace': cell['workspace'],
            'artifacts': {role: artifacts[role] for role in ROLES if role != 'execution_record'}}


def record_execution(bundle_dir, return_path, receipt_path, output_path, evidence_root):
    order, jobs = _load_order(bundle_dir)
    root = Path(bundle_dir).resolve()
    if Path(evidence_root).resolve().is_relative_to(root) or Path(output_path).resolve().is_relative_to(root):
        raise ValueError('Keep private evidence and working returns outside the frozen execution bundle')
    validate_return(bundle_dir, return_path, evidence_root)
    document = copy.deepcopy(read_json(return_path))
    receipt = read_json(receipt_path)
    _fields(receipt, ['receipt_version', 'collection_id', 'assumption_id', 'revision', 'workspace',
                     'assessor', 'reason', 'command', 'result', 'exit_code', 'evidence_files'], 'receipt')
    check_version(receipt, 'receipt_version')
    identifier, revision = receipt['assumption_id'], receipt['revision']
    if receipt['collection_id'] != order['collection_id'] or identifier not in jobs or revision not in REVISIONS:
        raise ValueError('Stale/unknown collection, assumption or revision')
    job = jobs[identifier]
    _validate_workspace(receipt['workspace'], job, revision)
    if receipt['result'] not in RESULTS:
        raise ValueError('Unknown or unfilled execution result')
    _fields(receipt['evidence_files'], ['check_source', 'output', 'reconstruction'], 'receipt.evidence_files')
    evidence_bytes = {'workspace': _json_bytes(receipt['workspace'])}
    for role, path in receipt['evidence_files'].items():
        _text(path, 'receipt evidence path', nullable=False)
        # Paths belong to the receipt file's directory; only R invokes this command on private material.
        evidence_bytes[role] = (Path(receipt_path).resolve().parent / path).read_bytes()
    digests = {role: _sha256(content) for role, content in evidence_bytes.items()}
    cell = {'outcome': RESULTS[receipt['result']], 'method': 'execution', 'assessor': receipt['assessor'],
            'workspace': _workspace_id(receipt['workspace']), 'reason': receipt['reason'], 'evidence': [],
            'execution': {'command': receipt['command'], 'asserted_target': job['statement'],
                          'result': receipt['result'], 'exit_code': receipt['exit_code']}}
    evidence_bytes['execution_record'] = _json_bytes(_audit(order['collection_id'], identifier, revision, cell, digests))
    digests['execution_record'] = _sha256(evidence_bytes['execution_record'])
    cell['evidence'] = [{'reference': f'lane-r://sha256/{digest}/{role}', 'sha256': digest}
                        for role, digest in digests.items()]
    row = next(row for row in document['rows'] if row['assumption_id'] == identifier)
    if row[revision] != pending_cell() and row[revision] != cell:
        raise ValueError('Cannot replace a completed cell silently; preserve the run and agree a new assessment version')
    row[revision] = cell
    # Validate before writing any public return. The temporary file contains only the blinded declaration.
    with tempfile.TemporaryDirectory() as temporary:
        check = Path(temporary) / 'return.json'
        check.write_bytes(_json_bytes(document))
        validate_return(bundle_dir, check)
    for role, content in evidence_bytes.items():
        write_file(Path(evidence_root) / 'sha256' / digests[role], content)
    write_file(output_path, _json_bytes(document))
    return validate_return(bundle_dir, output_path, evidence_root)


def import_return(bundle_dir, return_path, output_dir):
    validate_return(bundle_dir, return_path)
    root = Path(bundle_dir) / 'handoff'
    packages = sorted((root / 'acquisitions').iterdir())
    reviews = sorted((root / 'acquisitions').glob('*/evaluation.input.json'))
    return build_handoff(packages, output_dir, evaluations=reviews, validity_path=return_path,
                         selection_path=root / 'selection.csv')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare')
    prepare.add_argument('--handoff', required=True, type=Path)
    prepare.add_argument('--prepared', required=True, type=Path)
    prepare.add_argument('--output-dir', required=True, type=Path)
    for name in ['validate', 'record', 'import']:
        command = commands.add_parser(name)
        command.add_argument('--bundle', required=True, type=Path)
        command.add_argument('--return-file', required=True, type=Path)
        if name == 'validate': command.add_argument('--evidence-root', type=Path)
        if name == 'record':
            command.add_argument('--receipt', required=True, type=Path)
            command.add_argument('--evidence-root', required=True, type=Path)
            command.add_argument('--output', required=True, type=Path)
        if name == 'import': command.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            order = prepare_execution(args.handoff, args.prepared, args.output_dir)
            result = {'collection_id': order['collection_id'], 'rows': len(order['rows']),
                      'initial_assessments': order['initial_assessments'], 'checks_executed': 0}
        elif args.command == 'record':
            result = record_execution(args.bundle, args.return_file, args.receipt, args.output, args.evidence_root)
        elif args.command == 'import': result = import_return(args.bundle, args.return_file, args.output_dir)
        else: result = validate_return(args.bundle, args.return_file, args.evidence_root)
    except (ValueError, OSError, KeyError, TypeError) as error:
        # Do not print private evidence paths or provider/output contents in shared terminal logs.
        detail = str(error) if isinstance(error, ValueError) else 'Missing/unreadable input or malformed fields; inspect inputs locally.'
        parser.exit(2, f'Cannot {args.command} Lane R contract: {detail}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
