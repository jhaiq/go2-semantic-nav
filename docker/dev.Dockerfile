# Development container for go2-semantic-nav on x86_64.
# Not for Jetson — the Jetson image uses JetPack 6.x + l4t-pytorch base.
FROM nvidia/cuda:12.8.0-cudnn-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ARG ROS_DISTRO=humble

# --- System packages ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg lsb-release software-properties-common \
    git build-essential cmake pkg-config \
    python3-pip python3-dev python3-venv \
    libeigen3-dev libgl1-mesa-glx libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

# --- ROS 2 Humble ---
RUN curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.asc | gpg --dearmor -o /usr/share/keyrings/ros-archive-keyring.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(lsb_release -cs) main" > /etc/apt/sources.list.d/ros2.list \
 && apt-get update && apt-get install -y --no-install-recommends \
    ros-${ROS_DISTRO}-ros-base \
    ros-${ROS_DISTRO}-nav2-bringup \
    ros-${ROS_DISTRO}-cv-bridge \
    ros-${ROS_DISTRO}-tf2-ros \
    ros-${ROS_DISTRO}-vision-msgs \
    ros-${ROS_DISTRO}-rviz2 \
    python3-colcon-common-extensions \
    python3-rosdep \
 && rm -rf /var/lib/apt/lists/*

# --- Python ML stack ---
RUN pip install --upgrade pip \
 && pip install --extra-index-url https://download.pytorch.org/whl/cu128 \
    torch==2.3.0 torchvision==0.18.0 \
 && pip install \
    "numpy<2.0" \
    ultralytics>=8.4.0 \
    open_clip_torch>=2.24.0 \
    networkx>=3.2 \
    scipy>=1.11.0 \
    opencv-python>=4.8.0 \
    pyyaml \
    pytest \
    ruff \
    black
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