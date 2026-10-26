#!/usr/bin/env bash
# One-time WSL setup for Pilot A Lane R. Safe to re-run.
# Run inside WSL from the project root:  bash pilot-a/scripts/setup_wsl.sh
set -euo pipefail

UV_VERSION=0.12.21          # same as uv on Windows; bump deliberately
WSL_MEMORY=24GB

if ! command -v wslpath >/dev/null || ! command -v cmd.exe >/dev/null; then
    echo "This setup script requires WSL with Windows interoperability. See pilot-a/RUN_READINESS.md for native Linux."
    exit 2
fi
# Keep a newly provisioned WSL environment off the Windows checkout by default.
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-$HOME/.venvs/paper2027-pilot-a}"
source "$(dirname "$0")/env.sh"
cd "$PILOT_ROOT"

echo "== 1. uv $UV_VERSION"
if ! command -v uv >/dev/null || [[ "$(uv --version | awk '{print $2}')" != "$UV_VERSION" ]]; then
    curl -LsSf "https://astral.sh/uv/$UV_VERSION/install.sh" | env UV_NO_MODIFY_PATH=1 sh
fi
uv --version

echo "== 2. .wslconfig (Windows side)"
win_profile="$(wslpath "$(cmd.exe /c 'echo %USERPROFILE%' 2>/dev/null | tr -d '\r')")"
wslconfig="$win_profile/.wslconfig"
if [[ ! -f "$wslconfig" ]]; then
    printf '[wsl2]\r\nmemory=%s\r\n' "$WSL_MEMORY" > "$wslconfig"
    echo "wrote $wslconfig; run 'wsl --shutdown' from Windows for it to take effect"
elif ! grep -qi "^memory" "$wslconfig"; then
    echo "WARNING: $wslconfig exists without a memory= line; add 'memory=$WSL_MEMORY' under [wsl2] by hand"
else
    echo "exists: $(grep -i '^memory' "$wslconfig" | tr -d '\r')"
fi
echo "WSL currently sees: $(free -g | awk '/^Mem:/{print $2}') GB"

echo "== 3. Python env ($UV_PROJECT_ENVIRONMENT)"
uv python pin 3.12 >/dev/null
# Install exactly the committed uv.lock; never re-resolve here (re-locking is a deliberate,
# logged step: edit pyproject.toml, run `uv lock`, note it in pilot-a/CHANGES.md).
uv sync --locked
uv run --locked python -c "import importlib.metadata as m; print('mini-swe-agent', m.version('mini-swe-agent'))"
uv run --locked mini-extra --help >/dev/null && echo "mini-extra OK"

echo "== 4. Docker"
docker run --rm hello-world | grep -m1 "Hello from Docker"
docker info --format 'docker {{.ServerVersion}}, {{.NCPU}} CPUs, {{.MemTotal}} bytes RAM, root {{.DockerRootDir}}'
