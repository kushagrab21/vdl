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

echo "bootstrap: HF_HOME=$HF_HOME"
echo "bootstrap: python=$(command -v python3 || echo none)"
python3 - <<'EOF' 2>/dev/null || echo "bootstrap: vllm NOT importable — venv missing?"
import vllm, torch
print("bootstrap: vllm", vllm.__version__, "| torch", torch.__version__,
      "| cuda", torch.cuda.is_available())
EOF
