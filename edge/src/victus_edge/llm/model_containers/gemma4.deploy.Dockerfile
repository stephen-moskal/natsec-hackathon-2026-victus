# victus_edge Gemma 4 deployable image — extends the dev image and bakes in
# the GGUFs so the result is a single self-contained artifact.
#
# See qwen3vl.deploy.Dockerfile for the rationale. Same pattern, gemma4
# weights instead of qwen3vl.
#
# Build (run from ~/models on the Jetson, since the build context provides
# the GGUF files):
#
#   docker build \
#     -f ~/natsec-hackathon-2026-victus/edge/src/victus_edge/llm/model_containers/gemma4.deploy.Dockerfile \
#     -t victus_edge/gemma4-deploy:latest \
#     ~/models
#
# Run on a fresh Jetson (no -v mount needed):
#
#   docker run --runtime nvidia --rm --network host --device /dev/video0 \
#     victus_edge/gemma4-deploy:latest --gst-webcam 0 --test

FROM victus_edge/gemma4:latest

# COPY paths are relative to the build context (~/models on the Jetson).
COPY gemma4/gemma-4-E4B-it-Q4_K_M.gguf /opt/models/gemma4/gemma-4-E4B-it-Q4_K_M.gguf
COPY gemma4/mmproj-gemma-4-E4B-it-BF16.gguf /opt/models/gemma4/mmproj-gemma-4-E4B-it-BF16.gguf

# Env vars VICTUS_LLM_MODEL_PATH and VICTUS_LLM_MMPROJ_PATH already point at
# /opt/models/gemma4/... in the base image — no override needed. ENTRYPOINT
# and CMD are inherited (python3 -m victus_edge.main --model gemma4).
