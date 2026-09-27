"""Tổng hợp giọng nói: VieNeu-TTS cho tiếng Việt, Edge TTS fallback."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import EDGE_VOICE_MAP, VIENEU_DEFAULT_VOICE, VIENEU_MODE
from .media import change_tempo, duration_seconds
from .transcribe import Segment

ProgressFn = Callable[[str, float], None]

_vieneu_engine = None

# Phương án A: tăng tốc câu trước khi đè lên câu sau.
MAX_OVERLAP_TEMPO = 1.85
MIN_OVERLAP_TEMPO = 1.08
OVERLAP_GAP_MS = 50
OVERLAP_FADE_MS = 70
MIN_SLOT_MS = 200


def get_vieneu(mode: str | None = None, threads: int = 2, steps: int = 8):
    global _vieneu_engine
    if _vieneu_engine is None:
        from vieneu import Vieneu

        _vieneu_engine = Vieneu(mode=mode or VIENEU_MODE, threads=threads, steps=steps)
    return _vieneu_engine


def list_vieneu_voices() -> list[tuple[str, str]]:
    try:
        return get_vieneu().list_preset_voices()
    except Exception:
        return [
            ("Đức Trí — Nam · Bắc · Đọc truyện", "Đức Trí"),
            ("Anh Khôi — Nam · Bắc · Kể chuyện", "Anh Khôi"),
            ("Minh Quân — Nam · Bắc · Tự nhiên", "Minh Quân"),
            ("Mai Anh — Nữ · Bắc · Tin tức", "Mai Anh"),
            ("Trúc Ly — Nữ · Bắc · Tự nhiên", "Trúc Ly"),
        ]


def synthesize_vieneu(text: str, voice: str, out_path: Path, steps: int = 8) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    engine = get_vieneu()
    audio = engine.infer(text, voice=voice, steps=steps, sway=-1)
    dest = out_path.with_suffix(".wav")
    engine.save(audio, dest)
    return dest


async def _synth_edge(text: str, voice: str, out_path: Path) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text=text, voice=voice, rate="+0%")
    await communicate.save(str(out_path))


def synthesize_edge(text: str, voice: str, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(_synth_edge(text, voice, out_path))
    return out_path


def synthesize_segment(
    text: str,
    voice: str,
    out_path: Path,
    engine: str = "auto",
) -> Path:
    use_vieneu = engine == "vieneu" or (
        engine == "auto" and not str(voice).startswith(("vi-VN-", "en-", "zh-", "ja-", "ko-"))
    )
    if use_vieneu:
        return synthesize_vieneu(text, voice, out_path)
    return synthesize_edge(text, voice, out_path)


@dataclass
class _Clip:
    index: int
    start_ms: int
    path: Path
    text: str


def resolve_overlaps(
    clips: list[_Clip],
    work_dir: Path,
    max_tempo: float = MAX_OVERLAP_TEMPO,
    progress: ProgressFn | None = None,
) -> list[_Clip]:
    """Tăng tốc câu i nếu audio đè lên start của câu i+1. Không cắt cứng giữa từ."""
    from pydub import AudioSegment

    if len(clips) < 2:
        return clips

    resolved: list[_Clip] = list(clips)
    n = len(resolved)
    sped = 0
    faded = 0

    for i in range(n - 1):
        cur = resolved[i]
        nxt = resolved[i + 1]
        slot_ms = nxt.start_ms - cur.start_ms - OVERLAP_GAP_MS
        if slot_ms < MIN_SLOT_MS:
            slot_ms = MIN_SLOT_MS

        try:
            clip = AudioSegment.from_file(cur.path)
        except Exception:
            continue

        extra = len(clip) - slot_ms
        if extra <= 0:
            continue

        tempo = len(clip) / float(slot_ms)
        if tempo < MIN_OVERLAP_TEMPO:
            continue

        tempo = min(max_tempo, tempo)
        fast_path = work_dir / f"seg_{cur.index:04d}_ovl.wav"
        try:
            change_tempo(cur.path, fast_path, tempo)
            clip = AudioSegment.from_file(fast_path)
            cur = _Clip(cur.index, cur.start_ms, fast_path, cur.text)
            sped += 1
        except Exception:
            clip = AudioSegment.from_file(cur.path)

        if len(clip) > slot_ms:
            fade = min(OVERLAP_FADE_MS, max(20, slot_ms // 5))
            trimmed = clip[:slot_ms].fade_out(fade)
            fade_path = work_dir / f"seg_{cur.index:04d}_fade.wav"
            trimmed.export(fade_path, format="wav")
            cur = _Clip(cur.index, cur.start_ms, fade_path, cur.text)
            faded += 1

        resolved[i] = cur
        if progress:
            progress(
                f"Xử lý chồng câu {i + 1}/{n - 1}…",
                0.90 + 0.04 * (i + 1) / max(1, n - 1),
            )

    if progress:
        progress(f"Chồng: tăng tốc {sped} câu, fade {faded} câu.", 0.94)
    return resolved


def build_dub_track(
    segments: list[Segment],
    total_duration: float,
    work_dir: Path,
    output_wav: Path,
    target_lang: str,
    voice: str | None = None,
    fit_timing: bool = True,
    progress: ProgressFn | None = None,
    engine: str = "auto",
    resolve_overlap: bool = True,
    max_overlap_tempo: float = MAX_OVERLAP_TEMPO,
) -> Path:
    from pydub import AudioSegment

    import importlib.util
    has_vieneu = importlib.util.find_spec("vieneu") is not None

    if voice is None:
        if target_lang == "vi" and has_vieneu and engine != "edge":
            voice = VIENEU_DEFAULT_VOICE
        else:
            voice = EDGE_VOICE_MAP.get(target_lang, "vi-VN-HoaiMyNeural" if target_lang == "vi" else "en-US-JennyNeural")

    if engine == "auto" and target_lang == "vi" and not str(voice).startswith("vi-VN-") and has_vieneu:
        engine = "vieneu"
    elif engine == "auto":
        engine = "edge"

    work_dir.mkdir(parents=True, exist_ok=True)
    canvas_ms = max(1, int(total_duration * 1000) + 250)
    timeline = AudioSegment.silent(duration=canvas_ms)

    n = max(1, len(segments))
    clips: list[_Clip] = []

    for i, seg in enumerate(segments, start=1):
        text = (seg.translated or seg.text or "").strip()
        if not text:
            continue
        raw_path = work_dir / f"seg_{seg.index:04d}.wav"
        fitted_path = work_dir / f"seg_{seg.index:04d}_fit.wav"
        try:
            produced = synthesize_segment(text, voice, raw_path, engine=engine)
        except Exception:
            if progress:
                progress(f"Bỏ qua TTS đoạn {i} (lỗi giọng).", 0.76 + 0.14 * i / n)
            continue

        clip_path = produced
        if fit_timing:
            tts_dur = duration_seconds(produced)
            target = max(0.35, seg.duration)
            if tts_dur > 0.05:
                tempo = min(1.55, max(0.75, tts_dur / target)) if target > 0 else 1.0
                try:
                    change_tempo(produced, fitted_path, tempo)
                    clip_path = fitted_path
                except Exception:
                    clip_path = produced

        clips.append(
            _Clip(
                index=seg.index,
                start_ms=max(0, int(seg.start * 1000)),
                path=clip_path,
                text=text,
            )
        )
        if progress:
            progress(f"Lồng tiếng {i}/{n} đoạn…", 0.76 + 0.14 * i / n)

    if resolve_overlap:
        clips = resolve_overlaps(
            clips,
            work_dir,
            max_tempo=max_overlap_tempo,
            progress=progress,
        )

    for clip in clips:
        try:
            audio = AudioSegment.from_file(clip.path)
        except Exception:
            continue
        timeline = timeline.overlay(audio, position=clip.start_ms)

    output_wav.parent.mkdir(parents=True, exist_ok=True)
    timeline.export(output_wav, format="wav")
    return output_wav
