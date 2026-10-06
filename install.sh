#!/usr/bin/env bash
# JarvisAi — Ubuntu installer
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Creating Python 3.11 venv..."
uv venv --python 3.11 .venv

echo "==> Installing CPU-only torch..."
uv pip install --python .venv/bin/python torch --index-url https://download.pytorch.org/whl/cpu

echo "==> Installing project dependencies..."
uv pip install --python .venv/bin/python -r requirements.txt

echo "==> Downloading openWakeWord ONNX models..."
.venv/bin/python -c "from openwakeword import utils; utils.download_models()" || true
.venv/bin/python -c "import openwakeword, os, urllib.request; d=os.path.join(os.path.dirname(openwakeword.__file__),'resources','models'); os.makedirs(d,exist_ok=True); [urllib.request.urlretrieve('https://github.com/dscripka/openWakeWord/raw/main/openwakeword/resources/models/'+f, os.path.join(d,f)) for f in ['melspectrogram.onnx','embedding_model.onnx'] if not os.path.exists(os.path.join(d,f))]" || true

echo "==> Done. Run ./start.sh to launch."
