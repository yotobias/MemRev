import json


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


if __name__ == "__main__":
    trajectory = load_trajectory("pilot-a/fixtures/test/full_trajectory_example.traj.json")
    print_messages(trajectory)

