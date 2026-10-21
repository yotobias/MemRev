import copy
import json
from pathlib import Path

import pytest

from memrev.trajectory import build_extract_prompt, format_message, format_transcript, load_trajectory


ROOT = Path(__file__).resolve().parents[1]


def test_tool_call_without_text_preserves_actions_and_input():
    message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "call-a", "function": {"name": "bash", "arguments": '{"command":"pytest"}'}},
            {"id": "call-b", "function": {"name": "bash", "arguments": '{"command":"git diff"}'}},
        ],
        "extra": {"actions": [{"command": "pytest"}], "response": "RAW_RESPONSE"},
        "provider_specific_fields": {"opaque": "PROVIDER_DATA"},
    }
    original = copy.deepcopy(message)
    result = format_message(message, 5)
    for value in ["Message 5 | assistant", "[No text content]", "call-a", "call-b", "pytest", "git diff", "Parsed actions"]:
        assert value in result
    assert "RAW_RESPONSE" not in result
    assert "PROVIDER_DATA" not in result
    assert message == original


def test_tool_observation_preserves_connection_and_execution_metadata():
    result = format_message({
        "role": "tool",
        "content": "output",
        "tool_call_id": "call-a",
        "extra": {"returncode": 0, "raw_output": "raw output", "exception_type": "ExampleError", "exception_info": "details"},
    }, 6)
    for value in ["call-a", '"returncode": 0', "raw output", "ExampleError", "details"]:
        assert value in result


def test_reasoning_is_labeled_and_not_duplicated():
    result = format_message({
        "role": "assistant",
        "reasoning_content": "A hypothesis about the code",
        "thinking_blocks": [{"type": "thinking", "thinking": "A hypothesis about the code", "signature": "OPAQUE_SIGNATURE"}],
    }, 3)
    assert result.count("A hypothesis about the code") == 1
    assert "not execution evidence" in result
    assert "OPAQUE_SIGNATURE" not in result


def test_thinking_text_fallback_ignores_opaque_blocks():
    result = format_message({
        "role": "assistant",
        "extra": None,
        "thinking_blocks": [
            {"type": "thinking", "thinking": "Fallback reasoning", "signature": "OPAQUE_SIGNATURE"},
            {"type": "redacted_thinking", "data": "OPAQUE_DATA"},
        ],
    }, 4)
    assert "Fallback reasoning" in result
    assert "OPAQUE_SIGNATURE" not in result
    assert "OPAQUE_DATA" not in result


@pytest.mark.parametrize("content", ["Plain text café", [{"type": "text", "text": "café"}], {"text": "café"}])
def test_text_and_structured_content(content):
    result = format_message({"role": "user", "content": content}, 0)
    assert (content if isinstance(content, str) else json.dumps(content, indent=2, ensure_ascii=False)) in result


@pytest.mark.parametrize("message", [{"role": "user", "content": 42}, {"role": "user", "extra": []}])
def test_malformed_fields_report_message_index(message):
    with pytest.raises(ValueError, match="Message 7"):
        format_message(message, 7)


def test_legacy_call_and_exit_metadata():
    call = format_message({"role": "assistant", "function_call": {"name": "bash", "arguments": "ls"}}, 1)
    assert "Legacy function call" in call
    assert '"arguments": "ls"' in call
    exit_message = format_message({"role": "exit", "extra": {"exit_status": "Submitted", "submission": "example patch"}}, 2)
    assert "Submitted" in exit_message
    assert "example patch" in exit_message


@pytest.mark.parametrize("filename,count", [("message_only_github_issue.traj.json", 22), ("full_trajectory_example.traj.json", 78)])
def test_real_fixtures_preserve_indices_calls_and_saved_output(filename, count, tmp_path):
    trajectory = load_trajectory(ROOT / "pilot-a/fixtures/test" / filename)
    original = copy.deepcopy(trajectory)
    output = tmp_path / "transcript.txt"
    result = format_transcript(trajectory, output)
    headers = [line for line in result.splitlines() if line.startswith("--- Message ")]
    assert headers == [f"--- Message {i} | {m['role']} ---" for i, m in enumerate(trajectory['messages'])]
    assert len(headers) == count
    for message in trajectory['messages']:
        for call in message.get('tool_calls') or []:
            assert call['id'] in result
    assert output.read_bytes() == result.encode('utf-8')
    assert trajectory == original
    prompt = build_extract_prompt(trajectory, ROOT / "pilot-a/extract_prompt.md")
    assert '<trajectory>\n' + result + '</trajectory>' in prompt
