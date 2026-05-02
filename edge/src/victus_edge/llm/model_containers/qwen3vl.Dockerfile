# victus_edge Qwen3-VL 2B Instruct runtime image for Jetson Orin Nano Super.
#
# Model: Qwen/Qwen3-VL-2B-Instruct-GGUF (Apache 2.0)
#   Q4_K_M:  ~1.1 GB on disk, ~1.5 GB GPU resident
#   mmproj:  ~782 MB (vision projector)
#
# This image is intentionally model-less: GGUFs are bind-mounted from the
# host at runtime so rebuilds don't re-download weights and one image can
# serve any quantization variant.
#
# Expected host layout (provided via -v at run time):
#   ~/models/qwen3vl/Qwen3VL-2B-Instruct-Q4_K_M.gguf
#   ~/models/qwen3vl/mmproj-Qwen3VL-2B-Instruct-F16.gguf
#
# Build (run from project root — needs shared/ in build context):
#   docker build -f edge/src/victus_edge/llm/model_containers/qwen3vl.Dockerfile \
#                -t victus_edge/qwen3vl:latest .
#
# Run:
#   docker run --runtime nvidia --rm --network host \
#     -v ~/models:/opt/models:ro \
#     victus_edge/qwen3vl:latest

ARG L4T_TAG=r36.4.0
FROM dustynv/llama_cpp:${L4T_TAG}

WORKDIR /opt/victus_edge

# Common deps (same as llama_base.Dockerfile, inlined here for single-file build)
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

# nvidia-container-runtime mounts the host's Tegra plugins (nvv4l2decoder,
# nvvidconv, nvvideosink, etc.) under /usr/lib/aarch64-linux-gnu/tegra/.
# Tell GStreamer to scan that directory so the Tegra-native NVDEC element
# is discoverable inside the container.
ENV GST_PLUGIN_PATH=/usr/lib/aarch64-linux-gnu/gstreamer-1.0:/usr/lib/aarch64-linux-gnu/tegra-egl/gstreamer-1.0:/usr/lib/aarch64-linux-gnu/tegra/gstreamer-1.0
ENV LD_LIBRARY_PATH=/usr/lib/aarch64-linux-gnu/tegra:/usr/lib/aarch64-linux-gnu/tegra-egl:${LD_LIBRARY_PATH:-}

# Rebuild llama.cpp from current master — the dustynv image's prebuilt
# llama-server (build 4579, Feb 2025) predates native multimodal HTTP support.
# We need the unified mtmd interface for Qwen3-VL / Gemma 4. dustynv pre-cloned
# the source at /opt/llama.cpp, so we only fetch new commits.
ARG LLAMA_CPP_REF=master
RUN cd /opt/llama.cpp && \
    git fetch --depth=1 origin ${LLAMA_CPP_REF} && \
    git checkout FETCH_HEAD && \
    rm -rf build && \
    cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=87 \
                   -DLLAMA_CURL=ON -DCMAKE_BUILD_TYPE=Release && \
    cmake --build build --config Release -j$(nproc) --target llama-server && \
    cp build/bin/llama-server /usr/local/bin/llama-server && \
    cp build/bin/libllama.so /usr/local/lib/ 2>/dev/null || true && \
    cp build/bin/libggml*.so /usr/local/lib/ 2>/dev/null || true && \
    ldconfig

# dustynv/llama_cpp's baked-in pip.conf points at https://pypi.jetson-ai-lab.dev
# which is currently DNS-unresolvable. Override to use vanilla pypi.org for our
# install steps. Re-add a Jetson-AI-Lab index ONLY for steps that need
# CUDA-enabled aarch64 wheels (e.g., llama-cpp-python, torch).
ENV PIP_INDEX_URL=https://pypi.org/simple/

COPY edge/requirements.txt /opt/victus_edge/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r /opt/victus_edge/requirements.txt

# Models are intentionally NOT baked in — they're bind-mounted from the host
# at runtime via `-v ~/models:/opt/models:ro` (see header).

COPY edge/src/           /opt/victus_edge/src/
COPY edge/pyproject.toml /opt/victus_edge/

# Shared protocol JSON schemas — protocol.py reads these at import time from
# /opt/shared (its _REPO_ROOT computation lands at /opt inside the container).
COPY shared/ /opt/shared/

# Install the victus_edge package itself (editable) — pulls in pyproject.toml's
# core deps (httpx, structlog, pyyaml, uvloop, jsonschema, tenacity).
# requirements.txt above already covers them too with exact pins, so this is
# mostly a no-op for deps but registers the package + console script.
RUN pip install --no-cache-dir -e /opt/victus_edge

COPY edge/src/victus_edge/llm/model_containers/entrypoint.sh /opt/victus_edge/entrypoint.sh
RUN chmod +x /opt/victus_edge/entrypoint.sh

ENV PYTHONPATH=/opt/victus_edge/src \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,video \
    VICTUS_LLM_SERVER_URL=http://127.0.0.1:8080 \
    VICTUS_LLM_MODEL_PATH=/opt/models/qwen3vl/Qwen3VL-2B-Instruct-Q4_K_M.gguf \
    VICTUS_LLM_MMPROJ_PATH=/opt/models/qwen3vl/mmproj-Qwen3VL-2B-Instruct-F16.gguf

ENTRYPOINT ["/opt/victus_edge/entrypoint.sh"]
CMD []
