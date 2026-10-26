import argparse
import io
import json
from pathlib import Path
import shutil


def load_trajectory(path):
    """
    Load the full trajectory dictionary which may include:
    ["info", "messages", "trajectory_format"]
    
    ref: https://github.com/SWE-agent/mini-swe-agent/blob/v2.4.6/docs/usage/output_files.md
    """
    
    with open(path, 'r', encoding='utf-8') as file:
        traj = json.load(file)
        
    # Check if the provided path is a singular message file or full trajectory
    if isinstance(traj, dict):
        # Validate if messages is correct.
        if isinstance(traj.get("messages"), list):
            return traj
        else:
            raise ValueError('traj["messages"] is not a list')
    elif isinstance(traj, list):
        info, messages, trajectory_format = dict(), traj, ""
    else:
        raise ValueError("Incorrect Trajectory Parsing, it's neither a dictionary or list")
    
    trajectory = {
        "info": info,
        "messages" : messages,
        "trajectory_format" : trajectory_format
    }

    return trajectory

def print_messages(trajectory):
    """Print the messages stored in a local trajectory file"""
    for index, message in enumerate(trajectory["messages"]):
        role, content = message["role"], message["content"]
        print(index, role, content)

def extract_segment(trajectory, start_index=None, end_index=None):
    """Returns messages in a defined inclusive segment range"""
    messages = trajectory["messages"]
    if start_index >= 0 and start_index <= end_index and end_index < len(messages):
        segmented_messages = messages[start_index:end_index+1]
        
        result = list()
        for index, message in enumerate(segmented_messages, start=start_index):
            result.append({
                "message_index": index,
                "message": message
            })
        return result
    else:
        raise ValueError("extract_segment: invalidate segment range: expected 0 <= start_index <= end_index < message count")
        

def format_transcript(trajectory, output=None):
    """Returns a readable transcript of the messages"""
    messages = trajectory["messages"]
    
    sb = io.StringIO()
    
    for index, message in enumerate(messages):
        sb.write(format_message(message, index))
    
    result = sb.getvalue()
    if output is not None:
        sb.seek(0)
        with open(output, "w", encoding="utf-8") as f:
            shutil.copyfileobj(sb, f)
    sb.close()
    return result

def format_message(message, message_index):
    """Returns a readable representation of one original message."""
    if not isinstance(message, dict):
        raise ValueError(f"Message {message_index}: expected a dictionary")

    role, content = message.get("role", "unknown"), message.get("content")
    extra = message.get("extra")
    if extra is None:
        extra = dict()
    elif not isinstance(extra, dict):
        raise ValueError(f"Message {message_index}: extra must be a dictionary")

    if content is None:
        content = "[No text content]"
    elif isinstance(content, (list, dict)):
        content = json.dumps(content, indent=2, ensure_ascii=False)
    elif not isinstance(content, str):
        raise ValueError(f"Message {message_index}: unsupported content type")

    sections = [("Content", content)]

    # Keep action identifiers so tool observations can be traced to their calls.
    for field, label in [
        ("tool_calls", "Tool calls"),
        ("function_call", "Legacy function call"),
        ("tool_call_id", "Responds to tool call"),
    ]:
        value = message.get(field)
        if value is not None:
            sections.append((label, value))

    if extra.get("actions") is not None:
        sections.append(("Parsed actions", extra["actions"]))

    # Prefer the exposed reasoning text; thinking blocks often duplicate it.
    reasoning = message.get("reasoning_content")
    if not isinstance(reasoning, str) or not reasoning.strip():
        reasoning_parts = list()
        thinking_blocks = message.get("thinking_blocks")
        if isinstance(thinking_blocks, list):
            for block in thinking_blocks:
                if not isinstance(block, dict) or block.get("type") != "thinking":
                    continue
                text = block.get("thinking", block.get("text"))
                if isinstance(text, str) and text.strip() and text not in reasoning_parts:
                    reasoning_parts.append(text)
        reasoning = "\n\n".join(reasoning_parts)
    if reasoning:
        sections.append(("Agent reasoning (not execution evidence)", reasoning))

    # Select evidence fields instead of copying raw responses and provider data.
    execution = dict()
    for field in [
        "returncode", "exception", "exception_type", "exception_info",
        "raw_output", "exit_status", "submission",
    ]:
        if field in extra and extra[field] is not None:
            execution[field] = extra[field]
    if execution:
        sections.append(("Execution metadata", execution))

    sb = io.StringIO()
    sb.write(f"--- Message {message_index} | {role} ---\n\n")
    for label, value in sections:
        sb.write(f"{label}:\n")
        if isinstance(value, str):
            sb.write(value)
        else:
            sb.write(json.dumps(value, indent=2, ensure_ascii=False))
        sb.write("\n\n")

    result = sb.getvalue()
    sb.close()
    return result

def build_extract_prompt(trajectory, instructions):
    """Combines the extraction instruction w/ the formatted transcript"""
    
    with open(instructions, "r", encoding="utf-8") as file:
        instruction_prompt = file.read()

    transcript = format_transcript(trajectory)
    sb = io.StringIO()
    sb.write(instruction_prompt)
    sb.write("\n\n")
    sb.write("<trajectory>\n")
    sb.write(transcript)
    sb.write("</trajectory>")
    
    prompt = sb.getvalue()
    sb.close()
    return prompt

def parse_extraction(text):
    """Parse strict JSON, retaining the same rules for files and snapshots."""
    def read_object(pairs):
        result = dict()
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Extraction JSON: duplicate key {key!r}")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError(f"Extraction JSON: {value} is not a valid JSON constant")

    return json.loads(text, object_pairs_hook=read_object, parse_constant=reject_constant)


def load_extraction(extraction_file):
    """Load strict JSON without repairing or changing the model response."""
    with open(extraction_file, "r", encoding="utf-8") as file:
        return parse_extraction(file.read())


def _validate_fields(value, fields, path):
    """Require the documented raw-response fields, including nullable ones."""
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a dictionary")
    missing = set(fields) - set(value)
    if missing:
        raise ValueError(f"{path}: missing fields: {', '.join(sorted(missing))}")
    unexpected = set(value) - set(fields)
    if unexpected:
        raise ValueError(f"{path}: unexpected fields: {', '.join(sorted(map(str, unexpected)))}")


def _validate_text(value, path, nullable=False):
    if nullable and value is None:
        return
    if not isinstance(value, str) or not value.strip():
        expected = "a nonempty string or null" if nullable else "a nonempty string"
        raise ValueError(f"{path}: expected {expected}")


def _validate_choice(value, choices, path):
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"{path}: expected one of {', '.join(choices)}")


def _validate_assumption(assumption, message_count, path):
    _validate_fields(assumption, [
        "statement", "symbol", "file", "predicate", "kind", "scope",
        "evidence_message_indices", "evidence_basis", "workspace_context",
    ], path)
    for field in ["statement", "workspace_context"]:
        _validate_text(assumption[field], f"{path}.{field}")
    for field in ["symbol", "file"]:
        _validate_text(assumption[field], f"{path}.{field}", nullable=True)
    _validate_choice(assumption["predicate"], [
        "returns", "raises", "accepts", "mutates", "calls", "type_is", "default_is", "other",
    ], f"{path}.predicate")
    _validate_choice(assumption["kind"], [
        "repo_behaviour", "procedure", "environment",
    ], f"{path}.kind")

    scope = assumption["scope"]
    _validate_fields(scope, ["inputs", "config", "env"], f"{path}.scope")
    for field in ["inputs", "config", "env"]:
        _validate_text(scope[field], f"{path}.scope.{field}", nullable=True)

    basis = assumption["evidence_basis"]
    _validate_choice(basis, [
        "execution_observation", "code_observation", "unverified_assertion", "no_evidence",
    ], f"{path}.evidence_basis")
    indices = assumption["evidence_message_indices"]
    index_path = f"{path}.evidence_message_indices"
    if not isinstance(indices, list):
        raise ValueError(f"{index_path}: expected a list")
    if basis == "no_evidence":
        if indices:
            raise ValueError(f"{index_path}: must be empty for no_evidence")
    elif not indices:
        raise ValueError(f"{index_path}: at least one citation is required for {basis}")

    seen = set()
    for position, index in enumerate(indices):
        if type(index) is not int:
            raise ValueError(f"{index_path}[{position}]: expected an integer, not a boolean or other type")
        if not 0 <= index < message_count:
            raise ValueError(f"{index_path}[{position}]: index {index} outside trajectory with {message_count} messages")
        if index in seen:
            raise ValueError(f"{index_path}[{position}]: duplicate index {index}")
        seen.add(index)


def validate_extraction(extraction, trajectory):
    """Validate raw v2 structure and citations, not truth; return input unchanged."""
    if not isinstance(trajectory, dict) or not isinstance(trajectory.get("messages"), list):
        raise ValueError("trajectory.messages: expected a list")
    _validate_fields(extraction, ["schema_version", "lessons"], "extraction")
    if type(extraction["schema_version"]) is not int or extraction["schema_version"] != 2:
        raise ValueError("extraction.schema_version: expected integer 2; legacy responses require explicit migration")
    lessons = extraction["lessons"]
    if not isinstance(lessons, list):
        raise ValueError("extraction.lessons: expected a list")

    for lesson_index, lesson in enumerate(lessons):
        path = f"lessons[{lesson_index}]"
        _validate_fields(lesson, ["advice", "from_failed_step", "assumptions"], path)
        _validate_text(lesson["advice"], f"{path}.advice")
        failed = lesson["from_failed_step"]
        if failed is not None and type(failed) is not bool:
            raise ValueError(f"{path}.from_failed_step: expected a boolean or null")
        assumptions = lesson["assumptions"]
        if not isinstance(assumptions, list):
            raise ValueError(f"{path}.assumptions: expected a list")
        for assumption_index, assumption in enumerate(assumptions):
            _validate_assumption(assumption, len(trajectory["messages"]), f"{path}.assumptions[{assumption_index}]")

    return extraction


def main():
    parser = argparse.ArgumentParser(description="Format a saved trajectory into an extraction prompt.")
    parser.add_argument("--trajectory", required=True, type=Path)
    parser.add_argument("--prompt-template", type=Path,
                        default=Path(__file__).resolve().parents[2] / "pilot-a/extract_prompt.md")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--extraction", type=Path, help="Optionally validate an existing response against this trajectory")
    args = parser.parse_args()
    try:
        trajectory = load_trajectory(args.trajectory)
        prompt = build_extract_prompt(trajectory, args.prompt_template)
        if args.extraction is not None:
            validate_extraction(load_extraction(args.extraction), trajectory)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(prompt)
    except (ValueError, OSError) as error:
        parser.exit(2, f"Cannot prepare prompt: {error}\n")
    print(f"Saved extraction prompt to {args.output.resolve()}")
    if args.extraction is not None:
        print("Extraction structure validated; semantic correctness remains unassessed.")


if __name__ == "__main__":
    main()
