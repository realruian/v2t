#!/usr/bin/env bash
# 从 HuggingFace 镜像下载 Whisper Large-V3 模型到 models/large-v3/
# 国内速度通常 10-50 MB/s，~3GB 大概 1-5 分钟。
set -e
cd "$(dirname "$0")"

MODEL_DIR="models/large-v3"
mkdir -p "$MODEL_DIR"
cd "$MODEL_DIR"

# 镜像源（如果需要切换，改这一行即可）
BASE="${HF_ENDPOINT:-https://hf-mirror.com}/Systran/faster-whisper-large-v3/resolve/main"

# faster-whisper 加载所需的全部文件
FILES=(
  "config.json"
  "model.bin"
  "preprocessor_config.json"
  "tokenizer.json"
  "vocabulary.json"
)

echo "→ 下载到：$(pwd)"
echo "→ 镜像：$BASE"
echo ""

for f in "${FILES[@]}"; do
  if [ -f "$f" ] && [ -s "$f" ]; then
    size=$(du -h "$f" | cut -f1)
    echo "  ✓ $f  ($size，已存在，跳过)"
    continue
  fi
  echo "  ↓ $f"
  # -L 跟随重定向；-C - 断点续传；--fail 失败时退出非零
  curl -L -C - --fail --progress-bar -o "$f" "$BASE/$f"
done

for f in "${FILES[@]}"; do
  if [ ! -s "$f" ]; then
    echo "❌ 模型文件不完整：$f"
    exit 1
  fi
done

echo ""
echo "✅ 下载完成"
echo ""
ls -lh
echo ""
echo "下次启动 V2T，会自动从这里加载（无需联网）。"
