#!/usr/bin/env bash
# Environment fingerprint of one task image -> pilot-a/env/<instance_id>.json (+ .pip-freeze.txt)
#   bash pilot-a/scripts/fingerprint.sh <instance_id> <image> <base_commit>
# Runs the probe the way mini-swe-agent runs commands: bash -c with BASH_ENV=/root/.bashrc,
# which activates the testbed conda env in both image families.
set -euo pipefail
source "$(dirname "$0")/env.sh"

iid=$1 image=$2 base=$3
out="$PILOT_ROOT/pilot-a/env"; mkdir -p "$out"
case $iid in   # import check: the package, plus a compiled module where it has one
    scikit-learn__*) pkg=sklearn;    imp="import sklearn, sklearn.utils.murmurhash" ;;
    matplotlib__*)   pkg=matplotlib; imp="import matplotlib; from matplotlib import ft2font" ;;
    psf__requests-*) pkg=requests;   imp="import requests" ;;
    pallets__flask-*) pkg=flask;     imp="import flask" ;;
    *)               pkg=${iid%%__*}; imp="import $pkg" ;;
esac

inside=$(docker run --rm -e BASH_ENV=/root/.bashrc "$image" bash -c "
cd /testbed
echo \"head=\$(git rev-parse HEAD)\"
echo \"head_subject=\$(git log -1 --format=%s)\"
if git cat-file -e '$base^{commit}' 2>/dev/null; then
  echo base_present=true
  echo \"commits_above_base=\$(git rev-list --count '$base'..HEAD)\"
  echo \"diff_base_head=\$(git diff --shortstat '$base' HEAD)\"
  echo \"content_lines_changed_base_head=\$(git diff --numstat '$base' HEAD | awk '{s+=\$1+\$2} END {print s+0}')\"
  # Commits the agent could reach (git log --all) that are not ancestors of base_commit.
  # future = committed after base (1 is the swebench mode-only commit); side = older,
  # e.g. maintenance-branch release tags, harmless.
  bdate=\$(git log -1 --format=%cI '$base')
  echo \"future_commits=\$(git rev-list --count --all --not '$base' --since=\"\$bdate\")\"
  echo \"side_commits=\$(git rev-list --count --all --not '$base' --until=\"\$bdate\")\"
else
  echo base_present=false
fi
echo \"dirty_files=\$(git status --porcelain | wc -l)\"
if err=\$(python -c '$imp' 2>&1); then echo import_ok=true; else echo import_ok=false; echo \"import_error=\$(echo \"\$err\" | grep -E '^[A-Za-z]*Error' | tail -1)\"; fi
echo \"import_path=\$(python -c 'import $pkg; print($pkg.__file__)' 2>/dev/null)\"
echo \"python_path=\$(which python)\"
echo \"python_version=\$(python --version 2>&1)\"
echo \"conda_env=\${CONDA_DEFAULT_ENV:-}\"
echo '--- pip freeze'
python -m pip freeze 2>/dev/null
")

kv=${inside%%--- pip freeze*}
freeze=${inside#*--- pip freeze}; freeze=${freeze#$'\n'}
printf '%s\n' "$freeze" > "$out/$iid.pip-freeze.txt"

IID=$iid IMAGE=$image BASE=$base KV=$kv \
DIGEST=$(docker image inspect --format '{{index .RepoDigests 0}}' "$image") \
IMAGE_ID=$(docker image inspect --format '{{.Id}}' "$image") \
SIZE=$(docker image inspect --format '{{.Size}}' "$image") \
FREEZE_SHA=$(sha256sum < "$out/$iid.pip-freeze.txt" | cut -d' ' -f1) \
FREEZE_N=$(grep -c . "$out/$iid.pip-freeze.txt" || true) \
"$UV_PROJECT_ENVIRONMENT/bin/python" -I -c '
import json, os, datetime
e = os.environ
d = {"instance_id": e["IID"], "image": e["IMAGE"], "repo_digest": e["DIGEST"],
     "image_id": e["IMAGE_ID"], "size_bytes": int(e["SIZE"]), "base_commit": e["BASE"]}
for line in e["KV"].strip().splitlines():
    k, _, v = line.partition("=")
    d[k] = {"true": True, "false": False}.get(v, int(v) if v.isdigit() and k != "head" else v)
d["pip_freeze_sha256"] = e["FREEZE_SHA"]
d["pip_freeze_packages"] = int(e["FREEZE_N"])
d["head_is_base"] = d["head"] == d["base_commit"]
d["import_from_testbed"] = d.get("import_path", "").startswith("/testbed/")
d["fingerprinted_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
print(json.dumps(d, indent=2))
' > "$out/$iid.json"

echo "$iid: $(grep -E '"(python_version|commits_above_base|content_lines_changed_base_head|future_commits|dirty_files|import_ok|import_from_testbed)"' "$out/$iid.json" | tr -d ' \n')"
