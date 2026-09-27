"""Nhận dạng giọng nói bằng faster-whisper."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import WHISPER_LANG_MAP

ProgressFn = Callable[[str, float], None]


@dataclass
class Segment:
    index: int
    start: float
    end: float
    text: str
    translated: str = ""

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


_GLOBAL_WHISPER_CACHE: dict[tuple[str, str, str], Any] = {}


class Transcriber:
    def __init__(
        self,
        model_size: str = "medium",
        device: str = "auto",
        compute_type: str = "auto",
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        from faster_whisper import WhisperModel

        device = self.device
        compute = self.compute_type
        if device == "auto":
            try:
                import ctranslate2

                device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
            except Exception:
                try:
                    import torch

                    device = "cuda" if torch.cuda.is_available() else "cpu"
                except Exception:
                    device = "cpu"
        if compute == "auto":
            compute = "float16" if device == "cuda" else "int8"

        cache_key = (self.model_size, device, compute)
        if cache_key in _GLOBAL_WHISPER_CACHE:
            self._model = _GLOBAL_WHISPER_CACHE[cache_key]
            return self._model

        # Đăng ký thư mục DLL của NVIDIA trên Windows (cublas, cudnn)
        import sys, os
        if sys.platform == "win32":
            for p in sys.path:
                for sub in [("nvidia", "cublas", "bin"), ("nvidia", "cudnn", "bin"), ("nvidia", "cuda_nvrtc", "bin")]:
                    d = os.path.join(p, *sub)
                    if os.path.isdir(d):
                        try:
                            os.add_dll_directory(d)
                        except Exception:
                            pass
                        if d not in os.environ.get("PATH", ""):
                            os.environ["PATH"] = d + ";" + os.environ.get("PATH", "")

        try:
            self._model = WhisperModel(
                self.model_size,
                device=device,
                compute_type=compute,
            )
        except Exception as exc:
            err_str = str(exc).lower()
            if device == "cuda" and ("cublas" in err_str or "cudnn" in err_str or "dll" in err_str or "library" in err_str):
                print(f"\n[Cảnh báo] Chưa load được CUDA DLL ({exc}). Tự động chuyển sang CPU để tiếp tục không bị gián đoạn...")
                self._model = WhisperModel(
                    self.model_size,
                    device="cpu",
                    compute_type="int8",
                )
            else:
                raise
        _GLOBAL_WHISPER_CACHE[cache_key] = self._model
        return self._model

    def run(
        self,
        audio_path: Path,
        source_lang: str = "auto",
        progress: ProgressFn | None = None,
    ) -> tuple[list[Segment], str]:
        model = self._load()
        whisper_lang = WHISPER_LANG_MAP.get(source_lang, source_lang)
        if whisper_lang == "auto":
            whisper_lang = None

        if progress:
            progress("Đang nhận dạng giọng nói…", 0.15)

        segments_iter, info = model.transcribe(
            str(audio_path),
            language=whisper_lang,
            vad_filter=True,
            beam_size=5,
        )
        detected = info.language or "unknown"
        out: list[Segment] = []
        for i, seg in enumerate(segments_iter, start=1):
            text = (seg.text or "").strip()
            if not text:
                continue
            out.append(
                Segment(
                    index=i,
                    start=float(seg.start or 0.0),
                    end=float(seg.end or 0.0),
                    text=text,
                )
            )
            if progress and i % 8 == 0:
                progress(f"Đã nhận {i} đoạn thoại…", min(0.55, 0.15 + i * 0.01))

        if progress:
            progress(f"Xong nhận dạng ({len(out)} đoạn, lang={detected}).", 0.58)
        return out, detected
