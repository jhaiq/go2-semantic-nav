# Development container for go2-semantic-nav on x86_64.
# Not for Jetson — the Jetson image uses JetPack 6.x + l4t-pytorch base.
#
# Runtime: AGIROS loong (ROS 2 Humble-generation compatible) on Ubuntu 22.04.
# - CLI is `agiros` (same arguments as the ros2 CLI; there is no `ros2` binary)
# - rosdep is replaced by agirosdep (run `agirosdep update` once before `check`)
# - ROS_DISTRO is baked into the image as `loong`
FROM docker.agiros.org.cn/agiros/agiros-loong-ubuntu-base:latest

# The base image defaults to user `ros`; apt/colcon setup needs root, and the
# old (nvidia/cuda-based) dev container ran as root too.
USER root

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# --- APT repo: rewrite the baked-in signed-by entry to the current official
# trusted=yes form (the 2606 repo Release no longer verifies against the old
# keyring, and apt update fails against it). Mirrors the official installer at
# http://repo.agiros.org.cn/debrepo/agiros/ubuntu2204lts/2606/install.sh
RUN echo "deb [arch=$(dpkg --print-architecture) trusted=yes] http://repo.agiros.org.cn/debrepo/agiros/ubuntu2204lts/2606 jammy main" \
    > /etc/apt/sources.list.d/agiros.list

# --- System packages + colcon (AGIROS base images ship no colcon) ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    git build-essential cmake pkg-config \
    python3-pip python3-dev python3-venv \
    python3-colcon-common-extensions python3-colcon-ros \
    libeigen3-dev libgl1-mesa-glx libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

# --- agirosdep (resolves standard rosdep keys against the AGIROS repo) ---
# `init` writes the gitee-hosted sources list under /etc/agiros/agirosdep/;
# without it every agirosdep call exits 1.
RUN python3 -m pip install --no-cache-dir \
    http://repo.agiros.org.cn/yumrepo/agiros/agirosdep/agirosdep-0.25.1-py3-none-any.whl \
 && agirosdep init \
 && agirosdep update

# --- AGIROS loong packages (mechanical rename of the former ros-humble-* set;
# every name verified against the 2606 jammy repo) ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    agiros-loong-ros-base \
    agiros-loong-nav2-bringup \
    agiros-loong-cv-bridge \
    agiros-loong-tf2-ros \
    agiros-loong-tf2-geometry-msgs \
    agiros-loong-nav2-msgs \
    agiros-loong-vision-msgs \
    agiros-loong-rviz2 \
 && rm -rf /var/lib/apt/lists/*

# --- Python ML stack ---
# MobileSAM has no PyPI package (`mobile-sam` never resolved); install it from
# source at the same pinned commit as the Jetson image.
RUN pip install --upgrade pip \
 && pip install --extra-index-url https://download.pytorch.org/whl/cu128 \
    torch==2.3.0 torchvision==0.18.0 \
 && pip install \
    "numpy<2.0" \
    "ultralytics>=8.4.0" \
    "open_clip_torch>=2.24.0" \
    "networkx>=3.2" \
    "scipy>=1.11.0" \
    "opencv-python>=4.8.0" \
    pyyaml \
    ruff \
    black \
 && pip install --upgrade "pytest>=7.4"
# pytest is upgraded explicitly: apt colcon pulls python3-pytest 6.2.5 and a
# plain `pip install pytest` sees it as already satisfied, leaving a pytest too
# old for the test suite (no _pytest.scope) in /usr/lib.

ARG MOBILESAM_COMMIT=f706ad9c4eb7f219c00d9050e46328518ffb65d2
RUN git clone --depth 1 https://github.com/ChaoningZhang/MobileSAM.git /opt/MobileSAM \
 && cd /opt/MobileSAM && git fetch --depth 1 origin ${MOBILESAM_COMMIT} \
 && git checkout ${MOBILESAM_COMMIT} \
 && pip install --no-cache-dir . \
 && rm -rf /opt/MobileSAM/.git

WORKDIR /workspace
CMD ["/bin/bash"]
