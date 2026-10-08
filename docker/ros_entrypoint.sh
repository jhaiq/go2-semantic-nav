#!/bin/bash
set -e
source /opt/ros/humble/setup.bash
[ -f /workspace/ros2_ws/install/setup.bash ] && \
    source /workspace/ros2_ws/install/setup.bash
export OMP_NUM_THREADS=4
exec "$@"