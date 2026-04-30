"""Core transcription engine using faster-whisper."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from faster_whisper import WhisperModel


def _bundled_resources_dir() -> Path | None:
    """If running from a py2app bundle, return its Resources dir (where we
    ship ffmpeg/ffprobe). Otherwise None."""
    here = Path(__file__).resolve()
    # In a py2app bundle, this file sits at .../V2T.app/Contents/Resources/
    if "Contents/Resources" in str(here):
        return here.parent
    return None


def _find_ffmpeg() -> str:
    """Locate ffmpeg, preferring a copy bundled inside the .app."""
    bundled = _bundled_resources_dir()
    if bundled:
        candidate = bundled / "Frameworks" / "ffmpeg"
        if candidate.exists():
            return str(candidate)
    found = shutil.which("ffmpeg")
    if found:
        return found
    for p in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"):
        if Path(p).exists():
            return p
    raise RuntimeError("未找到 ffmpeg。请先安装：brew install ffmpeg")


FFMPEG = None  # lazy

# Model search order:
#   1. ~/Library/Application Support/V2T/models/<size>/   (user-installed)
#   2. <project>/models/<size>/                            (dev/alias mode)
USER_DATA_MODELS = Path.home() / "Library" / "Application Support" / "V2T" / "models"
PROJECT_MODELS   = Path(__file__).parent / "models"
REQUIRED_MODEL_FILES = (
    "config.json",
    "model.bin",
    "preprocessor_config.json",
    "tokenizer.json",
    "vocabulary.json",
)


class ModelNotInstalledError(RuntimeError):
    pass


def model_is_complete(model_dir: Path) -> bool:
    return model_dir.exists() and all(
        (model_dir / name).exists() and (model_dir / name).stat().st_size > 0
        for name in REQUIRED_MODEL_FILES
    )


def _resolve_model_id(size: str) -> str:
    """Return a local model path, or raise instead of triggering HF auto-download."""
    for root in (USER_DATA_MODELS, PROJECT_MODELS):
        cand = root / size
        if model_is_complete(cand):
            return str(cand)
    raise ModelNotInstalledError(
        "Whisper Large-V3 模型未安装或不完整。请先点击顶部横幅下载模型，"
        "或运行 bash download_model.sh。"
    )


AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus", ".wma"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".wmv", ".m4v"}


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTS


def extract_audio(video_path: Path, out_dir: Path) -> Path:
    global FFMPEG
    if FFMPEG is None:
        FFMPEG = _find_ffmpeg()
    out = out_dir / (video_path.stem + ".wav")
    cmd = [
        FFMPEG, "-y", "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", str(out),
        "-loglevel", "error",
    ]
    subprocess.run(cmd, check=True)
    return out


def format_timestamp(seconds: float, srt: bool = True) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    sep = "," if srt else "."
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def format_duration_compact(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60:02d}s"
    return f"{seconds // 3600}h {(seconds % 3600) // 60:02d}m"


class CancelledError(Exception):
    pass


class Transcriber:
    """Wraps faster-whisper Large-V3. Loads model lazily."""

    def __init__(self, model_size: str = "large-v3", compute_type: str = "int8"):
        self.model_size = model_size
        self.compute_type = compute_type
        self._model: Optional[WhisperModel] = None
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def _check_cancel(self):
        if self._cancel.is_set():
            raise CancelledError()

    def load(self, progress: Optional[Callable] = None):
        if self._model is not None:
            return
        model_id = _resolve_model_id(self.model_size)
        is_local = Path(model_id).exists()
        if progress:
            label = "加载本地 Whisper Large-V3 模型…" if is_local \
                    else "下载 Whisper Large-V3 模型（首次约 3GB）…"
            progress({"label": label, "indeterminate": True})
        self._model = WhisperModel(
            model_id, device="cpu", compute_type=self.compute_type
        )
        if progress:
            progress({"label": "模型已加载", "indeterminate": True})

    def transcribe(
        self,
        media_path: str,
        language: Optional[str] = None,
        progress: Optional[Callable] = None,
    ) -> dict:
        self._cancel.clear()
        path = Path(media_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(path)

        self.load(progress)
        self._check_cancel()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            if is_video(path):
                if progress:
                    progress({"label": "提取音轨…", "indeterminate": True})
                audio_path = extract_audio(path, tmp_dir)
            else:
                audio_path = path
            self._check_cancel()

            if progress:
                progress({"label": "开始转写…", "indeterminate": True})

            segments_iter, info = self._model.transcribe(
                str(audio_path),
                language=language if language and language != "auto" else None,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
                beam_size=5,
            )

            total = info.duration or 0.0
            start_time = time.time()
            segments = []
            for seg in segments_iter:
                self._check_cancel()
                segments.append({
                    "id": seg.id,
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text.strip(),
                })
                if progress and total:
                    pct = min(99, seg.end / total * 100)
                    elapsed = time.time() - start_time
                    eta = ""
                    if pct > 1:
                        remaining = elapsed * (100 - pct) / pct
                        eta = f"剩余约 {format_duration_compact(remaining)}"
                    progress({
                        "pct": pct,
                        "eta": eta,
                        "label": f"转写中 · {format_timestamp(seg.end, False)} / {format_timestamp(total, False)}",
                    })

            return {
                "language": info.language,
                "duration": total,
                "segments": segments,
                "text": "\n".join(s["text"] for s in segments),
                "source": str(path),
            }


def to_srt(segments: list[dict]) -> str:
    out = []
    for i, s in enumerate(segments, 1):
        out.append(str(i))
        out.append(f"{format_timestamp(s['start'])} --> {format_timestamp(s['end'])}")
        out.append(s["text"])
        out.append("")
    return "\n".join(out)


def to_vtt(segments: list[dict]) -> str:
    out = ["WEBVTT", ""]
    for s in segments:
        out.append(f"{format_timestamp(s['start'], False)} --> {format_timestamp(s['end'], False)}")
        out.append(s["text"])
        out.append("")
    return "\n".join(out)


def to_markdown(result: dict) -> str:
    src = Path(result["source"]).name
    lines = [
        f"# {src}", "",
        f"- 语言: {result['language']}",
        f"- 时长: {format_timestamp(result['duration'], False)}",
        "", "---", "",
    ]
    for s in result["segments"]:
        lines.append(f"**[{format_timestamp(s['start'], False)}]** {s['text']}")
        lines.append("")
    return "\n".join(lines)


def _unique_output_paths(out_dir: Path, stem: str) -> dict:
    def paths_for(base: str) -> dict:
        return {
            "txt": out_dir / f"{base}.txt",
            "srt": out_dir / f"{base}.srt",
            "vtt": out_dir / f"{base}.vtt",
            "md":  out_dir / f"{base}.md",
            "json": out_dir / f"{base}.json",
        }

    paths = paths_for(stem)
    if not any(p.exists() for p in paths.values()):
        return paths

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for i in range(100):
        suffix = f"{timestamp}" if i == 0 else f"{timestamp}-{i + 1}"
        paths = paths_for(f"{stem}-{suffix}")
        if not any(p.exists() for p in paths.values()):
            return paths
    raise RuntimeError("无法生成不冲突的输出文件名")


def save_outputs(result: dict, out_dir: str) -> dict:
    out = Path(out_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(result["source"]).stem
    paths = _unique_output_paths(out, stem)
    paths["txt"].write_text(result["text"], encoding="utf-8")
    paths["srt"].write_text(to_srt(result["segments"]), encoding="utf-8")
    paths["vtt"].write_text(to_vtt(result["segments"]), encoding="utf-8")
    paths["md"].write_text(to_markdown(result), encoding="utf-8")
    paths["json"].write_text(json.dumps({
        "language": result["language"],
        "duration": result["duration"],
        "text": result["text"],
        "segments": result["segments"],
        "source": result["source"],
    }, ensure_ascii=False), encoding="utf-8")
    return {k: str(v) for k, v in paths.items()}
