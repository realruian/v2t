#!/usr/bin/env bash
# Build V2T.app via py2app.
#   bash build_app.sh             # alias (fast; .app links to this folder)
#   bash build_app.sh standalone  # full bundle (slow; portable)
#   bash build_app.sh --no-open   # build without opening Finder
set -e
cd "$(dirname "$0")"

MODE="alias"
OPEN_DIST=1

for arg in "$@"; do
  case "$arg" in
    standalone) MODE="standalone" ;;
    --no-open) OPEN_DIST=0 ;;
    *)
      echo "未知参数：$arg"
      exit 1
      ;;
  esac
done

if [ ! -d ".venv" ]; then
  echo "→ 先跑一次 setup.sh 安装依赖"
  bash setup.sh
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "→ 安装 py2app"
pip install --quiet py2app

echo "→ 清理旧产物"
rm -rf build dist

if [ "$MODE" = "standalone" ]; then
  echo "→ 打包（standalone，可能 5-15 分钟）"
  python setup_app.py py2app
else
  echo "→ 打包（alias，30 秒）"
  python setup_app.py py2app -A
fi

APP_PATH="$(pwd)/dist/V2T.app"
echo ""
if [ -d "$APP_PATH" ]; then
  echo "✅ 打包完成：$APP_PATH"
  echo ""
  echo "下一步："
  echo "  1. 在 Finder 中打开 dist/，把 V2T.app 拖到 /Applications 或 Dock"
  echo "  2. 双击启动；首次启动如提示安全警告，右键 → 打开"
  echo ""
  if [ "$OPEN_DIST" = "1" ]; then
    open "$(dirname "$APP_PATH")"
  fi
else
  echo "❌ 打包失败"
  exit 1
fi
