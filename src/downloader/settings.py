"""Quản lý Cài Đặt Hệ Thống & Bộ Hồ Sơ Thương Hiệu (Settings & Branding)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import OUTPUT_DIR

SETTINGS_FILE = OUTPUT_DIR / "settings.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    # 1. Thương hiệu & Logo
    "watermark_enabled": True,
    "watermark_text": "KEN VIDEO",
    "watermark_path": None,
    "watermark_opacity": 0.18,
    "watermark_motion": "drift",
    # 2. Bộ lọc lách bản quyền
    "anti_video": True,
    "anti_audio": True,
    # 3. Ngôn ngữ & Dịch thuật
    "source_lang": "zh-CN",
    "target_lang": "vi",
    "bilingual": False,
    # 4. Giọng đọc AI & Khớp nhịp
    "voice": "vi-VN-HoaiMyNeural",
    "fit_timing": True,
    "resolve_overlap": True,
    "max_overlap_tempo": 1.85,
    # 5. Phụ đề & Đè phụ đề gốc
    "burn_sub": True,
    "font_size": 16,
    "box_padding": 5,
    "sub_style": "solid_black",
    "sub_position": "bottom",
    "sub_margin_v": 30,
    "video_quality": "high",
    # 6. Phần cứng
    "model_size": "medium",
    "device": "cuda",
}


def load_settings() -> dict[str, Any]:
    """Tải cấu hình từ file settings.json hoặc trả về mặc định."""
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            settings = DEFAULT_SETTINGS.copy()
            settings.update(data)
            return settings
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict[str, Any]) -> None:
    """Lưu cấu hình vào file settings.json."""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
