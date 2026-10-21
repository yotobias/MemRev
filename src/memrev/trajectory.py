import json
from pathlib import Path


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
        

import io
import shutil
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

if __name__ == "__main__":
    test_dir = 'pilot-a/fixtures/test/'
    # test_file = 'message_only_github_issue.traj.json'
    test_file = 'full_trajectory_example.traj.json'
    path = f'{test_dir}{test_file}'
    trajectory = load_trajectory(path)
    
    prompt = build_extract_prompt(trajectory, "pilot-a/extract_prompt.md")
    output_path = Path("runs/extraction_prompt.txt")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(prompt, encoding="utf-8")
    print(f"Saved extraction prompt to {output_path}")
