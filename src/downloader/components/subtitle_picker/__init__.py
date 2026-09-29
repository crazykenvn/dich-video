"""Custom Streamlit Component: Kéo thả vị trí phụ đề trực quan trên khung hình video."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit.components.v1 as components

_COMPONENT_DIR = Path(__file__).resolve().parent

# Khởi tạo custom component từ thư mục frontend chứa index.html
_subtitle_picker_component = components.declare_component(
    "subtitle_drag_picker",
    path=str(_COMPONENT_DIR),
)


def subtitle_drag_picker(
    image_b64: str,
    video_width: int,
    video_height: int,
    default_margin_v: int = 40,
    font_size: int = 16,
    box_padding: int = 5,
    box_width: int = 92,
    sub_style: str = "solid_black",
    sample_text: str = "Đây là phụ đề tiếng Việt mẫu đè lên chữ gốc",
    key: str | None = None,
) -> dict[str, Any] | None:
    """Hiển thị khung hình video với hộp phụ đề có thể kéo thả trực tiếp để lấy toạ độ MarginV, cỡ chữ và kích thước hộp.

    Trả về:
        dict chứa:
          - margin_v (int): Toạ độ MarginV (px) tính theo độ phân giải video gốc.
          - percent_from_bottom (float): Khoảng cách tính bằng % từ đáy.
          - sub_position (str): 'bottom', 'middle', hoặc 'top'.
          - font_size (int): Cỡ chữ phụ đề.
          - box_padding (int): Độ dày viền hộp (px).
          - box_width (int): Độ rộng hộp (% màn hình).
          - video_w, video_h: Kích thước video gốc.
          - preview_w, preview_h: Kích thước khung hình preview hiển thị trên màn hình.
    """
    return _subtitle_picker_component(
        image_b64=image_b64,
        video_width=video_width,
        video_height=video_height,
        default_margin_v=default_margin_v,
        font_size=font_size,
        box_padding=box_padding,
        box_width=box_width,
        sub_style=sub_style,
        sample_text=sample_text,
        key=key,
        default=None,
    )
