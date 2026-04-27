# V2T

本地 macOS 视频/音频转文字工具：pywebview 壳 + Python (faster-whisper) 后端 + 原生 JS 前端。串行队列调度，状态持久化。

## Dev commands

```bash
# 一次性环境（创建 .venv + 安装依赖）
bash setup.sh

# 开发期：直接跑（用 Python 启动，不打包）
source .venv/bin/activate && python app.py

# 打包 .app（alias 模式，30 秒，依赖项目目录的 .venv）
bash build_app.sh

# 打包 .app（standalone 模式，~5 分钟，可分发，~170MB）
bash build_app.sh standalone

# 模型下载（hf-mirror.com，~3GB → models/large-v3/）
bash download_model.sh

# 验证语法（无单元测试，至少跑这两个）
node --check web/app.js
python3 -c "import ast; ast.parse(open('app.py').read()); ast.parse(open('transcribe.py').read())"
```

**修改代码后必须跑**：上面两条语法检查 + 重新 `bash build_app.sh` + 启动验证窗口能开。

## 发版流程

```bash
# 1. standalone 打包 → 生成 .dmg
bash build_app.sh standalone
# DMG 拼装：cp dist/V2T.app + ln -s /Applications + hdiutil create UDZO

# 2. tag + push
git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z

# 3. release（带 DMG 资产）
gh release create vX.Y.Z dist/V2T-X.Y.Z.dmg --title "V2T vX.Y.Z" --notes "..."
```

## 架构

```
V2T.app
└─ pywebview (WKWebView)
   ├─ web/index.html  状态机 body[data-state="empty|hasItems"]
   ├─ web/app.js      队列调度（前端管，串行）+ ffprobe 元信息 + 模型下载流程
   ├─ web/style.css   macOS tokens（8px 圆角 / 系统蓝 / 4-倍间距）
   └─ ↕ js_api ↕ Python (app.py)
       └─ Transcriber (transcribe.py) → faster-whisper Large-V3 (CPU int8)
           └─ ffmpeg → audio extraction
```

**前端调度**：JS 维护 `state.items[]`，每个 item 有 `queued|running|done|error|cancelled`。`scheduleNext()` 在 done/error/cancelled 时被调用，挑下一个 queued 项调 `pywebview.api.transcribe()`。Python 后端**不知道队列**，只串行处理一个文件。

**事件契约（Python → JS）**：`window.__onPyEvent({type, payload})` 中 type ∈ `progress | status | done | error | cancelled`。done 的 payload 含 `language, duration, text, segments[], files{txt,srt,vtt,md}`。

## 文件地图

| 文件 | 职责 |
|---|---|
| `app.py` | pywebview 入口；`Api` 类暴露给 JS（pick_files / probe_media / transcribe / save_state / model_status / start_model_download / ...）；版本号 `APP_VERSION` 在这里 |
| `transcribe.py` | faster-whisper 封装；模型搜索路径；ffmpeg 查找；输出 4 种格式 |
| `setup_app.py` | py2app 配置；plist 含 `CFBundleIdentifier=com.v2t.app`、`LSMultipleInstancesProhibited=true` |
| `build_app.sh` | 打包脚本（默认 alias，加 `standalone` 参数走完整模式） |
| `make_icon.py` | 程序化生成 `icon.icns`（不需要外部设计资源） |
| `download_model.sh` | 从 hf-mirror.com 下载模型到 `models/large-v3/` |
| `web/app.js` | 队列状态机、渲染、拖拽重排、ffprobe 探测、模型下载 banner |
| `web/index.html` | DOM 结构（顶栏 + banner + 列表 + 状态栏） |
| `web/style.css` | 全部样式；用 `body[data-state]` + `data-show` 控制显隐 |

## 关键路径约定

| 数据 | 位置 |
|---|---|
| Whisper 模型 | 优先 `~/Library/Application Support/V2T/models/large-v3/`（.app 装时用），其次 `<项目>/models/large-v3/`（开发期）|
| 队列持久化 | `~/.config/V2T/state.json`（含 items + language + outputDir） |
| 默认输出目录 | `~/Documents/V2T-Output/` |
| HF 镜像 | `https://hf-mirror.com/Systran/faster-whisper-large-v3` |
| Bundle ID | `com.v2t.app` |

## 踩坑笔记（不要再踩）

1. **CSS `[hidden]` 属性会被 `display: flex` 覆盖** —— 必须显式写 `[hidden] { display: none !important }`，否则 hidden 元素照样显示。
2. **从 Finder 启动的 .app 不继承 shell PATH** —— 调用 `ffmpeg` 必须 fallback 写死 `/opt/homebrew/bin/ffmpeg`，不能只靠 PATH。`transcribe._find_ffmpeg()` 已处理。
3. **homebrew 的 ffmpeg 不能直接打包进 .app** —— 它依赖 `/opt/homebrew/Cellar/` 下一堆 dylib。要内置必须用静态版（evermeet.cx）或 brew 的 `--with-static`。当前选择是要求用户自己 `brew install ffmpeg`。
4. **py2app alias 模式硬链到 .venv 路径** —— 不可分发，体积小（~200KB）但只在本机能跑。要分发必须 `bash build_app.sh standalone`（~170MB）。
5. **HuggingFace 直连国内极慢** —— 模型下载默认走 `hf-mirror.com` 镜像。faster-whisper 的 `WhisperModel("large-v3")` 自动下载用 HF 直连，所以**首次必须靠我们的 banner / 脚本走镜像**，不要让 faster-whisper 默认下载。
6. **`LSMultipleInstancesProhibited`** 防止双击 .app 开多实例（之前会出现 Dock 一排 Python 火箭）。修改 plist 后必须重新打包才生效。
7. **WhisperModel 在 macOS Apple Silicon 上**用 `device="cuda"` 或 metal 路径有兼容性问题。**只用 `device="cpu", compute_type="int8"`**，速度反而最稳。
8. **pywebview 的 `create_file_dialog`** 默认单选，要多选必须传 `allow_multiple=True`，所以 `pick_file` / `pick_files` 是两个不同的 API。
9. **pywebview 暴露的 `f.path`** 在 macOS 拖拽事件中可用（Webkit 扩展），是从 JS 拿到本地文件路径的唯一方式。**不要尝试用 `FileReader` 读内容**，Python 后端只接受路径字符串。
10. **修改 plist / 资源后** alias 模式可以用 `bash build_app.sh` 30 秒重打包，但**修改 Python 业务逻辑后**已运行的 alias .app 会立即生效（因为 alias 链接到源码），不必重打包；只有改 plist / 入口点才需要。

## 版本与发布历史

- v0.1.0 — 首次公开 release（队列、音频段跳转、持久化）
- v0.1.1 — 模型下载 banner / 分析中徽标 / 拖拽 grip 常驻 / 默认 ~/Documents

## 不在范围内的事（明确不做）

- 代码签名 / 公证（要 Apple Developer $99/年）→ 用户首次启动右键打开绕过 Gatekeeper
- App Store 上架
- Sparkle 自动更新
- 内嵌 ffmpeg（依赖问题，要静态版）
- 说话人分离 / 行内编辑 / 全局搜索（v3 议题）
