"""Persist attempts before calling models; resume without repeating completed responses."""

from datetime import datetime, timezone
import math
import os
from pathlib import Path
import tempfile
import time

from memrev.handoff_io import json_file, load_bundle, read_json, write_bundle
from memrev.model_client import ModelCallError
from memrev.provenance import _json_bytes


def write_file(path, content, replace=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not replace:
        if path.read_bytes() != content:
            raise FileExistsError(f'Refusing to overwrite changed artifact: {path}')
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            if replace:
                os.replace(temporary, path)
            else:
                os.link(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def now():
    return datetime.now(timezone.utc).isoformat()


def call_count(output):
    return len(list((output / 'calls').glob('*/*/*/request.json')))


def obtain_response(output, request, config, client, retry_unknown=False):
    stage_dir = output / 'calls' / request['task_id'] / request['stage']
    for number in range(1, config['max_attempts'] + 1):
        attempt = stage_dir / str(number)
        request_path = attempt / 'request.json'
        if request_path.exists():
            if read_json(request_path)['request'] != request:
                raise ValueError('Saved request differs from current inputs')
            if not (attempt / 'result').exists():
                if retry_unknown:
                    continue
                raise ValueError('Request outcome unknown after interruption; inspect provider logs before --retry-unknown')
            _, files = load_bundle(attempt / 'result')
            if 'response.json' in files:
                return json_file(files, 'response.json')
            error = json_file(files, 'error.json')
            if error['retryable']:
                continue
            raise ValueError(f"Model call failed: {error['kind']}; use a new run after correcting settings")
        if call_count(output) >= config['max_calls']:
            raise ValueError('Run call limit reached (including failed/unknown attempts)')
        write_file(request_path, _json_bytes({'started_at': now(), 'request': request}))
        try:
            response = client(request)
        except ModelCallError as error:
            write_bundle(attempt / 'result', {'error.json': _json_bytes({
                'kind': error.kind, 'retryable': error.retryable, 'cost_usd': None})}, {'finished_at': now()})
            if not error.retryable:
                raise ValueError(f'Model call failed: {error.kind}') from None
            if number < config['max_attempts']:
                time.sleep(min(number, 5))
            continue
        # Unexpected client exceptions/crashes leave an unknown attempt, never an automatic duplicate call.
        write_bundle(attempt / 'result', {'response.json': _json_bytes(response)}, {'finished_at': now()})
        return response
    raise ValueError('Maximum attempts reached for this stage')


def usage_summary(output):
    calls = []
    for path in sorted((output / 'calls').glob('*/*/*/request.json')):
        row = {'task_id': path.parents[2].name, 'stage': path.parents[1].name,
               'attempt': int(path.parent.name), 'cost_usd': None, 'cost_basis': 'unknown',
               'input_tokens': None, 'output_tokens': None, 'outcome': 'unknown'}
        if (path.parent / 'result').exists():
            _, files = load_bundle(path.parent / 'result')
            if 'response.json' in files:
                response = json_file(files, 'response.json')
                row.update({key: response.get(key) for key in ['cost_usd', 'cost_basis', 'input_tokens', 'output_tokens']})
                cost = row['cost_usd']
                if type(cost) not in [int, float] or not math.isfinite(cost) or cost < 0:
                    row.update(cost_usd=None, cost_basis='unknown')
                row['outcome'] = 'response_received'
            else:
                row['outcome'] = 'transport_error'
        calls.append(row)
    return {'calls': calls, 'known_estimated_cost_usd': sum(row['cost_usd'] for row in calls if row['cost_usd'] is not None),
            'unknown_cost_calls': sum(row['cost_usd'] is None for row in calls),
            'note': 'Includes unsuccessful attempts when usage is available. Estimates are not provider invoices; unknown is not zero.'}
