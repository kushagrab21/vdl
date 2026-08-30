export HF_HOME=/workspace/hf
cd /workspace/vdl
P=/usr/local/bin/python
echo "=== GPU SANITY $(date -u) ==="
$P src/steer_w7b.py --arms B7b_above_L27_ap05 B7b_above_null10_am05 --n 4 --batch 4 --out-root runs/w7b_smoke_pod
echo "SANITY_RC=$?"
echo "=== FULL RUN $(date -u) ==="
$P src/steer_w7b.py --out-root runs/w7b_steer
echo "FULL_RC=$? DONE $(date -u)"
