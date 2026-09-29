"""Module Phòng Thử Nghiệm Kỹ Thuật Lách Bản Quyền (A/B Testing Lab).

Cho phép chọn 1 video và tick chọn nhiều phương pháp xử lý hình ảnh/nhiễu/rỗ khác nhau,
sau đó sinh hàng loạt các biến thể để người dùng kiểm tra hiệu ứng thị giác và test quét bot.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from ..config import OUTPUT_DIR
from ..media import _run, get_audio_anti_detect_filter, probe

LAB_OUTPUT_DIR = OUTPUT_DIR / "lab_variants"
LAB_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


LAB_PRESETS: dict[str, dict[str, Any]] = {
    "control": {
        "id": "control",
        "name": "0. Bản Gốc Đối Chứng (Control)",
        "tag": "GỐC",
        "category": "Đối chứng",
        "description": "Giữ nguyên 100% hình ảnh gốc, chỉ mã hóa lại chuẩn CRF 18 để làm mốc so sánh (Baseline).",
        "recommended": False,
        "filter": "setsar=1,format=yuv420p",
    },
    "grain_subtle": {
        "id": "grain_subtle",
        "name": "1. Hạt Film Grain Siêu Mịn (Subtle Noise)",
        "tag": "HẠT NHIỄU",
        "category": "Nhiễu hạt",
        "description": "Phủ lớp hạt film mịn (Luma 7, Chroma 3) biến thiên theo thời gian thực. Mắt thường hầu như không nhận ra nhưng làm lệch ma trận băm DCT.",
        "recommended": True,
        "filter": "setsar=1,noise=c0s=7:c0f=t+u:c1s=3:c1f=t,format=yuv420p",
    },
    "grain_cinema": {
        "id": "grain_cinema",
        "name": "2. Hạt Film Grain Điện Ảnh 35mm (Cinema Grain)",
        "tag": "HẠT NHIỄU",
        "category": "Nhiễu hạt",
        "description": "Phủ lớp hạt máy quay phim nhựa rõ nét (Luma 14) + tăng nhẹ 4% tương phản. Phong cách điện ảnh cổ điển, phá mạnh pHash của bot.",
        "recommended": True,
        "filter": "setsar=1,eq=contrast=1.04:saturation=1.03,noise=c0s=14:c0f=t+u:c1s=7:c1f=t,format=yuv420p",
    },
    "softlight_noise": {
        "id": "softlight_noise",
        "name": "3. Phủ Lớp Nhiễu Hòa Trộn Softlight (Cinema Blend)",
        "tag": "HẠT NHIỄU",
        "category": "Nhiễu hạt",
        "description": "Sinh lớp nhiễu ảo độc lập rồi hòa trộn Softlight 35% lên video. Giữ nguyên độ sắc nét chi tiết khuôn mặt mà bề mặt vẫn có độ nhám động.",
        "recommended": False,
        "filter_complex": "[0:v]setsar=1,split[base][src];[src]noise=c0s=45:c0f=t+u[noise_layer];[base][noise_layer]blend=all_mode=softlight:all_opacity=0.35,format=yuv420p[v_out]",
    },
    "scanlines_crt": {
        "id": "scanlines_crt",
        "name": "4. Lưới Rỗ Sọc Kẻ CRT (Scanlines 3px)",
        "tag": "LƯỚI RỖ",
        "category": "Lưới rỗ",
        "description": "Vẽ các đường sọc ngang cách nhau 3px mờ 14% giả lập màn hình tivi CRT. Mắt xem lướt thấy tự nhiên nhưng cắt vụn liên kết dòng pixel của bot.",
        "recommended": True,
        "filter": "setsar=1,drawgrid=w=iw:h=3:t=1:c=black@0.14,format=yuv420p",
    },
    "mesh_grid": {
        "id": "mesh_grid",
        "name": "5. Lưới Rỗ Mắt Cáo Ma Trận (Mesh Grid 4x4)",
        "tag": "LƯỚI RỖ",
        "category": "Lưới rỗ",
        "description": "Tạo lớp ma trận ô vuông chấm rỗ 4x4 pixel phủ đều toàn màn hình mờ 12%. Tạo cảm giác texture vải nhám, cực kỳ khó chịu với bot quét ảnh tĩnh.",
        "recommended": True,
        "filter": "setsar=1,drawgrid=w=4:h=4:t=1:c=black@0.12,format=yuv420p",
    },
    "edge_roughening": {
        "id": "edge_roughening",
        "name": "6. Gai Nét Rỗ Viền Cạnh (Unsharp Masking)",
        "tag": "GAI NÉT",
        "category": "Biên viền",
        "description": "Tăng độ sắc nhọn biên cạnh cực hạn, làm rỗ các đường viền áo, tóc, khuôn mặt và nền. Làm biến dạng bộ lọc nhận dạng đường cong Laplace.",
        "recommended": False,
        "filter": "setsar=1,unsharp=lx=5:ly=5:la=1.8:cx=3:cy=3:ca=0.8,format=yuv420p",
    },
    "chromatic_shift": {
        "id": "chromatic_shift",
        "name": "7. Lệch Sắc Sai Màu RGB (Chromatic Aberration)",
        "tag": "MÀU SẮC",
        "category": "Màu sắc",
        "description": "Dịch lệch kênh Đỏ sang phải 2px và Xanh dương xuống 2px tạo hiệu ứng tách viền quang sai 3D. Đánh lừa mạng nơ-ron nhận diện biên đối tượng.",
        "recommended": True,
        "filter": "setsar=1,format=rgba,rgbashift=rh=2:bv=-2,format=yuv420p",
    },
    "bayer_dither": {
        "id": "bayer_dither",
        "name": "8. Rỗ Ma Trận Hạt Bayer (Bayer Dithering)",
        "tag": "LƯỚI RỖ",
        "category": "Lưới rỗ",
        "description": "Lượng tử hóa bảng màu và áp dụng thuật toán ma trận Bayer dither tạo các cụm chấm rỗ retro nghệ thuật độc lạ.",
        "recommended": False,
        "filter_complex": "[0:v]setsar=1,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=3,format=yuv420p[v_out]",
    },
    "super_combo": {
        "id": "super_combo",
        "name": "9. Combo Siêu Lách Toàn Diện (All-in-One Extreme)",
        "tag": "COMBO SIÊU CẤP",
        "category": "Tổ hợp",
        "description": "Tổ hợp công nghệ tối tân: Cắt vi mô 1.5% + Phóng to Lanczos + Lưới rỗ 3x3 + Lệch màu RGB 1px + Tương phản nhẹ + Noise Grain 9.",
        "recommended": True,
        "filter_complex": "[0:v]crop=w=trunc(in_w*0.985/2)*2:h=trunc(in_h*0.985/2)*2,scale=w=trunc(iw/0.985/2)*2:h=trunc(ih/0.985/2)*2:flags=lanczos,setsar=1,drawgrid=w=3:h=3:t=1:c=black@0.10,format=rgba,rgbashift=rh=1:bv=-1,format=yuv420p,eq=contrast=1.03:brightness=0.01:saturation=1.04,noise=c0s=9:c0f=t+u:c1s=4:c1f=t[v_out]",
    },
}


def generate_single_variant(
    video_path: Path,
    output_path: Path,
    preset_id: str,
    preview_duration: float | None = 15.0,
    anti_audio: bool = True,
) -> dict[str, Any]:
    """Sinh 1 biến thể video theo preset kỹ thuật được chọn.

    Args:
        video_path: Đường dẫn video nguồn.
        output_path: Đường dẫn file kết quả.
        preset_id: Mã định danh của kỹ thuật (xem LAB_PRESETS).
        preview_duration: Số giây cắt test (None = toàn bộ video).
        anti_audio: Bật/tắt bộ lọc biến điệu âm thanh Acoustic Fingerprint.

    Returns:
        dict chứa kết quả: success, render_time, file_size_mb, output_path, v.v.
    """
    preset = LAB_PRESETS.get(preset_id)
    if not preset:
        return {"success": False, "error": f"Không tìm thấy preset '{preset_id}'"}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    start_time = time.time()

    cmd = ["ffmpeg", "-y", "-hwaccel", "auto"]

    # Cắt preview ngắn nếu được yêu cầu
    if preview_duration and preview_duration > 0:
        cmd += ["-t", str(preview_duration)]

    cmd += ["-i", str(video_path)]

    # Xử lý video filter
    if "filter_complex" in preset:
        cmd += ["-filter_complex", preset["filter_complex"], "-map", "[v_out]"]
    else:
        cmd += ["-vf", preset["filter"]]

    # Xử lý âm thanh
    if anti_audio:
        audio_filter = get_audio_anti_detect_filter()
        cmd += ["-af", audio_filter, "-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-c:a", "copy"]

    # Video encoding CRF 18
    cmd += [
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output_path),
    ]

    try:
        _run(cmd)
        elapsed = round(time.time() - start_time, 2)
        size_mb = round(output_path.stat().st_size / (1024 * 1024), 2)
        return {
            "success": True,
            "preset_id": preset_id,
            "preset_name": preset["name"],
            "tag": preset["tag"],
            "description": preset["description"],
            "output_path": output_path,
            "render_time_sec": elapsed,
            "file_size_mb": size_mb,
            "filter_code": preset.get("filter") or preset.get("filter_complex", ""),
        }
    except Exception as e:
        return {
            "success": False,
            "preset_id": preset_id,
            "preset_name": preset["name"],
            "error": str(e),
        }
