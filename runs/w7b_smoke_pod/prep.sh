set -x
export HF_HOME=/workspace/hf
P=/usr/local/bin/python
$P -m pip install -q "transformers==4.57.6" accelerate safetensors huggingface_hub anthropic python-dotenv tenacity fire tqdm openai 2>&1 | tail -5
$P -c "import transformers,accelerate,safetensors,anthropic;print(\"transformers\",transformers.__version__)"
$P -c "
from huggingface_hub import snapshot_download
p=snapshot_download(\"Qwen/Qwen2.5-14B-Instruct\", max_workers=8)
print(\"SNAPSHOT\", p)
"
