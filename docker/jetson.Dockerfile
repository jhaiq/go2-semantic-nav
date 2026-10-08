# Jetson deployment container for go2-semantic-nav.
# Base: NVIDIA L4T PyTorch for JetPack 6.x (Orin NX 16 GB).
#
# Build on the Jetson:
#   docker build -f docker/jetson.Dockerfile -t go2-semantic-nav:jetson .
#
# Run:
#   docker run --rm -it --runtime nvidia --network host \
#     -v "$PWD:/workspace" \
#     -v "$HOME/.cache:/home/ros/.cache" \
#     go2-semantic-nav:jetson

# # Jetson 本机构建（老版本 Docker 需显式开启 BuildKit 才能用 cache mount）
# DOCKER_BUILDKIT=1 docker build -f docker/jetson.Dockerfile -t go2-semantic-nav:jetson .

# docker run --rm -it --runtime nvidia --network host \
#   -v "$PWD:/workspace" \
#   -v "$HOME/.cache:/root/.cache" \
#   go2-semantic-nav:jetson

# syntax=docker/dockerfile:1
FROM nvcr.io/nvidia/l4t-pytorch:r36.2.0-pth2.3-py3

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
ARG ROS_DISTRO=humble

# --- 基础工具 ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg lsb-release software-properties-common \
    git build-essential cmake pkg-config \
    python3-pip python3-dev \
    libeigen3-dev \
 && rm -rf /var/lib/apt/lists/*

# --- ROS 2 Humble (Jammy / JetPack 6.x) ---
RUN curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.asc \
    | gpg --dearmor -o /usr/share/keyrings/ros-archive-keyring.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu jammy main" \
    > /etc/apt/sources.list.d/ros2.list \
 && apt-get update && apt-get install -y --no-install-recommends \
    ros-${ROS_DISTRO}-ros-base \
    ros-${ROS_DISTRO}-nav2-bringup \
    ros-${ROS_DISTRO}-cv-bridge \
    ros-${ROS_DISTRO}-tf2-ros \
    ros-${ROS_DISTRO}-vision-msgs \
    ros-${ROS_DISTRO}-rviz2 \
    python3-colcon-common-extensions \
 && rm -rf /var/lib/apt/lists/*

# --- Python ML 依赖（锁版本，见下方 requirements） ---
# torch 已在基础镜像中，绝不重装；numpy<2 匹配 Jetson 编译版 torch。
# BuildKit 缓存挂载：pip 下载在重建间复用，大幅加速。
# clip 预装：避免 YOLO-World 首次推理时联网安装导致 hang。
COPY docker/requirements-jetson.txt /tmp/requirements-jetson.txt

RUN --mount=type=cache,target=/root/.cache/pip \
    python3 -m pip install --upgrade "pip==24.0" \
        --index-url https://pypi.org/simple \
 && python3 -m pip install -r /tmp/requirements-jetson.txt \
        --index-url https://pypi.org/simple

# --- MobileSAM（aarch64 无 wheel，锁 commit，浅克隆） ---
ARG MOBILESAM_COMMIT=f706ad9c4eb7f219c00d9050e46328518ffb65d2  # 换成你验证过的 SHA
RUN git clone --depth 1 https://github.com/ChaoningZhang/MobileSAM.git /opt/MobileSAM \
 && cd /opt/MobileSAM && git fetch --depth 1 origin ${MOBILESAM_COMMIT} \
 && git checkout ${MOBILESAM_COMMIT} \
 && python3 -m pip install . \
 && rm -rf /opt/MobileSAM/.git

# --- NanoSAM（editable 安装需要保留源码目录） ---
ARG NANOSAM_COMMIT=653633614b2eb93b06ba3be9adb2aeffb117bd72
RUN git clone --depth 1 https://github.com/NVIDIA-AI-IOT/nanosam.git /opt/nanosam \
 && cd /opt/nanosam && git checkout ${NANOSAM_COMMIT} \
 && python3 -m pip install -e .

# --- 入口：source ROS 2 + workspace，替代 .bashrc 黑魔法 ---
COPY docker/ros_entrypoint.sh /ros_entrypoint.sh
RUN chmod +x /ros_entrypoint.sh
WORKDIR /workspace
ENTRYPOINT ["/ros_entrypoint.sh"]
CMD ["bash"]