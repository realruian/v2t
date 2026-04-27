#!/usr/bin/env bash
# One-time setup: create venv and install dependencies.
set -e
cd "$(dirname "$0")"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "❌ 未检测到 ffmpeg，请先安装：brew install ffmpeg"
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "→ 创建虚拟环境 .venv"
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "→ 升级 pip"
pip install --upgrade pip wheel >/dev/null

echo "→ 安装依赖（faster-whisper / pywebview）"
pip install -r requirements.txt

echo ""
echo "✅ 安装完成。双击 V2T.command 启动应用。"
echo "   首次转写会自动下载 Large-V3 模型（约 3GB），下载后会缓存。"
