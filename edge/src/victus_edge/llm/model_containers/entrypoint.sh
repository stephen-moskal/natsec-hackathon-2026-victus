#!/bin/bash
# Entrypoint: launches llama-server in the background, waits for it to come
# up, then runs the victus_edge harness in the foreground. Forwards CLI args
# straight through to `python3 -m victus_edge.main`, so any args passed via
# `docker run image -- ...` reach the Python entry point.
set -euo pipefail

: "${VICTUS_LLM_MODEL_PATH:?VICTUS_LLM_MODEL_PATH not set — should be set by the model-specific image}"
: "${VICTUS_LLM_MMPROJ_PATH:?VICTUS_LLM_MMPROJ_PATH not set — should be set by the model-specific image}"

# llama-server flags tuned for the 8 GB Jetson Orin Nano Super:
#   -ngl 99           offload all layers to GPU (Orin Nano: full INT4 model fits)
#   --mmproj          vision projector for multimodal models
#   -c ${CTX:-2048}   context window — drone reasoning prompts fit in 2K easily
#   --parallel 1      single inference slot (default 4) → each slot keeps its own
#                     KV cache, so 4-slot quadruples memory; we only stream one
#                     frame at a time through the harness.
#   --cache-ram 0     disable the prompt cache entirely (default 8 GB allocation
#                     is way more than the Jetson can spare).
#   --jinja           use the GGUF's embedded chat template (correct formatting)
CTX=${VICTUS_LLM_CTX_SIZE:-2048}
# Vision encoders use non-causal attention which requires
# `n_ubatch >= n_tokens_in_image_chunk`. Gemma 4's mmproj produces 256 tokens
# per image, so -ub 256 is the floor. Keeping -b == -ub keeps per-step
# compute graphs minimal.
BATCH=${VICTUS_LLM_BATCH:-256}
UBATCH=${VICTUS_LLM_UBATCH:-256}
echo "[entrypoint] starting llama-server with $(basename "$VICTUS_LLM_MODEL_PATH"), ctx=$CTX, batch=$BATCH/$UBATCH"
# -b/-ub small (defaults are 512/256) to keep the compute graph buffer below
# ~80 MiB. Each multimodal request reserves a fresh compute buffer twice
# (once for image decode, once for text post-image), so peak = 2× ubatch
# buffer. With the default batch sizes Gemma 4's twin allocations OOM the
# 8 GB Jetson; -b 64 -ub 32 fits safely.
llama-server \
    -m "$VICTUS_LLM_MODEL_PATH" \
    --mmproj "$VICTUS_LLM_MMPROJ_PATH" \
    -ngl 99 \
    -c "$CTX" \
    -b "$BATCH" \
    -ub "$UBATCH" \
    --parallel 1 \
    --cache-ram 0 \
    --host 127.0.0.1 \
    --port 8080 \
    --jinja \
    > /tmp/llama-server.log 2>&1 &

LLAMA_PID=$!
trap 'kill $LLAMA_PID 2>/dev/null || true; wait $LLAMA_PID 2>/dev/null || true' EXIT TERM INT

# Wait for /health to report "ok"
echo "[entrypoint] waiting for llama-server to load model..."
for i in $(seq 1 180); do
    if curl -sf http://127.0.0.1:8080/health 2>/dev/null | grep -q '"ok"'; then
        echo "[entrypoint] llama-server ready in ${i}s"
        break
    fi
    if ! kill -0 $LLAMA_PID 2>/dev/null; then
        echo "[entrypoint] llama-server died during startup — last 50 log lines:"
        tail -50 /tmp/llama-server.log
        exit 1
    fi
    sleep 1
done

# Run the harness. CLI args from `docker run ... --arg1 ...` arrive here as $@.
echo "[entrypoint] launching victus_edge harness with args: $*"
python3 -m victus_edge.main "$@"
HARNESS_RC=$?

# Dump server timing summary so per-request timings are visible to the host.
if [ "${VICTUS_DUMP_SERVER_LOG:-1}" = "1" ]; then
    echo
    echo "[entrypoint] === llama-server log (last 200 lines) ==="
    tail -200 /tmp/llama-server.log 2>/dev/null | grep -E "(prompt eval|^[ ]+eval time|total time|process_chun|image slice|image decoded|^slot)" || tail -200 /tmp/llama-server.log
    echo "[entrypoint] === end llama-server log ==="
fi
exit "$HARNESS_RC"
