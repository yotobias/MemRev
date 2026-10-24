#!/usr/bin/env bash
# Run mini-swe-agent on an instance set, with the shipped swebench config unchanged.
#   bash pilot-a/scripts/run_agent.sh <set> <model> <run_name> [workers]
#   e.g.  bash pilot-a/scripts/run_agent.sh smoke claude-haiku-5-5 smoke-1
#         bash pilot-a/scripts/run_agent.sh main claude-sonnet-5-5 main-1 2
# Output: pilot-a/runs/<model>/<run_name>/ (refuses to reuse an existing directory).
# Needs ANTHROPIC_API_KEY in <project root>/.env (git-ignored); the key is never printed.
#
# No -c option: mini-extra replaces the default config when -c is given, which would drop
# the shipped swebench.yaml (prompts, limits, BASH_ENV). No temperature: current Claude
# models reject non-default sampling (pilot-a/CHANGES.md).
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$PILOT_ROOT"

set_name=$1 model=$2 run=$3 workers=${4:-1} extra=${5:-}
subset="pilot-a/instances/$set_name"
# Optional 5th argument: a settings file merged on top of the shipped config (pilot-a/config/).
config_args=()
if [[ -n $extra ]]; then
    [[ -f $extra ]] || { echo "no settings file $extra"; exit 2; }
    config_args=(-c swebench.yaml -c "$extra")
fi
out="pilot-a/runs/$model/$run"
[[ -f $subset/instances.jsonl ]] || { echo "no instance set $subset"; exit 2; }
[[ -e $out ]] && { echo "$out exists; every run gets a fresh directory"; exit 2; }

[[ -f .env ]] || { echo "missing .env with ANTHROPIC_API_KEY"; exit 2; }
# tolerate Windows line endings and spaces around '=' (KEY = value)
set -a; source <(tr -d '\r' < .env | sed -E 's/^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=[[:space:]]*/\1=/'); set +a
[[ -n ${ANTHROPIC_API_KEY:-} ]] || { echo ".env has no ANTHROPIC_API_KEY"; exit 2; }

# What produced this run, for the report and for reruns. The run directory is created
# only after every image is found locally, so a failed check leaves nothing behind.
SUBSET=$subset MODEL=$model RUN=$run WORKERS=$workers OUT=$out EXTRA=$extra "$UV_PROJECT_ENVIRONMENT/bin/python" -I - <<'PY'
import datetime, hashlib, importlib.metadata as md, json, os, pathlib, subprocess
e = os.environ
inst = [json.loads(l) for l in open(pathlib.Path(e["SUBSET"]) / "instances.jsonl")]
sha = lambda p: hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
images = {}
for i in inst:
    img = i["image_name"]
    images[i["instance_id"]] = {"image": img, "image_id": subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", img], capture_output=True, text=True).stdout.strip()}
meta = {"run": e["RUN"], "model": f"anthropic/{e['MODEL']}", "instance_set": e["SUBSET"],
        "workers": int(e["WORKERS"]),
        "config": f"minisweagent swebench.yaml as shipped + {e['EXTRA']}" if e["EXTRA"]
                  else "minisweagent swebench.yaml as shipped (no -c)",
        "extra_config": pathlib.Path(e["EXTRA"]).read_text() if e["EXTRA"] else None,
        "temperature": "not set (provider default)",
        "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "versions": {p: md.version(p) for p in ["mini-swe-agent", "litellm", "datasets"]},
        "instances_sha256": sha(pathlib.Path(e["SUBSET"]) / "instances.jsonl"),
        "uv_lock_sha256": sha("uv.lock"), "images": images}
missing = [k for k, v in images.items() if not v["image_id"]]
if missing:
    raise SystemExit(f"images not present locally: {missing}")
out = pathlib.Path(e["OUT"]); out.mkdir(parents=True)
json.dump(meta, open(out / "run_meta.json", "w"), indent=2)
PY

echo "running $set_name with anthropic/$model -> $out"
# --locked: refuse to start if uv.lock is out of date, instead of silently re-resolving
# packages (run_meta.json records the versions installed before this line).
uv run --locked mini-extra swebench --subset "$subset" --split train --workers "$workers" \
    "${config_args[@]}" -m "anthropic/$model" -o "$out" 2>&1 | tee "$out/console.log"
