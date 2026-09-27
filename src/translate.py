"""Dịch từng đoạn thoại: Hỗ trợ Gemini Round-Robin (nhiều key) và fallback Google Translate."""

from __future__ import annotations

import logging
from typing import Callable

from .gemini_rotator import GeminiRotator, get_shared_rotator
from .transcribe import Segment

logger = logging.getLogger(__name__)
ProgressFn = Callable[[str, float], None]


class Translator:
    def __init__(
        self,
        target_lang: str = "vi",
        source_lang: str = "auto",
        rotator: GeminiRotator | None = None,
    ) -> None:
        self.target_lang = target_lang
        self.source_lang = source_lang
        self.rotator = rotator if rotator is not None else get_shared_rotator()
        if self.rotator.total_keys > 0:
            logger.info(
                f"Đã kích hoạt Gemini Round-Robin với {self.rotator.total_keys} API keys."
            )
        else:
            logger.info("Chưa có Gemini API key nào, dùng Google Translate mặc định.")

    def _translate_google_batch(self, batch: list[str], idxs: list[int], segments: list[Segment]) -> None:
        from deep_translator import GoogleTranslator

        src = self.source_lang if self.source_lang and self.source_lang != "auto" else "auto"
        try:
            translator = GoogleTranslator(source=src, target=self.target_lang)
            translated = translator.translate_batch(batch)
            if not isinstance(translated, list) or len(translated) != len(batch):
                raise ValueError("batch lệch")
            for j, dst in zip(idxs, translated):
                segments[j].translated = (dst or segments[j].text).strip()
        except Exception:
            for j, src_text in zip(idxs, batch):
                try:
                    t = GoogleTranslator(source=src, target=self.target_lang).translate(src_text)
                    segments[j].translated = (t or segments[j].text).strip()
                except Exception:
                    segments[j].translated = segments[j].text

    def translate_segments(
        self,
        segments: list[Segment],
        progress: ProgressFn | None = None,
    ) -> list[Segment]:
        if self.target_lang == self.source_lang:
            for seg in segments:
                seg.translated = seg.text
            return segments

        n = max(1, len(segments))

        # Ưu tiên 1: Dùng Gemini Round-Robin nếu có keys
        if self.rotator.total_keys > 0:
            if progress:
                progress(f"Đang dịch {n} câu bằng Gemini Flash ({self.rotator.total_keys} keys xoay vòng)...", 0.60)

            # Chia batch 20 câu để prompt hiệu quả và giữ ngữ cảnh
            batch_size = 20
            for start_idx in range(0, n, batch_size):
                sub_segs = segments[start_idx : start_idx + batch_size]
                items = [
                    {
                        "index": seg.index,
                        "text": seg.text or "",
                        "duration": seg.duration,
                    }
                    for seg in sub_segs
                    if (seg.text or "").strip()
                ]

                vi_results = self.rotator.translate_batch(
                    items, source_lang=self.source_lang, target_lang=self.target_lang
                )

                # Điền kết quả dịch
                for seg in sub_segs:
                    if seg.index in vi_results:
                        seg.translated = vi_results[seg.index].strip()
                    elif not seg.translated:
                        # Fallback riêng cho câu bị thiếu
                        seg.translated = seg.text

                cur_done = min(n, start_idx + batch_size)
                if progress:
                    progress(f"Đã dịch {cur_done}/{n} đoạn (Gemini)...", 0.58 + 0.16 * cur_done / n)

            return segments

        # Ưu tiên 2: Fallback Google Translate
        batch: list[str] = []
        idxs: list[int] = []
        for i, seg in enumerate(segments):
            text = (seg.text or "").strip()
            if not text:
                seg.translated = ""
                continue
            batch.append(text)
            idxs.append(i)
            if len(batch) >= 25 or i == len(segments) - 1:
                self._translate_google_batch(batch, idxs, segments)
                batch, idxs = [], []
                if progress:
                    progress(f"Đã dịch {i + 1}/{n} đoạn (Google Translate)...", 0.58 + 0.16 * (i + 1) / n)
        return segments
