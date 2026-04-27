#!/usr/bin/env bash
# Double-click to launch V2T.
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "首次启动，正在执行安装…"
  bash setup.sh || { echo "安装失败，按任意键退出"; read -n 1; exit 1; }
fi

# shellcheck disable=SC1091
source .venv/bin/activate
exec python app.py
