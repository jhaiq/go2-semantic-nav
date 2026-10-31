# Jetson deployment container for go2-semantic-nav.
# Base: NVIDIA L4T PyTorch for JetPack 6.x (Orin NX 16 GB).
#
# Build on the Jetson:
#   docker build -f docker/jetson.Dockerfile -t go2-semantic-nav:jetson .
#
# Run:
#   docker run --rm -it --runtime nvidia --network host \
#     -v "$PWD:/workspace" \
#     -v "$HOME/.cache:/root/.cache" \
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

# --- 基础工具 ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg lsb-release software-properties-common \
    git build-essential cmake pkg-config \
    python3-pip python3-dev \
    libeigen3-dev \
 && rm -rf /var/lib/apt/lists/*

# --- AGIROS loong (Jammy / JetPack 6.x, aarch64) ---
# AGIROS 发布 jammy 的 aarch64 构建;源配置复刻官方安装器
# http://repo.agiros.org.cn/debrepo/agiros/ubuntu2204lts/2606/install.sh (trusted=yes)。
# CLI 为 agiros(等价 ros2 参数),rosdep 由 agirosdep 替代。
RUN echo "deb [arch=$(dpkg --print-architecture) trusted=yes] http://repo.agiros.org.cn/debrepo/agiros/ubuntu2204lts/2606 jammy main" \
    > /etc/apt/sources.list.d/agiros.list \
 && apt-get update && apt-get install -y --no-install-recommends \
    agiros-loong-ros-base \
    agiros-loong-nav2-bringup \
    agiros-loong-cv-bridge \
    agiros-loong-tf2-ros \
    agiros-loong-vision-msgs \
    agiros-loong-rviz2 \
    python3-colcon-common-extensions \
 && rm -rf /var/lib/apt/lists/* \
 && python3 -m pip install http://repo.agiros.org.cn/yumrepo/agiros/agirosdep/agirosdep-0.25.1-py3-none-any.whl \
 && agirosdep init && agirosdep update

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

# --- 入口：source AGIROS + workspace，替代 .bashrc 黑魔法 ---
COPY docker/ros_entrypoint.sh /ros_entrypoint.sh
RUN chmod +x /ros_entrypoint.sh
WORKDIR /workspace
ENTRYPOINT ["/ros_entrypoint.sh"]
CMD ["bash"]