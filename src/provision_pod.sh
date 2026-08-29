#!/usr/bin/env bash
# Build this project's GPU stack ON THE VOLUME so it survives a RunPod stop (D-009).
# Run once per fresh pod/volume, from the pod:   bash /workspace/vdl/src/provision_pod.sh
# Takes ~21 min (D-009). Idempotent: skips the venv build if /workspace/venv exists.
set -u

export HF_HOME=/workspace/hf
mkdir -p /workspace/hf

if [ ! -x /workspace/venv/bin/python ]; then
  echo "=== building /workspace/venv (expect ~21 min) ==="
  python3 -m venv /workspace/venv
  /workspace/venv/bin/pip install -q --upgrade pip
  # vllm pulls its own torch; the rest are what importing the frozen upstream package
  # transitively needs (D-010/2) plus the judge's fire/tqdm.
  /workspace/venv/bin/pip install vllm anthropic openai python-dotenv accelerate \
      huggingface_hub tenacity fire ninja tqdm
else
  echo "=== /workspace/venv already present, skipping build ==="
fi

# Install the committed bootstrap as the volume's standing start procedure.
if [ -f /workspace/vdl/src/bootstrap.sh ]; then
  cp /workspace/vdl/src/bootstrap.sh /workspace/bootstrap.sh
  chmod +x /workspace/bootstrap.sh
  echo "=== installed /workspace/bootstrap.sh from the repo copy ==="
fi

source /workspace/bootstrap.sh
