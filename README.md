# V2T

> 本地视频 / 音频转文字工具，基于 Whisper Large-V3，中英双语，原生 macOS 应用。

队列式工作流：拖入多个文件 → 自动排队 → 串行转写。完整离线运行，不上传任何文件。

## 特性

- 🎯 **效果**：Whisper Large-V3，中英双语 SOTA
- 🔒 **离线**：模型本地加载，全程零网络请求
- ⚡ **性能**：CTranslate2 + int8 量化，M 系列 Mac 友好
- 🧰 **格式**：单次转写同时产出 `.txt` / `.srt` / `.vtt` / `.md`
- 🪟 **原生**：单文件 `.app`、Dock 图标、系统通知、暗色模式自动切换
- 📋 **队列**：多文件批量、拖拽重排、状态持久化（关 app 不丢）
- 🎧 **可读**：完成后内嵌音频播放器，点段落跳转

## 技术栈

| 层 | 技术 |
|---|---|
| ASR 模型 | [Whisper Large-V3](https://huggingface.co/openai/whisper-large-v3) |
| 推理引擎 | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2) |
| 音视频处理 | ffmpeg / ffprobe |
| 桌面壳 | [pywebview](https://pywebview.flowrl.com/) (WKWebView) |
| 前端 | 原生 HTML / CSS / JS（零依赖） |
| 打包 | py2app |

## 安装

### 1. 系统依赖

```bash
brew install ffmpeg
```

需要 Python 3.9+（macOS 自带即可）。

### 2. 项目依赖

```bash
git clone https://github.com/realruian/v2t.git
cd v2t
bash setup.sh        # 创建 .venv 并安装 faster-whisper / pywebview
```

### 3. 模型

二选一：

**A. 自动下载**（首次启动时）：~3GB，从 HuggingFace 直连，国内可能慢。

**B. 手动下载到本地目录**（推荐国内用户）：
```bash
bash download_model.sh   # 走 hf-mirror.com 镜像，~3GB
```
下载后会放到 `models/large-v3/`，启动时自动识别本地模型，无需联网。

### 4. 打包成 .app

```bash
bash build_app.sh        # alias 模式，30 秒；产物在 dist/V2T.app
# 或：
bash build_app.sh standalone   # 完整独立包（约 5-15 分钟，可分享）
```

把 `dist/V2T.app` 拖到 `/Applications/` 或 Dock，双击即开。

## 使用

1. 拖入音视频文件（支持多选） → 自动加入队列
2. 选语言（默认自动识别）+ 输出目录
3. 队列自动开始，每个文件转写完后自动接力下一个
4. 完成项点击展开 → 内嵌播放器 + 段落点击跳转 + 复制 / 导出

## 性能参考（Apple Silicon）

- M4 Pro：1 小时音频约 5–15 分钟
- 内存：~4GB
- 模式：CPU + int8（Apple Silicon 上 Metal 路径兼容性弱，CPU int8 反而最稳）

## 输出格式

```
output_dir/
├── filename.txt   # 纯文本
├── filename.srt   # 视频字幕
├── filename.vtt   # Web 字幕
└── filename.md    # 带时间戳的 Markdown
```

## 项目结构

```
v2t/
├── app.py            # pywebview 主程序 + JS API bridge
├── transcribe.py     # faster-whisper 封装 + 输出格式化
├── setup_app.py      # py2app 配置
├── make_icon.py      # 图标生成器
├── build_app.sh      # 打包脚本
├── setup.sh          # 依赖安装
├── download_model.sh # 镜像下载模型
├── icon.icns
└── web/              # 前端
    ├── index.html
    ├── style.css
    └── app.js
```

## 开发

不通过 .app 直接运行（开发调试）：

```bash
source .venv/bin/activate
python app.py
```

## License

MIT
