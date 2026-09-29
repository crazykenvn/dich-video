"""Module Phòng Thử Nghiệm Kỹ Thuật Lách Bản Quyền (A/B Testing Lab).

Cho phép chọn 1 video và tick chọn nhiều phương pháp xử lý hình ảnh/nhiễu/rỗ khác nhau,
bao gồm cả các công thức phối hợp hoàng kim (Combos) và bộ phối hợp tự do (Custom Mix),
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
    # =========================================================================
    # NHÓM 1: CÁC CÔNG THỨC PHỐI HỢP HOÀNG KIM (GOLDEN COMBOS)
    # =========================================================================
    "combo_stealth": {
        "id": "combo_stealth",
        "name": "💎 Combo 1: Tàng Hình Tinh Tế (Mỹ phẩm, Gái xinh, Dance)",
        "tag": "COMBO TÀNG HÌNH",
        "category": "Công thức phối hợp",
        "description": "Micro-Crop 1.5% + Lanczos + Lưới Mesh 3x3 siêu mờ (7%) + Film Grain mịn (Luma 6) + Tăng 4% bão hòa màu. Da mặt vẫn mịn đẹp nhưng ma trận băm pHash/DCT bị bẻ gãy.",
        "recommended": True,
        "filter": "crop=w=trunc(in_w*0.985/2)*2:h=trunc(in_h*0.985/2)*2,scale=w=trunc(iw/0.985/2)*2:h=trunc(ih/0.985/2)*2:flags=lanczos,setsar=1,drawgrid=w=3:h=3:t=1:c=black@0.07,eq=contrast=1.03:saturation=1.04,noise=c0s=6:c0f=t+u:c1s=3:c1f=t,format=yuv420p",
    },
    "combo_cinema": {
        "id": "combo_cinema",
        "name": "🎬 Combo 2: Điện Ảnh Cổ Điển (Review phim, Podcast, Đời sống)",
        "tag": "COMBO ĐIỆN ẢNH",
        "category": "Công thức phối hợp",
        "description": "Quầng tối Vignette 4 góc + Tông màu ấm điện ảnh + Hạt Film Grain 35mm rõ (Luma 12) + Gai nét viền Unsharp. Biến video thành phong cách máy quay phim nhựa kinh điển.",
        "recommended": True,
        "filter": "setsar=1,vignette=PI/5,eq=contrast=1.04:brightness=0.01:saturation=1.03,unsharp=lx=3:ly=3:la=1.2,noise=c0s=12:c0f=t+u:c1s=5:c1f=t,format=yuv420p",
    },
    "combo_retro_crt": {
        "id": "combo_retro_crt",
        "name": "📺 Combo 3: Màn Hình TV CRT (Hài hước, Tin tức, Tech)",
        "tag": "COMBO RETRO CRT",
        "category": "Công thức phối hợp",
        "description": "Lưới sọc ngang CRT 3px (mờ 14%) + Lệch quang sai màu RGB 2px + Hạt nhiễu Luma 9. Phong cách tivi cổ cắt vụn liên kết dòng quét dọc của AI.",
        "recommended": True,
        "filter": "setsar=1,drawgrid=w=iw:h=3:t=1:c=black@0.14,format=rgba,rgbashift=rh=2:bv=-2,format=yuv420p,noise=c0s=9:c0f=t+u:c1s=4:c1f=t",
    },
    "combo_fortress": {
        "id": "combo_fortress",
        "name": "🏰 Combo 4: Pháo Đài Bất Khả Xâm Phạm (Bản quyền gắt, VTV, Show lớn)",
        "tag": "COMBO CỰC HẠN",
        "category": "Công thức phối hợp",
        "description": "Đòn đánh toàn diện: Crop 1.5% + Lanczos + Mesh Grid 3x3 + Lệch RGB 1px + Tương phản + Film Grain 9 + Unsharp + Tăng tốc vi mô 1.025x (kèm audio pitch/eq). Phá vỡ toàn bộ nhịp khung hình và mã băm.",
        "recommended": True,
        "filter_complex": "[0:v]crop=w=trunc(in_w*0.985/2)*2:h=trunc(in_h*0.985/2)*2,scale=w=trunc(iw/0.985/2)*2:h=trunc(ih/0.985/2)*2:flags=lanczos,setsar=1,drawgrid=w=3:h=3:t=1:c=black@0.10,format=rgba,rgbashift=rh=1:bv=-1,format=yuv420p,eq=contrast=1.03:brightness=0.01:saturation=1.04,unsharp=lx=3:ly=3:la=1.1,noise=c0s=9:c0f=t+u:c1s=4:c1f=t,setpts=PTS/1.025[v_out];[0:a]asetrate=44100*1.025,atempo=1/1.025,aresample=44100,equalizer=f=1000:t=q:w=1.5:g=-2.5,equalizer=f=3200:t=q:w=1.2:g=2.0,atempo=1.025[a_out]",
    },

    # =========================================================================
    # NHÓM 2: CÁC KỸ THUẬT ĐƠN LẺ (ĐỂ NGHIÊN CỨU & SO SÁNH ĐỐI CHỨNG)
    # =========================================================================
    "control": {
        "id": "control",
        "name": "0. Bản Gốc Đối Chứng (Control Baseline)",
        "tag": "GỐC",
        "category": "Kỹ thuật đơn lẻ",
        "description": "Giữ nguyên 100% hình ảnh gốc, chỉ mã hóa lại chuẩn CRF 18 để làm mốc so sánh (Baseline).",
        "recommended": False,
        "filter": "setsar=1,format=yuv420p",
    },
    "grain_subtle": {
        "id": "grain_subtle",
        "name": "1. Hạt Film Grain Siêu Mịn (Subtle Noise)",
        "tag": "HẠT NHIỄU",
        "category": "Kỹ thuật đơn lẻ",
        "description": "Phủ lớp hạt film mịn (Luma 7, Chroma 3) biến thiên theo thời gian thực. Mắt thường hầu như không nhận ra nhưng làm lệch ma trận băm DCT.",
        "recommended": False,
        "filter": "setsar=1,noise=c0s=7:c0f=t+u:c1s=3:c1f=t,format=yuv420p",
    },
    "grain_cinema": {
        "id": "grain_cinema",
        "name": "2. Hạt Film Grain Điện Ảnh 35mm (Cinema Grain)",
        "tag": "HẠT NHIỄU",
        "category": "Kỹ thuật đơn lẻ",
        "description": "Phủ lớp hạt máy quay phim nhựa rõ nét (Luma 14) + tăng nhẹ 4% tương phản. Phong cách điện ảnh cổ điển, phá mạnh pHash của bot.",
        "recommended": False,
        "filter": "setsar=1,eq=contrast=1.04:saturation=1.03,noise=c0s=14:c0f=t+u:c1s=7:c1f=t,format=yuv420p",
    },
    "softlight_noise": {
        "id": "softlight_noise",
        "name": "3. Phủ Lớp Nhiễu Hòa Trộn Softlight (Cinema Blend)",
        "tag": "HẠT NHIỄU",
        "category": "Kỹ thuật đơn lẻ",
        "description": "Sinh lớp nhiễu ảo độc lập rồi hòa trộn Softlight 35% lên video. Giữ nguyên độ sắc nét chi tiết khuôn mặt mà bề mặt vẫn có độ nhám động.",
        "recommended": False,
        "filter_complex": "[0:v]setsar=1,split[base][src];[src]noise=c0s=45:c0f=t+u[noise_layer];[base][noise_layer]blend=all_mode=softlight:all_opacity=0.35,format=yuv420p[v_out]",
    },
    "scanlines_crt": {
        "id": "scanlines_crt",
        "name": "4. Lưới Rỗ Sọc Kẻ CRT (Scanlines 3px)",
        "tag": "LƯỚI RỖ",
        "category": "Kỹ thuật đơn lẻ",
        "description": "Vẽ các đường sọc ngang cách nhau 3px mờ 14% giả lập màn hình tivi CRT. Mắt xem lướt thấy tự nhiên nhưng cắt vụn liên kết dòng pixel của bot.",
        "recommended": False,
        "filter": "setsar=1,drawgrid=w=iw:h=3:t=1:c=black@0.14,format=yuv420p",
    },
    "mesh_grid": {
        "id": "mesh_grid",
        "name": "5. Lưới Rỗ Mắt Cáo Ma Trận (Mesh Grid 4x4)",
        "tag": "LƯỚI RỖ",
        "category": "Kỹ thuật đơn lẻ",
        "description": "Tạo lớp ma trận ô vuông chấm rỗ 4x4 pixel phủ đều toàn màn hình mờ 12%. Tạo cảm giác texture vải nhám, cực kỳ khó chịu với bot quét ảnh tĩnh.",
        "recommended": False,
        "filter": "setsar=1,drawgrid=w=4:h=4:t=1:c=black@0.12,format=yuv420p",
    },
    "edge_roughening": {
        "id": "edge_roughening",
        "name": "6. Gai Nét Rỗ Viền Cạnh (Unsharp Masking)",
        "tag": "GAI NÉT",
        "category": "Kỹ thuật đơn lẻ",
        "description": "Tăng độ sắc nhọn biên cạnh cực hạn, làm rỗ các đường viền áo, tóc, khuôn mặt và nền. Làm biến dạng bộ lọc nhận dạng đường cong Laplace.",
        "recommended": False,
        "filter": "setsar=1,unsharp=lx=5:ly=5:la=1.8:cx=3:cy=3:ca=0.8,format=yuv420p",
    },
    "chromatic_shift": {
        "id": "chromatic_shift",
        "name": "7. Lệch Sắc Sai Màu RGB (Chromatic Aberration)",
        "tag": "MÀU SẮC",
        "category": "Kỹ thuật đơn lẻ",
        "description": "Dịch lệch kênh Đỏ sang phải 2px và Xanh dương xuống 2px tạo hiệu ứng tách viền quang sai 3D. Đánh lừa mạng nơ-ron nhận diện biên đối tượng.",
        "recommended": False,
        "filter": "setsar=1,format=rgba,rgbashift=rh=2:bv=-2,format=yuv420p",
    },
    "bayer_dither": {
        "id": "bayer_dither",
        "name": "8. Rỗ Ma Trận Hạt Bayer (Bayer Dithering)",
        "tag": "LƯỚI RỖ",
        "category": "Kỹ thuật đơn lẻ",
        "description": "Lượng tử hóa bảng màu và áp dụng thuật toán ma trận Bayer dither tạo các cụm chấm rỗ retro nghệ thuật độc lạ.",
        "recommended": False,
        "filter_complex": "[0:v]setsar=1,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=3,format=yuv420p[v_out]",
    },
}


def build_custom_mix_filter(
    crop_lanczos: bool = True,
    grid_mode: str = "none",  # "none", "scanlines_3px", "mesh_3x3_subtle", "mesh_4x4_medium"
    rgb_shift: int = 0,       # 0, 1, 2
    grain_mode: str = "none", # "none", "subtle", "cinema", "heavy"
    unsharp: bool = False,
    vignette: bool = False,
    color_eq: bool = False,
    speed_warp: bool = False,
) -> tuple[str, bool]:
    """Tạo chuỗi filter FFmpeg chuẩn theo đúng thứ tự mắt xích tối ưu (Filter Pipeline Order).

    1. Hình học (Geometry): crop -> scale Lanczos
    2. Màu sắc & Quang sai: eq -> rgbashift
    3. Cấu trúc lưới rỗ: drawgrid
    4. Độ sắc viền & Vignette: unsharp -> vignette
    5. Nhiễu động thời gian: noise (allf=t+u)
    6. Biến thiên thời gian: setpts

    Returns:
        tuple (filter_str, has_speed_warp)
    """
    v_filters: list[str] = []

    # 1. Hình học (Geometry)
    if crop_lanczos:
        v_filters.append("crop=w=trunc(in_w*0.985/2)*2:h=trunc(in_h*0.985/2)*2")
        v_filters.append("scale=w=trunc(iw/0.985/2)*2:h=trunc(ih/0.985/2)*2:flags=lanczos")
    v_filters.append("setsar=1")

    # 2. Màu sắc & Quang sai (Color & Chromatic)
    if color_eq:
        v_filters.append("eq=contrast=1.03:brightness=0.01:saturation=1.04")
    if rgb_shift > 0:
        v_filters.append("format=rgba")
        v_filters.append(f"rgbashift=rh={rgb_shift}:bv=-{rgb_shift}")
        v_filters.append("format=yuv420p")

    # 3. Cấu trúc lưới rỗ (Grid / Mesh)
    if grid_mode == "scanlines_3px":
        v_filters.append("drawgrid=w=iw:h=3:t=1:c=black@0.14")
    elif grid_mode == "mesh_3x3_subtle":
        v_filters.append("drawgrid=w=3:h=3:t=1:c=black@0.07")
    elif grid_mode == "mesh_4x4_medium":
        v_filters.append("drawgrid=w=4:h=4:t=1:c=black@0.12")

    # 4. Độ sắc nét & Quầng góc (Sharpness & Vignette)
    if vignette:
        v_filters.append("vignette=PI/5")
    if unsharp:
        v_filters.append("unsharp=lx=3:ly=3:la=1.2:cx=3:cy=3:ca=0.6")

    # 5. Lớp phủ nhiễu ngẫu nhiên (Temporal Noise)
    if grain_mode == "subtle":
        v_filters.append("noise=c0s=6:c0f=t+u:c1s=3:c1f=t")
    elif grain_mode == "cinema":
        v_filters.append("noise=c0s=12:c0f=t+u:c1s=5:c1f=t")
    elif grain_mode == "heavy":
        v_filters.append("noise=c0s=18:c0f=t+u:c1s=8:c1f=t")

    # 6. Biến thiên thời gian (Time warping)
    if speed_warp:
        v_filters.append("setpts=PTS/1.025")

    v_filters.append("format=yuv420p")
    return (",".join(v_filters), speed_warp)


def generate_single_variant(
    video_path: Path,
    output_path: Path,
    preset_id: str,
    preview_duration: float | None = 15.0,
    anti_audio: bool = True,
) -> dict[str, Any]:
    """Sinh 1 biến thể video theo preset kỹ thuật được chọn."""
    preset = LAB_PRESETS.get(preset_id)
    if not preset:
        return {"success": False, "error": f"Không tìm thấy preset '{preset_id}'"}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    start_time = time.time()

    cmd = ["ffmpeg", "-y", "-hwaccel", "auto"]

    if preview_duration and preview_duration > 0:
        cmd += ["-t", str(preview_duration)]

    cmd += ["-i", str(video_path)]

    # Xử lý video filter & audio
    if "filter_complex" in preset:
        fc = preset["filter_complex"]
        if "[a_out]" in fc:
            cmd += ["-filter_complex", fc, "-map", "[v_out]", "-map", "[a_out]", "-c:a", "aac", "-b:a", "192k"]
        else:
            cmd += ["-filter_complex", fc, "-map", "[v_out]"]
            if anti_audio:
                audio_filter = get_audio_anti_detect_filter()
                cmd += ["-af", audio_filter, "-c:a", "aac", "-b:a", "192k"]
            else:
                cmd += ["-c:a", "copy"]
    else:
        cmd += ["-vf", preset["filter"]]
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


def generate_custom_variant(
    video_path: Path,
    output_path: Path,
    custom_cfg: dict[str, Any],
    preview_duration: float | None = 15.0,
    anti_audio: bool = True,
) -> dict[str, Any]:
    """Sinh 1 biến thể video tự do phối hợp các kỹ thuật theo cấu hình tùy biến."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    start_time = time.time()

    vf_str, has_speed_warp = build_custom_mix_filter(
        crop_lanczos=custom_cfg.get("crop_lanczos", True),
        grid_mode=custom_cfg.get("grid_mode", "none"),
        rgb_shift=custom_cfg.get("rgb_shift", 0),
        grain_mode=custom_cfg.get("grain_mode", "none"),
        unsharp=custom_cfg.get("unsharp", False),
        vignette=custom_cfg.get("vignette", False),
        color_eq=custom_cfg.get("color_eq", False),
        speed_warp=custom_cfg.get("speed_warp", False),
    )

    cmd = ["ffmpeg", "-y", "-hwaccel", "auto"]
    if preview_duration and preview_duration > 0:
        cmd += ["-t", str(preview_duration)]
    cmd += ["-i", str(video_path)]

    cmd += ["-vf", vf_str]

    # Xử lý âm thanh (nếu có speed warp 1.025x thì audio phải ăn theo atempo=1.025)
    af_parts = []
    if anti_audio:
        af_parts.append(get_audio_anti_detect_filter())
    if has_speed_warp:
        af_parts.append("atempo=1.025")

    if af_parts:
        cmd += ["-af", ",".join(af_parts), "-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-c:a", "copy"]

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
            "preset_id": "custom_mix",
            "preset_name": "🎛️ Bản Phối Tùy Biến (Custom Mix)",
            "tag": "CUSTOM MIX",
            "description": "Bản phối ghép tự do các mắt xích theo công thức tùy chỉnh của bạn.",
            "output_path": output_path,
            "render_time_sec": elapsed,
            "file_size_mb": size_mb,
            "filter_code": vf_str,
        }
    except Exception as e:
        return {
            "success": False,
            "preset_id": "custom_mix",
            "preset_name": "🎛️ Bản Phối Tùy Biến",
            "error": str(e),
        }
