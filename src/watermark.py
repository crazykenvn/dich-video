"""Module hỗ trợ tạo và chèn watermark/logo lách bản quyền video."""

from __future__ import annotations

import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def generate_text_logo(
    text: str,
    output_path: Path,
    font_size: int = 28,
    padding: tuple[int, int] = (22, 10),
) -> Path:
    """Tự động tạo ảnh PNG logo trong suốt đẹp mắt từ một đoạn text (tên kênh, watermark)."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Thử nạp font hệ thống tiếng Việt
    font = None
    candidate_fonts = [
        "C:\\Windows\\Fonts\\arialbd.ttf",  # Arial Bold
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\tahoma.ttf",
        "C:\\Windows\\Fonts\\segoeui.ttf",
    ]
    for fp in candidate_fonts:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except Exception:
                continue

    if font is None:
        font = ImageFont.load_default()

    # Đo kích thước chữ
    dummy_img = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    dummy_draw = ImageDraw.Draw(dummy_img)
    bbox = dummy_draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    pad_x, pad_y = padding
    box_w = text_w + pad_x * 2
    box_h = text_h + pad_y * 2

    # Vẽ nền bo tròn mờ nhẹ với viền tinh tế
    img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Nền mờ kính (glassmorphism/capsule)
    draw.rounded_rectangle(
        [(0, 0), (box_w - 1, box_h - 1)],
        radius=min(box_h // 2, 12),
        fill=(255, 255, 255, 190),
        outline=(200, 200, 200, 220),
        width=2,
    )

    # Vẽ chữ màu đen đậm nổi bật
    text_x = pad_x - bbox[0]
    text_y = pad_y - bbox[1]
    draw.text((text_x, text_y), text, fill=(15, 23, 42, 255), font=font)

    img.save(str(output_path), "PNG")
    return output_path


def get_watermark_motion_expr(motion_type: str = "drift") -> tuple[str, str]:
    """Trả về công thức tọa độ (x_expr, y_expr) cho overlay filter của FFmpeg.

    - drift: Trôi lượn sóng mượt mà khắp màn hình (tối ưu nhất để lách bản quyền)
    - scroll: Chạy ngang từ phải sang trái
    - bounce: Nảy các cạnh màn hình DVD screensaver
    - top_right: Cố định góc trên bên phải
    - bottom_right: Cố định góc dưới bên phải
    """
    if motion_type == "scroll":
        return "W - mod(70*t, W+w)", "H*0.14"
    elif motion_type == "bounce":
        return "abs(mod(55*t, 2*(W-w)) - (W-w))", "abs(mod(38*t, 2*(H-h)) - (H-h))"
    elif motion_type == "top_right":
        return "W-w-35", "35"
    elif motion_type == "bottom_right":
        return "W-w-35", "H-h-45"
    else:
        # Mặc định: Trôi lượn sóng tự nhiên khắp màn hình (Lissajous curve)
        # Chu kỳ 18s theo trục X và 24s theo trục Y giúp logo quét toàn bộ khung hình
        return "(W-w)*(0.5+0.44*sin(2*PI*t/18))", "(H-h)*(0.5+0.44*cos(2*PI*t/24))"
