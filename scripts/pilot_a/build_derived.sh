#!/usr/bin/env bash
# Rebuild the compiled parts of a task's package inside its image and save the result
# as a local derived image  pilot-a/<owner>.<repo>-<n>:built.  The original image is untouched.
#   bash scripts/pilot_a/build_derived.sh <instance_id> <image>
#
# Why: the jiayuanz3 images compile the package (pip install -e .) and then run a
# history-cutoff step whose `git clean -fdx` deletes the compiled extensions, so e.g.
# `import sklearn` fails. The SCB harness repairs this before grading with the command
# mirrored below (swebench_memory/harness/run_evaluation.py, _python_rebuild_command).
# matplotlib with meson-python is installed non-editable in those images; here it is
# reinstalled editable, so that edits in /testbed take effect for the agent.
set -euo pipefail
source "$(dirname "$0")/env.sh"

iid=$1 image=$2
tag="pilot-a/${iid/__/.}:built"   # same rule as derived_tag() in naming.py
name="pa-build-${iid/__/-}"

rebuild='set -e
cd /testbed
if [ -s /constraints.txt ]; then export PIP_CONSTRAINT=/constraints.txt; fi
if [ -d sklearn ]; then export CFLAGS=-Wno-error=incompatible-pointer-types; fi
pip=/opt/conda/envs/testbed/bin/pip
log=/tmp/pilot-a-build.log
try() { echo "+ $*"; "$@" > $log 2>&1 && return 0; tail -5 $log; return 1; }
if grep -q "meson-python" pyproject.toml 2>/dev/null; then
    $pip uninstall -y matplotlib > /dev/null 2>&1 || true
    try $pip install -e . --no-build-isolation --no-deps
else
    try $pip install -e . --no-build-isolation --no-deps \
      || try $pip install -e . --no-deps \
      || try /opt/conda/envs/testbed/bin/python setup.py develop
fi
rm -f $log
# The tree was clean before the build, so anything untracked now is a build artefact
# (e.g. meson subprojects/.wraplock). Hide it via the local exclude file so it cannot
# enter the agent patch (mini-swe-agent submits `git add -A` output); no tracked file changes.
git status --porcelain | sed -n "s/^?? //p" | while read -r p; do
    echo "/$p" >> .git/info/exclude; echo "excluded build artefact: $p"; done
echo "git status after build: $(git status --porcelain | wc -l) entries"'

docker rm -f "$name" >/dev/null 2>&1 || true
start=$(date +%s)
# No -e here and CMD reset on commit: docker commit saves the container's command and
# env vars into the new image, which must keep the original image's config. (The build
# needs no BASH_ENV: pip is called by absolute path, and the image PATH puts testbed first.)
docker run --name "$name" "$image" bash -c "$rebuild"
docker commit --change 'CMD ["/bin/bash"]' \
    -m "pilot-a: rebuild package after history cutoff (scripts/pilot_a/build_derived.sh)" "$name" "$tag" >/dev/null
docker rm "$name" >/dev/null
echo "$iid: built $tag from $image in $(( $(date +%s) - start ))s"
