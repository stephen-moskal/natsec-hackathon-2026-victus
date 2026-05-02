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

# Light apt deps for OpenCV runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libsm6 libxext6 libgl1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps. Same Jetson AI Lab mirror used previously for any aarch64 wheels.
ENV PIP_EXTRA_INDEX_URL="https://pypi.jetson-ai-lab.io/jp6/cu126 https://pypi.ngc.nvidia.com"

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
