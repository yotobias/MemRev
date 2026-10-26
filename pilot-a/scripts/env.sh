# Shared settings for Lane R scripts. Source it, do not run it:
#   source pilot-a/scripts/env.sh
# Must be sourced from inside WSL.

# Project root = two levels above this file.
PILOT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PILOT_ROOT

# pyproject.toml and uv.lock live in the repo (on the Windows drive); the venv
# lives on the Linux filesystem, which is much faster and keeps Linux symlinks
# out of the Windows folder.
export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/paper2027-pilot-a"
export PATH="$HOME/.local/bin:$PATH"
