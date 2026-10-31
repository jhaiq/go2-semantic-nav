#!/usr/bin/env bash
# AGIROS loong migration verification ladder, executed inside Docker so the
# host needs no AGIROS installation.
#
# Steps (scene-migration verification ladder):
#   1/5 env      — source /opt/agiros/loong, assert ROS_DISTRO=loong + agiros CLI
#   2/5 deps     — agirosdep check --from-paths ros2_ws/src
#   3/5 build    — colcon build (full workspace, symlink install)
#   4/5 test     — colcon test + repo-root pytest suite
#   5/5 data     — smoke_test_integration.py: synthetic RGB-D -> detector ->
#                  scene_graph -> grounding action -> success assertion
#
# Usage:
#   docker/verify.sh               # full ladder (builds the image first)
#   docker/verify.sh --no-build    # reuse existing go2-semantic-nav:agiros-dev
#   docker/verify.sh --no-smoke    # skip step 5 (no model downloads / GPU)
#
# Env:
#   VERIFY_DEVICE   torch device for the smoke test (default: cpu)
#   HF_ENDPOINT     passed through for HuggingFace mirrors on the smoke run

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

IMAGE=go2-semantic-nav:agiros-dev
NO_BUILD=0
NO_SMOKE=0
for a in "$@"; do
  case "$a" in
    --no-build) NO_BUILD=1 ;;
    --no-smoke) NO_SMOKE=1 ;;
    *) echo "unknown flag: $a" >&2; exit 2 ;;
  esac
done

if [[ $NO_BUILD -eq 0 ]]; then
  echo "=== building $IMAGE ==="
  docker build -f docker/dev.Dockerfile -t "$IMAGE" .
elif ! docker image inspect "$IMAGE" > /dev/null 2>&1; then
  echo "error: image $IMAGE not found locally; run without --no-build first" >&2
  exit 1
fi

# Run as the host uid so workspace artifacts (build/, install/, log/) stay
# user-owned; HOME points into the container with a persistent cache mount.
mkdir -p "${HOME}/.cache/go2-agiros"
# `-e HF_ENDPOINT` without a value passes it through only when set on the
# host; an empty value would break open_clip HF downloads (missing protocol).
docker run --rm --network host \
  -u "$(id -u):$(id -g)" \
  -e HOME=/tmp/agiros-home \
  -v "${HOME}/.cache/go2-agiros:/tmp/agiros-home" \
  -v "$PWD:/workspace" -w /workspace \
  -e VERIFY_DEVICE="${VERIFY_DEVICE:-cpu}" \
  -e HF_ENDPOINT \
  "$IMAGE" bash -c '
# NOTE: no `set -u` — /opt/agiros/loong/setup.bash references unbound vars
# (AMENT_TRACE_SETUP_FILES) and sourcing it under -u aborts.
set -eo pipefail
mkdir -p "$HOME"
source /opt/agiros/loong/setup.bash

echo "=== [1/5] AGIROS environment ==="
echo "ROS_DISTRO=${ROS_DISTRO} ROS_VERSION=${ROS_VERSION} agiros=$(command -v agiros)"
[[ "${ROS_DISTRO}" == "loong" ]]
agiros --help > /dev/null
echo "env OK"

echo "=== [2/5] agirosdep check ==="
# The update cache is per-user ($ROS_HOME, default $HOME/.ros); the one baked
# at image build time lives under the root home dir, so refresh it for this uid.
agirosdep update
# --ignore-src: go2_* packages depend on each other; colcon owns build order
# for workspace-internal deps, agirosdep only checks the system keys.
agirosdep check --from-paths ros2_ws/src --ignore-src

echo "=== [3/5] colcon build ==="
cd ros2_ws
# Stale artifacts from host (pre-migration) builds break CMakeCache inside
# the container; derived files are rebuilt fresh under the AGIROS toolchain.
rm -rf build install log
colcon build --symlink-install
source install/setup.bash
agiros pkg list | grep "^go2_" | sort

echo "=== [4/5] tests ==="
colcon test --event-handlers console_cohesion-
colcon test-result --verbose
cd /workspace
python3 -m pytest

if [[ "${1:-}" == "1" ]]; then
  echo "=== [5/5] smoke: SKIPPED (--no-smoke) ==="
  exit 0
fi
echo "=== [5/5] smoke: synthetic RGB-D -> detector -> scene graph -> grounding ==="
cd /workspace
python3 scripts/smoke_test_integration.py \
  --device "${VERIFY_DEVICE}" --text person --timeout 240
' verify "${NO_SMOKE}"

echo
echo "verify.sh: all requested steps PASSED"
