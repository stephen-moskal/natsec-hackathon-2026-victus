# victus_edge Qwen3-VL deployable image — extends the dev image and bakes in
# the GGUFs so the result is a single self-contained artifact.
#
# Use this Dockerfile for Foundry distribution: one tarball per model, no
# host-side ~/models bind-mount required on the target Jetson. The dev
# Dockerfile (qwen3vl.Dockerfile) stays model-less so iteration on Python
# code keeps its <30s rebuild loop.
#
# Build (run from ~/models on the Jetson, since the build context provides
# the GGUF files):
#
#   docker build \
#     -f ~/natsec-hackathon-2026-victus/edge/src/victus_edge/llm/model_containers/qwen3vl.deploy.Dockerfile \
#     -t victus_edge/qwen3vl-deploy:latest \
#     ~/models
#
# Run on a fresh Jetson (no -v mount needed):
#
#   docker run --runtime nvidia --rm --network host --device /dev/video0 \
#     victus_edge/qwen3vl-deploy:latest --gst-webcam 0 --test

FROM victus_edge/qwen3vl:latest

# COPY paths are relative to the build context (~/models on the Jetson).
COPY qwen3vl/Qwen3VL-2B-Instruct-Q4_K_M.gguf /opt/models/qwen3vl/Qwen3VL-2B-Instruct-Q4_K_M.gguf
COPY qwen3vl/mmproj-Qwen3VL-2B-Instruct-F16.gguf /opt/models/qwen3vl/mmproj-Qwen3VL-2B-Instruct-F16.gguf

# Env vars VICTUS_LLM_MODEL_PATH and VICTUS_LLM_MMPROJ_PATH already point at
# /opt/models/qwen3vl/... in the base image — no override needed. ENTRYPOINT
# and CMD are inherited (python3 -m victus_edge.main --model qwen-vl).
