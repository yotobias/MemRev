#!/usr/bin/env bash
# Pull every image in pilot-a/clusters.csv and fingerprint it. Safe to re-run:
# docker pull is a no-op for an up-to-date image, and fingerprints are rewritten.
#   bash pilot-a/scripts/pull_images.sh            # all tasks
#   bash pilot-a/scripts/pull_images.sh <id> ...   # only these instance ids
set -uo pipefail
source "$(dirname "$0")/env.sh"
cd "$PILOT_ROOT"

overlap=pilot-a/data/lite_task_file_overlap.csv
failed=()
while IFS=, read -r iid _cluster _kind image _rest; do
    [[ $iid == instance_id ]] && continue
    [[ $# -gt 0 && " $* " != *" $iid "* ]] && continue
    base=$(awk -F, -v id="$iid" '$1 == id {print $4}' "$overlap")
    echo "== $(date +%H:%M:%S) $iid  $image"
    if ! docker pull -q "$image"; then failed+=("$iid (pull)"); continue; fi
    bash pilot-a/scripts/fingerprint.sh "$iid" "$image" "$base" || failed+=("$iid (fingerprint)")
done < <(tr -d '\r' < pilot-a/clusters.csv)

echo "== done $(date +%H:%M:%S); disk used by images: $(docker system df --format '{{.Type}} {{.Size}}' | grep Images)"
if (( ${#failed[@]} )); then printf 'FAILED: %s\n' "${failed[@]}"; exit 1; fi
