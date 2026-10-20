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
        role, content = message["role"], message["content"]
        sb.write(f"--- Message {index} | {role}")
        sb.write("\n\n")
        sb.write(content)
        sb.write("\n\n")
    
    result = sb.getvalue()
    if output is not None:
        sb.seek(0)
        with open(output, "w", encoding="utf-8") as f:
            shutil.copyfileobj(sb, f)
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
    test_file = 'message_only_github_issue.traj'
    path = f'{test_dir}{test_file}.json'
    trajectory = load_trajectory(path)
    
    prompt = build_extract_prompt(trajectory, "pilot-a/extract_prompt.md")
    output_path = Path("runs/extraction_prompt.txt")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(prompt, encoding="utf-8")
    print(f"Saved extraction prompt to {output_path}")
