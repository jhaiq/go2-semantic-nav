# Docker for go2-semantic-nav

## Dev container (`dev.Dockerfile`)
For x86_64 development on the dev workstation. Contains **AGIROS loong**
(ROS 2 Humble-generation compatible) + Nav2 + the full Python ML stack.

Notes on the AGIROS environment:
- CLI is `agiros` (same arguments as `ros2`; there is no `ros2` binary), e.g.
  `agiros topic list`, `agiros launch ...`
- `rosdep` is replaced by `agirosdep` — run `agirosdep update` once before
  `agirosdep check --from-paths ros2_ws/src --ignore-src`
- `ROS_DISTRO` is `loong`; environment root is `/opt/agiros/loong`

Build:
```bash
docker build -f docker/dev.Dockerfile -t go2-semantic-nav:agiros-dev .
```

Run with GPU passthrough:
```bash
docker run --rm -it --gpus all \
  -v "$PWD:/workspace" \
  --network=host \
  go2-semantic-nav:agiros-dev
```

Inside the container (from `/workspace`):
```bash
agirosdep check --from-paths ros2_ws/src --ignore-src
cd ros2_ws && colcon build --symlink-install
source install/setup.bash && agiros launch go2_semantic_bringup semantic_nav.launch.py --show-args
```

## Jetson container (`jetson.Dockerfile`)
Base: `nvcr.io/nvidia/l4t-pytorch:r36.2.0-pth2.3-py3` for JetPack 6.x
(Ubuntu 22.04, aarch64 — an AGIROS-supported platform). The ROS layer
installs `agiros-loong-*` packages from the AGIROS jammy repo.

Build on the Jetson:
```bash
DOCKER_BUILDKIT=1 docker build -f docker/jetson.Dockerfile -t go2-semantic-nav:jetson .
```

Run:
```bash
docker run --rm -it --runtime nvidia --network host \
  -v "$PWD:/workspace" \
  -v "$HOME/.cache:/root/.cache" \
  go2-semantic-nav:jetson
```
