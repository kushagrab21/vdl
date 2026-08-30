#!/usr/bin/env bash
# Re-establish container-local state after a RunPod start. D-009: a "stop" wipes the
# container filesystem — only /workspace survives — so this must run at the top of every
# GPU packet:   source /workspace/bootstrap.sh
#
# This file is the COMMITTED master copy. src/provision_pod.sh installs it to
# /workspace/bootstrap.sh. W2 committed it after discovering the pod-resident copy was
# the only one in existence (D-012), which would have been lost with the volume.

export HF_HOME=/workspace/hf
export PATH=/workspace/venv/bin:$PATH
export VLLM_WORKER_MULTIPROC_METHOD=spawn

mkdir -p /root/.ssh && chmod 700 /root/.ssh
if [ -f /workspace/.ssh/id_deploy ]; then
  cp /workspace/.ssh/id_deploy /root/.ssh/id_deploy
  chmod 600 /root/.ssh/id_deploy
  cat > /root/.ssh/config <<'EOF'
Host github.com
  User git
  IdentityFile /root/.ssh/id_deploy
  IdentitiesOnly yes
  StrictHostKeyChecking yes
EOF
  chmod 600 /root/.ssh/config
  ssh-keyscan -t rsa,ecdsa,ed25519 github.com > /root/.ssh/known_hosts 2>/dev/null
  chmod 600 /root/.ssh/known_hosts
else
  echo "bootstrap: no /workspace/.ssh/id_deploy — git over SSH unavailable;" \
       "push code to the pod with rsync instead"
fi

# R-010(4) / D-022: pick the interpreter that actually has torch, and say which one.
# In runpod/pytorch:1.2.0-...-cu1281-torch280 `python3` is /usr/bin/python3 (3.10, NO
# torch) while `python` is /usr/local/bin/python (3.12, torch 2.8, and where pip installs).
# The old line printed `command -v python3` unconditionally and would have named the wrong
# interpreter; W4's first prep pass ran under it and died on ModuleNotFoundError: torch.
pick_python() {
  for cand in /usr/local/bin/python python python3; do
    c=$(command -v "$cand" 2>/dev/null) || continue
    if "$c" -c 'import torch' >/dev/null 2>&1; then echo "$c"; return 0; fi
  done
  # nothing has torch: fall back to whatever python exists, and say so
  command -v python || command -v python3 || echo none
  return 1
}
VDL_PYTHON="$(pick_python)"
export VDL_PYTHON

echo "bootstrap: HF_HOME=$HF_HOME"
echo "bootstrap: python=$VDL_PYTHON  (python=$(command -v python || echo none), python3=$(command -v python3 || echo none))"
"$VDL_PYTHON" - <<'EOF' 2>/dev/null || echo "bootstrap: torch NOT importable under $VDL_PYTHON"
import torch
print("bootstrap: torch", torch.__version__, "| cuda", torch.cuda.is_available())
try:
    import vllm
    print("bootstrap: vllm", vllm.__version__)
except Exception:
    print("bootstrap: vllm not installed (W4+ packets do not need it)")
EOF
