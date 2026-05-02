# Common base for the victus_edge llama.cpp-backed images (qwen3vl, gemma4).
# Builds on top of dustynv/llama_cpp which already ships:
#   - llama-server, llama-mtmd-cli (built with CUDA, sm_87 / Orin)
#   - Python 3.10
# We add only the lightweight HTTP-driver stack (opencv-python-headless,
# requests, pillow) plus the victus_edge source. Total added size is small (<300 MB).
#
# Cross-revision note: matches the host R36.5.0 host even though tag is r36.4.0
# — userland is decoupled from host kernel via nvidia-container-runtime.

FROM dustynv/llama_cpp:r36.4.0

WORKDIR /opt/victus_edge

# Light apt deps for OpenCV runtime + GStreamer (used for hardware-accelerated
# video decode via Tegra-native plugins, mounted in by nvidia-container-runtime).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libsm6 libxext6 libgl1 curl \
        gstreamer1.0-tools \
        gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-bad \
        gstreamer1.0-libav \
        python3-gi python3-gst-1.0 \
        gir1.2-gstreamer-1.0 \
        libgstreamer1.0-0 libgstreamer-plugins-base1.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV GST_PLUGIN_PATH=/usr/lib/aarch64-linux-gnu/gstreamer-1.0:/usr/lib/aarch64-linux-gnu/tegra-egl/gstreamer-1.0:/usr/lib/aarch64-linux-gnu/tegra/gstreamer-1.0

# Override dustynv's baked-in pypi.jetson-ai-lab.dev primary index (DNS-broken).
ENV PIP_INDEX_URL=https://pypi.org/simple/

COPY requirements.txt /opt/victus_edge/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r /opt/victus_edge/requirements.txt

# Source last so iteration on Python doesn't bust the heavy layers.
COPY src/           /opt/victus_edge/src/
COPY pyproject.toml /opt/victus_edge/

ENV PYTHONPATH=/opt/victus_edge/src \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,video \
    VICTUS_LLM_SERVER_URL=http://127.0.0.1:8080

# Per-model images add the GGUFs and copy the entrypoint script.
