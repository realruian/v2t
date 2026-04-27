"""V2T desktop app — pywebview window with HTML/CSS/JS UI."""
from __future__ import annotations

import json
import os
import subprocess
import threading
import traceback
from pathlib import Path

import webview

from transcribe import Transcriber, save_outputs, CancelledError, _find_ffmpeg


STATE_FILE = Path.home() / ".config" / "V2T" / "state.json"


HERE = Path(__file__).parent.resolve()
WEB_DIR = HERE / "web"
DEFAULT_OUT_DIR = Path.home() / "Desktop" / "V2T-Output"


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
