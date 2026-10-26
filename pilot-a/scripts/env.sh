# Shared settings for Lane R scripts. Source it, do not run it:
#   source pilot-a/scripts/env.sh
# Source inside Linux or WSL.

# Project root = two levels above this file.
PILOT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PILOT_ROOT

# Respect an explicit choice. Prefer this checkout's existing environment, then
# Ocean's original WSL environment. New native Linux checkouts default to .venv.
if [[ -z ${UV_PROJECT_ENVIRONMENT:-} ]]; then
    if [[ -x "$PILOT_ROOT/.venv/bin/python" ]]; then
        UV_PROJECT_ENVIRONMENT="$PILOT_ROOT/.venv"
    elif [[ -x "$HOME/.venvs/paper2027-pilot-a/bin/python" ]]; then
        UV_PROJECT_ENVIRONMENT="$HOME/.venvs/paper2027-pilot-a"
    else
        UV_PROJECT_ENVIRONMENT="$PILOT_ROOT/.venv"
    fi
fi
export UV_PROJECT_ENVIRONMENT
export PATH="$HOME/.local/bin:$PATH"
