"""One stateless LiteLLM request, with explicit settings and no hidden retry loop."""

import math
import os
import re

from memrev.provenance import _fields, _text


class ModelCallError(Exception):
    def __init__(self, kind, retryable=False):
        super().__init__(kind)
        self.kind = kind
        self.retryable = retryable


def validate_config(config):
    _fields(config, ['workflow_version', 'run_id', 'max_calls', 'max_attempts', 'extractor', 'reviewer'], 'config')
    if type(config['workflow_version']) is not int or config['workflow_version'] != 1:
        raise ValueError('config.workflow_version: expected 1')
    if not isinstance(config['run_id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]+', config['run_id']):
        raise ValueError('config.run_id: use letters, numbers, underscores or hyphens')
    for field in ['max_calls', 'max_attempts']:
        if type(config[field]) is not int or config[field] < 1:
            raise ValueError(f'config.{field}: expected positive integer')
    for role in ['extractor', 'reviewer']:
        spec = config[role]
        _fields(spec, ['provider', 'model', 'api_key_env', 'output_mode', 'max_output_tokens', 'timeout_seconds']
                + [key for key in ['temperature', 'reasoning_effort'] if key in spec], role)
        for field in ['provider', 'model', 'api_key_env']:
            _text(spec[field], f'{role}.{field}', nullable=False)
        if not re.fullmatch(r'[a-z][a-z0-9_]*', spec['provider']):
            raise ValueError(f'{role}.provider: expected LiteLLM provider name')
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*', spec['api_key_env']):
            raise ValueError(f'{role}.api_key_env: expected environment variable name, not a key')
        if spec['output_mode'] not in ['json_schema', 'json_object', 'text']:
            raise ValueError(f'{role}.output_mode: expected json_schema, json_object or text')
        for field in ['max_output_tokens', 'timeout_seconds']:
            if type(spec[field]) is not int or spec[field] < 1:
                raise ValueError(f'{role}.{field}: expected positive integer')
        if 'temperature' in spec and (type(spec['temperature']) not in [int, float]
                                     or not math.isfinite(spec['temperature']) or not 0 <= spec['temperature'] <= 2):
            raise ValueError(f'{role}.temperature: expected number between 0 and 2')
        if 'reasoning_effort' in spec:
            _text(spec['reasoning_effort'], f'{role}.reasoning_effort', nullable=False)
    if (config['extractor']['provider'], config['extractor']['model']) == (config['reviewer']['provider'], config['reviewer']['model']):
        raise ValueError('Choose different extractor and reviewer model identifiers')
    return config


class LiteLLMClient:
    def __call__(self, request):
        # Use the installed pricing map; importing this adapter must not fetch a remote map.
        os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
        import litellm

        spec = request['model']
        key = os.environ.get(spec['api_key_env'])
        if not key:
            raise ModelCallError('MissingCredential')
        kwargs = {'model': spec['model'], 'custom_llm_provider': spec['provider'], 'api_key': key,
                  'messages': request['messages'], 'max_tokens': spec['max_output_tokens'],
                  'timeout': spec['timeout_seconds'], 'num_retries': 0, 'max_retries': 0,
                  'drop_params': False, 'caching': False}
        for field in ['temperature', 'reasoning_effort']:
            if field in spec:
                kwargs[field] = spec[field]
        if spec['output_mode'] == 'json_schema':
            kwargs['response_format'] = {'type': 'json_schema', 'json_schema': {
                'name': 'pilot_a_' + request['stage'], 'strict': True, 'schema': request['schema']}}
        elif spec['output_mode'] == 'json_object':
            kwargs['response_format'] = {'type': 'json_object'}
        try:
            response = litellm.completion(**kwargs)
        except Exception as error:
            # Exception messages can contain request headers/keys. Persist only a safe category.
            retryable = isinstance(error, (litellm.RateLimitError, litellm.ServiceUnavailableError,
                                          litellm.Timeout, litellm.APIConnectionError))
            raise ModelCallError(type(error).__name__, retryable) from None
        raw = response.model_dump(mode='json')
        first = raw.get('choices', [{}])[0]
        message = first.get('message', {})
        usage = raw.get('usage') or {}
        cost = None
        try:
            estimate = litellm.completion_cost(completion_response=response)
            if type(estimate) in [int, float] and math.isfinite(estimate) and estimate >= 0:
                cost = estimate
        except Exception:
            pass  # Unsupported pricing is unknown, not zero.
        return {'content': None if message.get('refusal') else message.get('content'),
                'model_id': raw.get('model'), 'input_tokens': usage.get('prompt_tokens'),
                'output_tokens': usage.get('completion_tokens'), 'cost_usd': cost,
                'cost_basis': 'litellm_estimate' if cost is not None else 'unknown',
                'finish_reason': first.get('finish_reason'), 'raw_response': raw}
