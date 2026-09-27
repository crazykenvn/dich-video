"""Gemini Smart Round-Robin Key Manager & Batch Translator.

Sử dụng REST API trực tiếp với model gemini-3.1-flash-lite / gemini-3.5-flash-lite
để đạt tốc độ cao nhất, không bị lỗi 503 spike, hỗ trợ xoay vòng nhiều tài khoản
Google Gemini (Round-Robin) với cơ chế tự động bắt lỗi Rate Limit 429 và failover
sang key tiếp theo. Tự động kiểm soát độ dài câu dịch theo thời lượng (duration)
của câu gốc tiếng Trung.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

COOLDOWN_SECONDS = 65
PRIMARY_MODELS = ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-flash-latest"]


@dataclass
class KeySlot:
    key: str
    cooldown_until: float = 0.0

    @property
    def is_available(self) -> bool:
        return time.time() >= self.cooldown_until


class GeminiRotator:
    def __init__(self, keys_file: Path | str | None = None, keys: list[str] | None = None):
        self.slots: list[KeySlot] = []
        self._current_idx = 0

        # 1. Nạp từ list truyền vào
        if keys:
            for k in keys:
                k_clean = k.strip()
                if k_clean and not k_clean.startswith("#"):
                    self.slots.append(KeySlot(key=k_clean))

        # 2. Nạp từ file gemini_keys.txt nếu chưa có
        if not self.slots:
            target_file = Path(keys_file) if keys_file else Path("gemini_keys.txt")
            if not target_file.is_absolute():
                candidates = [
                    Path.cwd() / target_file,
                    Path(__file__).resolve().parent.parent / target_file,
                ]
                for c in candidates:
                    if c.exists():
                        target_file = c
                        break

            if target_file.exists():
                for line in target_file.read_text(encoding="utf-8").splitlines():
                    k_clean = line.strip()
                    if k_clean and not k_clean.startswith("#"):
                        self.slots.append(KeySlot(key=k_clean))

        # 3. Nạp từ biến môi trường
        if not self.slots:
            env_keys = os.getenv("GEMINI_API_KEYS", "") or os.getenv("GEMINI_API_KEY", "")
            for k in env_keys.replace(";", ",").split(","):
                k_clean = k.strip()
                if k_clean:
                    self.slots.append(KeySlot(key=k_clean))

    @property
    def total_keys(self) -> int:
        return len(self.slots)

    def get_next_key(self) -> str | None:
        """Lấy key khả dụng tiếp theo theo thuật toán Round-Robin."""
        if not self.slots:
            return None

        n = len(self.slots)
        now = time.time()

        for _ in range(n):
            slot = self.slots[self._current_idx]
            self._current_idx = (self._current_idx + 1) % n
            if slot.is_available:
                return slot.key

        min_cooldown = min(s.cooldown_until for s in self.slots)
        wait_s = max(1.0, min_cooldown - now)
        logger.warning(
            f"Tất cả {n} Gemini API keys đang bận/cooldown. Chờ {wait_s:.1f}s..."
        )
        time.sleep(wait_s)
        return self.slots[0].key

    def mark_rate_limited(self, key_str: str) -> None:
        """Đánh dấu key bị lỗi 429 và cho ngủ COOLDOWN_SECONDS."""
        for slot in self.slots:
            if slot.key == key_str:
                slot.cooldown_until = time.time() + COOLDOWN_SECONDS
                logger.warning(
                    f"Key ...{key_str[-6:]} bị Rate Limit. Tạm dừng {COOLDOWN_SECONDS}s, chuyển sang key khác."
                )
                break

    def translate_batch(
        self,
        items: list[dict[str, Any]],
        source_lang: str = "zh",
        target_lang: str = "vi",
        max_retries: int = 3,
    ) -> dict[int, str]:
        """
        Dịch 1 batch câu thoại tiếng Trung sang tiếng Việt.
        items: [{"index": int, "text": str, "duration": float}]
        Trả về: {index: "câu tiếng Việt"}
        """
        if not self.slots or not items:
            return {}

        prompt = f"""Bạn là biên dịch viên phim và biên kịch lồng tiếng (Voiceover/Dubbing) chuyên nghiệp từ tiếng Trung sang tiếng Việt.

Nhiệm vụ: Dịch danh sách các câu thoại tiếng Trung sau sang tiếng Việt.

YÊU CẦU BẮT BUỘC:
1. Văn phong tự nhiên, chuẩn khẩu ngữ, xưng hô phù hợp ngữ cảnh đời sống/phim ảnh Việt Nam.
2. ĐẶC BIỆT VỀ ĐỘ DÀI: Tiếng Trung phát âm rất nhanh và ngắn. Câu tiếng Việt dịch ra PHẢI THẬT SÚC TÍCH, CÔ ĐỌNG, số âm tiết vừa vặn với thời lượng (duration_seconds) được quy định để diễn viên lồng tiếng nói kịp timeline. TUYỆT ĐỐI không dịch rườm rà, thừa từ.
3. Giữ nguyên nghĩa chính xác, không lược bỏ thông tin cốt lõi.
4. Trả về DUY NHẤT một mảng JSON (không có markdown giải thích nào khác) theo format:
[
  {{"index": 1, "vi": "câu dịch súc tích"}},
  ...
]

Danh sách câu thoại cần dịch:
{json.dumps([{"index": it["index"], "zh": it["text"], "duration_seconds": round(float(it.get("duration", 2.0)), 2)} for it in items], ensure_ascii=False, indent=2)}
"""

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2
            }
        }

        attempts = 0
        total_attempts = max(len(self.slots) * 2, max_retries)

        while attempts < total_attempts:
            attempts += 1
            key = self.get_next_key()
            if not key:
                break

            headers = {
                "Content-Type": "application/json",
                "X-goog-api-key": key,
            }

            for model_name in PRIMARY_MODELS:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
                try:
                    resp = requests.post(url, headers=headers, json=payload, timeout=20)
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                            # Trích xuất JSON nếu model bọc trong ```json
                            match = re.search(r"\[\s*\{.*\}\s*\]", raw_text, re.DOTALL)
                            if match:
                                raw_text = match.group(0)
                            parsed = json.loads(raw_text)
                            if isinstance(parsed, list):
                                return {it["index"]: it["vi"] for it in parsed if "index" in it and "vi" in it}
                            elif isinstance(parsed, dict) and "translations" in parsed:
                                return {it["index"]: it["vi"] for it in parsed["translations"]}
                    elif resp.status_code in (429, 503):
                        continue
                    else:
                        logger.error(f"Lỗi gọi Gemini {model_name} ({resp.status_code}): {resp.text[:200]}")
                except Exception as e:
                    logger.debug(f"Exception khi gọi Gemini {model_name}: {e}")

            # Nếu tất cả models trong 1 key đều 429/503
            self.mark_rate_limited(key)

        return {}


_SHARED_ROTATOR: GeminiRotator | None = None


def get_shared_rotator(keys_file: Path | str | None = None) -> GeminiRotator:
    global _SHARED_ROTATOR
    if _SHARED_ROTATOR is None:
        _SHARED_ROTATOR = GeminiRotator(keys_file=keys_file)
    return _SHARED_ROTATOR

