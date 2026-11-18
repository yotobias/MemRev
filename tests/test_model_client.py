import sys
from types import SimpleNamespace

import pytest

from memrev.model_client import LiteLLMClient, ModelCallError


@pytest.fixture
def transport(monkeypatch):
    calls = []
    response = {'model': 'reported-snapshot', 'choices': [{'finish_reason': 'stop', 'message': {'content': '{}'}}],
                'usage': {'prompt_tokens': 11, 'completion_tokens': 7}}
    def completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(model_dump=lambda **_: response)
    class Transient(Exception):
        pass
    module = SimpleNamespace(completion=completion, completion_cost=lambda **_: 0.01,
                             RateLimitError=Transient, ServiceUnavailableError=Transient,
                             Timeout=Transient, APIConnectionError=Transient)
    monkeypatch.setitem(sys.modules, 'litellm', module)
    monkeypatch.setenv('SYNTHETIC_KEY', 'fake-secret-for-test')
    request = {'stage': 'extract', 'model': {'provider': 'openai', 'model': 'requested-model',
               'api_key_env': 'SYNTHETIC_KEY', 'max_output_tokens': 1000, 'timeout_seconds': 10,
               'output_mode': 'json_schema'}, 'schema': {'type': 'object'},
               'messages': [{'role': 'system', 'content': 'JSON only'}, {'role': 'user', 'content': 'Task'}]}
    return calls, module, request, response


def test_adapter_sends_only_explicit_context_and_returns_reported_metadata(transport):
    calls, module, request, raw = transport
    result = LiteLLMClient()(request)
    kwargs = calls[0]
    assert kwargs['messages'] == request['messages']
    assert kwargs['custom_llm_provider'] == 'openai'
    assert kwargs['max_retries'] == kwargs['num_retries'] == 0
    assert kwargs['drop_params'] is False
    assert kwargs['caching'] is False
    assert kwargs['response_format']['json_schema']['strict'] is True
    assert not {'tools', 'previous_response_id', 'conversation'} & set(kwargs)
    assert result['model_id'] == 'reported-snapshot'
    assert result['input_tokens'] == 11
    assert result['cost_basis'] == 'litellm_estimate'
    assert 'fake-secret' not in str(result)


def test_provider_failure_never_persists_exception_message(transport):
    calls, module, request, raw = transport
    def fail(**kwargs):
        raise module.RateLimitError('Headers contain fake-secret-for-test')
    module.completion = fail
    with pytest.raises(ModelCallError) as caught:
        LiteLLMClient()(request)
    assert caught.value.retryable
    assert 'fake-secret' not in str(caught.value)


def test_unpriced_usage_stays_unknown_and_refusal_has_no_content(transport):
    calls, module, request, raw = transport
    def unpriced(**kwargs):
        raise ValueError('Unknown price')
    module.completion_cost = unpriced
    raw['choices'][0]['message']['refusal'] = 'Cannot comply'
    result = LiteLLMClient()(request)
    assert result['content'] is None
    assert result['cost_usd'] is None
    assert result['cost_basis'] == 'unknown'


def test_text_mode_does_not_silently_request_unsupported_schema(transport):
    calls, module, request, raw = transport
    request['model']['output_mode'] = 'text'
    request['model']['reasoning_effort'] = 'high'
    LiteLLMClient()(request)
    assert 'response_format' not in calls[0]
    assert calls[0]['reasoning_effort'] == 'high'
