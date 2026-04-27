"""V2T desktop app — pywebview window with HTML/CSS/JS UI."""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import traceback
from pathlib import Path

import webview

from transcribe import Transcriber, save_outputs, CancelledError, _find_ffmpeg


STATE_FILE = Path.home() / ".config" / "V2T" / "state.json"

APP_VERSION = "0.1.1"

USER_MODELS_DIR = Path.home() / "Library" / "Application Support" / "V2T" / "models"
MODEL_FILES = ["config.json", "model.bin", "preprocessor_config.json",
               "tokenizer.json", "vocabulary.json"]
MODEL_BYTES_TOTAL = 3_086_000_000  # approx, for progress estimation
HF_MIRROR_BASE = "https://hf-mirror.com/Systran/faster-whisper-large-v3/resolve/main"


HERE = Path(__file__).parent.resolve()
WEB_DIR = HERE / "web"
DEFAULT_OUT_DIR = Path.home() / "Documents" / "V2T-Output"


def macos_notify(title: str, message: str):
    """Trigger a native macOS notification (best effort)."""
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{message}" with title "{title}" sound name "Glass"'],
            check=False, capture_output=True,
        )
    except Exception:
        pass


class Api:
    """Bridge object exposed to the JS frontend."""

    def __init__(self):
        self.transcriber = Transcriber(model_size="large-v3", compute_type="int8")
        self._window: webview.Window | None = None
        self._dl_state = {
            "active": False,
            "done": False,
            "error": None,
            "current_file": "",
            "bytes_done": 0,
            "bytes_total": MODEL_BYTES_TOTAL,
        }
        self._dl_proc = None

    def bind_window(self, window: webview.Window):
        self._window = window

    def _emit(self, event: str, payload):
        if self._window is None:
            return
        try:
            self._window.evaluate_js(
                f"window.__onPyEvent && window.__onPyEvent({{type:{event!r}, payload:{json.dumps(payload, ensure_ascii=False)}}})"
            )
        except Exception:
            pass

    # ---- exposed methods ----
    def pick_file(self):
        types = ("Media Files (*.mp3;*.wav;*.m4a;*.flac;*.aac;*.ogg;*.opus;*.mp4;*.mov;*.mkv;*.avi;*.webm;*.m4v)",
                 "All files (*.*)")
        result = self._window.create_file_dialog(webview.OPEN_DIALOG, file_types=types)
        if result and len(result) > 0:
            return result[0]
        return None

    def pick_files(self):
        """Multi-select variant for queue mode."""
        types = ("Media Files (*.mp3;*.wav;*.m4a;*.flac;*.aac;*.ogg;*.opus;*.mp4;*.mov;*.mkv;*.avi;*.webm;*.m4v)",
                 "All files (*.*)")
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG, file_types=types, allow_multiple=True
        )
        return list(result) if result else []

    def pick_output_dir(self):
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if result and len(result) > 0:
            return result[0]
        return None

    def default_output_dir(self):
        DEFAULT_OUT_DIR.mkdir(parents=True, exist_ok=True)
        return str(DEFAULT_OUT_DIR)

    def reveal(self, path: str):
        try:
            subprocess.run(["open", "-R", path], check=False)
        except Exception:
            pass

    def probe_media(self, path: str):
        """Return file size and audio duration (seconds) via ffprobe."""
        p = Path(path).expanduser()
        out = {"size": 0, "duration": 0.0}
        if not p.exists():
            return out
        try:
            out["size"] = p.stat().st_size
        except Exception:
            pass
        try:
            ffmpeg = _find_ffmpeg()
            ffprobe = ffmpeg.rsplit("ffmpeg", 1)[0] + "ffprobe"
            if not Path(ffprobe).exists():
                ffprobe = "ffprobe"
            r = subprocess.run(
                [ffprobe, "-v", "error",
                 "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
                capture_output=True, text=True, timeout=10,
            )
            txt = r.stdout.strip()
            if txt:
                out["duration"] = float(txt)
        except Exception:
            pass
        return out

    def save_state(self, data):
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps(data, ensure_ascii=False))
            return True
        except Exception:
            return False

    def load_state(self):
        try:
            if STATE_FILE.exists():
                return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
        return None

    def app_info(self):
        return {"version": APP_VERSION}

    # ---- Model management ----
    def _model_install_dir(self) -> Path:
        return USER_MODELS_DIR / "large-v3"

    def model_status(self):
        """Report whether a usable Whisper Large-V3 model is on disk."""
        # search across the same paths transcribe._resolve_model_id checks
        from transcribe import USER_DATA_MODELS, PROJECT_MODELS
        for root in (USER_DATA_MODELS, PROJECT_MODELS):
            cand = root / "large-v3"
            if cand.exists() and (cand / "model.bin").exists():
                return {"installed": True, "path": str(cand)}
        return {"installed": False, "install_to": str(self._model_install_dir())}

    def start_model_download(self):
        """Download model files to USER_MODELS_DIR/large-v3 in a worker thread.
        UI polls progress via model_download_progress()."""
        if self._dl_state["active"]:
            return False
        self._dl_state.update({
            "active": True, "done": False, "error": None,
            "current_file": "", "bytes_done": 0,
        })

        def worker():
            try:
                target = self._model_install_dir()
                target.mkdir(parents=True, exist_ok=True)
                cumulative = 0
                # Pre-compute remote sizes via HEAD (best effort) for accurate %
                sizes = {}
                for f in MODEL_FILES:
                    try:
                        r = subprocess.run(
                            ["curl", "-sIL", f"{HF_MIRROR_BASE}/{f}"],
                            capture_output=True, text=True, timeout=15,
                        )
                        for line in r.stdout.splitlines()[::-1]:
                            if line.lower().startswith("content-length:"):
                                sizes[f] = int(line.split(":")[1].strip()); break
                    except Exception:
                        pass
                total = sum(sizes.values()) or MODEL_BYTES_TOTAL
                self._dl_state["bytes_total"] = total

                for f in MODEL_FILES:
                    self._dl_state["current_file"] = f
                    out = target / f
                    if out.exists() and out.stat().st_size > 0 and \
                       sizes.get(f) and out.stat().st_size == sizes[f]:
                        cumulative += out.stat().st_size
                        self._dl_state["bytes_done"] = cumulative
                        continue

                    # curl with resume support
                    proc = subprocess.Popen(
                        ["curl", "-L", "-C", "-", "--fail", "--silent",
                         "-o", str(out), f"{HF_MIRROR_BASE}/{f}"],
                    )
                    self._dl_proc = proc
                    while proc.poll() is None:
                        try:
                            cur = out.stat().st_size if out.exists() else 0
                        except Exception:
                            cur = 0
                        self._dl_state["bytes_done"] = cumulative + cur
                        time.sleep(0.4)
                    self._dl_proc = None
                    if proc.returncode != 0:
                        raise RuntimeError(f"下载 {f} 失败（curl 返回 {proc.returncode}）")
                    cumulative += out.stat().st_size
                    self._dl_state["bytes_done"] = cumulative

                self._dl_state["done"] = True
                self._dl_state["active"] = False
                macos_notify("V2T 模型已就绪", "可以开始转写了")
            except Exception as e:
                traceback.print_exc()
                self._dl_state["error"] = f"{type(e).__name__}: {e}"
                self._dl_state["active"] = False

        threading.Thread(target=worker, daemon=True).start()
        return True

    def model_download_progress(self):
        s = self._dl_state
        total = s["bytes_total"] or 1
        pct = max(0.0, min(100.0, s["bytes_done"] * 100.0 / total))
        return {**s, "pct": pct}

    def cancel_model_download(self):
        if self._dl_proc is not None:
            try: self._dl_proc.terminate()
            except Exception: pass
        self._dl_state["active"] = False
        self._dl_state["error"] = "已取消"
        return True

    def reveal_models_dir(self):
        d = self._model_install_dir()
        d.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(["open", str(d)], check=False)
        except Exception:
            pass

    def cancel(self):
        self.transcriber.cancel()
        return True

    def transcribe(self, media_path: str, language: str, output_dir: str):
        def worker():
            try:
                self._emit("status", "running")
                result = self.transcriber.transcribe(
                    media_path,
                    language=language,
                    progress=lambda p: self._emit("progress", p),
                )
                self._emit("progress", {"label": "写出文件…", "pct": 99})
                paths = save_outputs(result, output_dir)
                self._emit("done", {
                    "language": result["language"],
                    "duration": result["duration"],
                    "text": result["text"],
                    "segments": result["segments"],
                    "files": paths,
                })
                macos_notify("V2T 转写完成", Path(media_path).name)
            except CancelledError:
                self._emit("cancelled", None)
            except Exception as e:
                traceback.print_exc()
                self._emit("error", f"{type(e).__name__}: {e}")

        threading.Thread(target=worker, daemon=True).start()
        return True


def main():
    api = Api()
    window = webview.create_window(
        title="V2T",
        url=str(WEB_DIR / "index.html"),
        js_api=api,
        width=820,
        height=640,
        min_size=(680, 540),
    )
    api.bind_window(window)
    # vibrancy=True gives a translucent macOS look; falls back gracefully on older systems
    try:
        webview.start(debug=False, private_mode=False)
    except TypeError:
        webview.start(debug=False)


if __name__ == "__main__":
    main()
