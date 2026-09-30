"""Thao tác video/audio bằng ffmpeg + ffprobe."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# Tự động tìm nạp và thêm đường dẫn ffmpeg/ffprobe vào PATH nếu máy chưa có
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except Exception:
    pass

for _cand in [
    Path(sys.prefix) / "Scripts",
    Path(sys.prefix) / "bin",
    Path(__file__).resolve().parent.parent / ".venv" / "Scripts",
    Path(__file__).resolve().parent.parent / "bin",
]:
    if _cand.exists() and (
        (_cand / "ffmpeg.exe").exists() or (_cand / "ffmpeg").exists()
    ):
        if str(_cand) not in os.environ.get("PATH", ""):
            os.environ["PATH"] = str(_cand) + os.pathsep + os.environ.get("PATH", "")


class FFmpegError(RuntimeError):
    pass


def _run(cmd: list[str], timeout: int = 3600) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise FFmpegError(
            "Không tìm thấy ffmpeg/ffprobe. Cài đặt: https://ffmpeg.org/download.html"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise FFmpegError(exc.stderr.strip() or str(exc)) from exc


def require_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        # Thử lại kích hoạt static_ffmpeg một lần nữa
        try:
            import static_ffmpeg
            static_ffmpeg.add_paths()
        except Exception:
            pass
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise FFmpegError("Cần ffmpeg và ffprobe trong PATH trước khi chạy pipeline.")


def probe(path: Path) -> dict[str, Any]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(path),
    ]
    result = _run(cmd)
    return json.loads(result.stdout)


def duration_seconds(path: Path) -> float:
    info = probe(path)
    raw = info.get("format", {}).get("duration")
    if raw is None:
        return 0.0
    return float(raw)


def get_video_resolution(video_path: Path) -> tuple[int, int]:
    """Lấy độ phân giải chuẩn (width, height) của video, tính cả góc xoay (rotate)."""
    try:
        info = probe(video_path)
        for s in info.get("streams", []):
            if s.get("codec_type") == "video":
                w = int(s.get("width", 1080))
                h = int(s.get("height", 1920))
                rot = s.get("tags", {}).get("rotate")
                if rot is None:
                    side_data = s.get("side_data_list", [])
                    for sd in side_data:
                        if "rotation" in sd:
                            rot = sd.get("rotation")
                            break
                if rot and int(float(rot)) in (90, 270, -90, -270):
                    w, h = h, w
                return w, h
    except Exception:
        pass
    return (1080, 1920)


def extract_preview_frame(video_path: Path, timestamp_sec: float = 1.0) -> str:
    """Trích xuất 1 khung hình tại giây timestamp_sec và trả về chuỗi data URL base64 JPEG."""
    import base64
    from .config import OUTPUT_DIR

    thumb_dir = OUTPUT_DIR / "thumbnails"
    thumb_dir.mkdir(parents=True, exist_ok=True)
    thumb_file = thumb_dir / f"{video_path.stem}_{int(timestamp_sec * 10)}f.jpg"

    if not thumb_file.exists() or thumb_file.stat().st_size == 0:
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(max(0.1, timestamp_sec)),
            "-i",
            str(video_path),
            "-vframes",
            "1",
            "-q:v",
            "2",
            str(thumb_file),
        ]
        try:
            _run(cmd)
        except Exception:
            cmd[3] = "0.0"
            try:
                _run(cmd)
            except Exception:
                return ""

    if thumb_file.exists() and thumb_file.stat().st_size > 0:
        raw_b64 = base64.b64encode(thumb_file.read_bytes()).decode("ascii")
        return f"data:image/jpeg;base64,{raw_b64}"
    return ""


def extract_audio(video_path: Path, wav_path: Path, sample_rate: int = 16000) -> Path:
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = wav_path.with_suffix(".tmp.wav")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-c:a",
        "pcm_s16le",
        str(tmp),
    ]
    _run(cmd)
    tmp.replace(wav_path)
    return wav_path


def _get_video_encode_args(video_quality: str = "high") -> list[str]:
    """Tùy chọn chất lượng encode:
    - 'high' (Mặc định, khuyên dùng): libx264 CRF 18, preset veryfast, yuv420p.
      Giữ trọn 100% độ sắc nét gốc (visually lossless), loại bỏ hoàn toàn hiện tượng vỡ hạt/mờ chữ.
    - 'medium': libx264 CRF 22, cân bằng dung lượng và tốc độ.
    - 'gpu': Dùng GPU phần cứng qua h264_mf ở bitrate cao 25M - 35M (Quality 95).
    """
    import sys
    if video_quality == "gpu" and sys.platform == "win32":
        return [
            "-c:v", "h264_mf",
            "-rate_control", "3",
            "-quality", "95",
            "-b:v", "25M",
            "-maxrate", "35M",
            "-bufsize", "50M",
        ]
    elif video_quality == "medium":
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p"]
    else:  # default "high" (CRF 18 visually lossless)
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]


def get_visual_anti_detect_filter() -> str:
    """Kỹ thuật 1: Bộ lọc hình ảnh chống quét bản quyền cấu trúc (pHash / DCT):
    - crop in_w*0.985:in_h*0.985: Cắt xén vi mô 1.5% viền ngoài.
    - scale w=trunc(iw/0.985/2)*2:h=trunc(ih/0.985/2)*2: Phóng to lại kích thước gốc bằng Lanczos làm lệch toàn bộ ma trận pixel.
    - setsar=1: Giữ tỷ lệ hiển thị nguyên bản 1:1.
    - eq: Tinh chỉnh nhẹ độ tương phản 1.03, sáng 0.01, bão hòa 1.04.
    - noise: Lớp hạt film grain động mịn 2.5% biến thiên theo thời gian thực (phá vỡ tính tĩnh).
    """
    return (
        "crop=w=trunc(in_w*0.985/2)*2:h=trunc(in_h*0.985/2)*2,"
        "scale=w=trunc(iw/0.985/2)*2:h=trunc(ih/0.985/2)*2:flags=lanczos,"
        "setsar=1,"
        "eq=contrast=1.03:brightness=0.01:saturation=1.04,"
        "noise=c0s=2.5:allf=t"
    )


def get_audio_anti_detect_filter(sample_rate: int = 44100) -> str:
    """Kỹ thuật 4: Bộ lọc âm thanh chống quét dấu vân tay (Acoustic Fingerprint):
    - Pitch Shift +2.5% kết hợp bù tempo 1/1.025 (khớp khẩu hình 100%, không trôi tiếng, nghe tự nhiên).
    - Parametric EQ: Xáo trộn năng lượng dải tần số 1000Hz (-2.5dB) và 3200Hz (+2.0dB) phá vỡ các đỉnh phổ.
    """
    return (
        f"asetrate={sample_rate}*1.025,atempo=1/1.025,aresample={sample_rate},"
        "equalizer=f=1000:t=q:w=1.5:g=-2.5,equalizer=f=3200:t=q:w=1.2:g=2.0"
    )


def get_subtitle_ass_style(
    font_name: str = "Arial",
    font_size: int = 16,
    sub_style: str = "solid_black",
    sub_position: str = "bottom",
    sub_margin_v: int = 30,
    box_padding: int = 5,
    box_opacity: float | int = 100,
) -> str:
    """Tạo chuỗi force_style cho libass.
    - font_size: Cỡ chữ phụ đề (px).
    - box_padding: Độ dày / chiều cao của hộp đè (Outline trong BorderStyle=3).
    - sub_position: 'bottom' (Alignment=2), 'middle' (Alignment=5), 'top' (Alignment=8).
    - sub_margin_v: Khoảng cách pixel từ cạnh đáy/đỉnh.
    - box_opacity: Tỷ lệ che phủ / mờ của hộp đè (% từ 0 đến 100).
    """
    align = 2
    if sub_position == "middle":
        align = 5
    elif sub_position == "top":
        align = 8

    margin_v = max(0, int(sub_margin_v or 30))
    outline = max(1, int(box_padding or 5))

    # Xử lý box_opacity (% từ 0-100 hoặc float 0.0-1.0)
    try:
        op_val = float(box_opacity)
        if op_val > 1.0:
            op = max(0.0, min(1.0, op_val / 100.0))
        else:
            op = max(0.0, min(1.0, op_val))
    except (ValueError, TypeError):
        op = 1.0

    # Tương thích ngược kiểu cũ nếu chọn black_box / white_box mà không truyền opacity riêng
    if box_opacity == 100 or box_opacity == 1.0:
        if sub_style == "black_box":
            op = 0.60
        elif sub_style == "white_box":
            op = 0.60

    # Trong ASS: &HAABBGGRR, AA: 00 = đặc 100%, FF = trong suốt 0%
    alpha_int = int(round((1.0 - op) * 255))
    alpha_hex = f"{alpha_int:02X}"

    # PlayResY=462, PlayResX=260: Khóa tọa độ chuẩn theo tỷ lệ khung Preview Canvas (260x462px)
    # Giúp MarginV, FontSize và Outline khớp 100% với màn hình Studio biên tập, không bị lệch/chạy lên trên
    res_prefix = "PlayResY=462,PlayResX=260,"

    if sub_style == "blur_box":
        # Kính mờ (Frosted Blur Glass): Hộp tối bán trong suốt 65% che kín phụ đề gốc
        blur_alpha = "58"  # ~65% opacity
        blur_bg = f"&H{blur_alpha}251912"  # Màu Slate Navy tối sang trọng (#121925)
        return (
            f"{res_prefix}FontName={font_name},FontSize={font_size},"
            f"PrimaryColour=&H00FFFFFF,OutlineColour={blur_bg},BackColour={blur_bg},"
            f"BorderStyle=3,Outline={outline},Shadow=0,Alignment={align},MarginV={margin_v}"
        )
    elif sub_style in ("solid_black", "black_box"):
        # Nền đen đặc hoặc mờ tùy chỉnh, chữ trắng
        return (
            f"{res_prefix}FontName={font_name},FontSize={font_size},"
            f"PrimaryColour=&H00FFFFFF,OutlineColour=&H{alpha_hex}000000,BackColour=&H{alpha_hex}000000,"
            f"BorderStyle=3,Outline={outline},Shadow=0,Alignment={align},MarginV={margin_v}"
        )
    elif sub_style in ("solid_white", "white_box"):
        # Nền trắng với độ mờ tùy chỉnh, chữ đen
        return (
            f"{res_prefix}FontName={font_name},FontSize={font_size},"
            f"PrimaryColour=&H00000000,OutlineColour=&H{alpha_hex}FFFFFF,BackColour=&H{alpha_hex}FFFFFF,"
            f"BorderStyle=3,Outline={outline},Shadow=0,Alignment={align},MarginV={margin_v}"
        )
    else:  # classic
        return (
            f"{res_prefix}FontName={font_name},FontSize={font_size},"
            f"PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&HFF000000,"
            f"BorderStyle=1,Outline={outline},Shadow=0,Alignment={align},MarginV={margin_v}"
        )


def mux_audio(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    original_mix: float = 0.0,
    srt_path: Path | None = None,
    burn_sub: bool = False,
    font_name: str = "Arial",
    font_size: int = 16,
    sub_style: str = "solid_black",
    sub_position: str = "bottom",
    sub_margin_v: int = 30,
    box_padding: int = 5,
    box_opacity: float | int = 100,
    watermark_enabled: bool = False,
    watermark_path: Path | str | None = None,
    watermark_opacity: float = 0.18,
    watermark_motion: str = "drift",
    watermark_width: int = 180,
    video_quality: str = "high",
    anti_video: bool = False,
    anti_audio: bool = False,
) -> Path:
    """Ghép video gốc với audio mới và tùy chọn phụ đề/watermark/anti-detect.
    - original_mix: giữ ~12% tiếng gốc.
    - burn_sub: in phụ đề cứng lên hình ảnh.
    - font_size: cỡ chữ phụ đề (px).
    - box_padding: độ dày viền hộp đè phụ đề.
    - sub_style: solid_black (hộp đen đặc che kín sub cũ).
    - watermark_enabled: chèn logo lách bản quyền di chuyển liên tục với độ mờ thấp.
    - video_quality: 'high' (CRF 18 visually lossless - 100% gốc), 'medium' (CRF 22), 'gpu' (h264_mf 25M).
    - anti_video: Kỹ thuật 1 - crop 1.5% + scale + film grain + micro EQ.
    - anti_audio: Kỹ thuật 4 - biến điệu âm thanh gốc (pitch/tempo/eq) trước khi hòa âm.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_name(output_path.stem + ".tmp" + output_path.suffix)
    mix = max(0.0, min(1.0, float(original_mix or 0.0)))

    cmd = ["ffmpeg", "-y", "-hwaccel", "auto", "-i", str(video_path), "-i", str(audio_path)]

    has_wm = bool(watermark_enabled and watermark_path and Path(watermark_path).exists())
    if has_wm:
        cmd += ["-loop", "1", "-i", str(Path(watermark_path).resolve())]

    filter_complex_parts: list[str] = []
    cur_v = "0:v"
    need_video_encode = False

    # 1. Bộ lọc hình ảnh chống quét bản quyền (Kỹ thuật 1)
    if anti_video:
        filter_complex_parts.append(f"[{cur_v}]{get_visual_anti_detect_filter()}[v_anti]")
        cur_v = "v_anti"
        need_video_encode = True

    # 2. Chèn Watermark Logo nếu kích hoạt
    if has_wm:
        from .watermark import get_watermark_motion_expr

        x_expr, y_expr = get_watermark_motion_expr(watermark_motion)
        op = max(0.03, min(1.0, float(watermark_opacity or 0.18)))
        wm_w = max(50, min(800, int(watermark_width or 180)))
        filter_complex_parts.append(
            f"[2:v]format=rgba,colorchannelmixer=aa={op:.2f},scale={wm_w}:-1[wm_ready]"
        )
        filter_complex_parts.append(
            f"[{cur_v}][wm_ready]overlay=x='{x_expr}':y='{y_expr}':shortest=1[v_wm]"
        )
        cur_v = "v_wm"
        need_video_encode = True

    # 3. In phụ đề cứng nếu kích hoạt
    if burn_sub and srt_path is not None:
        srt_escaped = (
            str(srt_path.resolve())
            .replace("\\", "/")
            .replace(":", "\\:")
            .replace("'", r"\'")
        )
        style = get_subtitle_ass_style(
            font_name=font_name,
            font_size=font_size,
            sub_style=sub_style,
            sub_position=sub_position,
            sub_margin_v=sub_margin_v,
            box_padding=box_padding,
            box_opacity=box_opacity,
        )
        filter_complex_parts.append(
            f"[{cur_v}]subtitles='{srt_escaped}':force_style='{style}'[v_sub]"
        )
        cur_v = "v_sub"
        need_video_encode = True

    # 4. Hòa trộn âm thanh (Audio Mixing) có biến điệu tiếng gốc (Kỹ thuật 4)
    if mix > 0:
        if anti_audio:
            filter_complex_parts.append(
                f"[0:a]{get_audio_anti_detect_filter()}[a0_clean];"
                f"[a0_clean]volume={mix}[a0];[1:a]volume=1.0[a1];"
                "[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[a_out]"
            )
        else:
            filter_complex_parts.append(
                f"[0:a]volume={mix}[a0];[1:a]volume=1.0[a1];"
                "[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[a_out]"
            )
        audio_map = "[a_out]"
    else:
        audio_map = "1:a:0"

    # Kết nối filter_complex vào lệnh FFmpeg
    if filter_complex_parts:
        cmd += ["-filter_complex", ";".join(filter_complex_parts)]
        if cur_v.startswith("v_"):
            cmd += ["-map", f"[{cur_v}]"]
        else:
            cmd += ["-map", "0:v:0"]
        cmd += ["-map", audio_map]
    else:
        cmd += ["-map", "0:v:0", "-map", audio_map]

    if need_video_encode:
        cmd += _get_video_encode_args(video_quality=video_quality)
    else:
        cmd += ["-c:v", "copy"]

    cmd += [
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(tmp),
    ]

    try:
        _run(cmd)
    except Exception:
        # Fallback về libx264 CRF 18 nếu GPU encoder gặp vấn đề
        if need_video_encode and "h264_mf" in cmd:
            fallback_cmd = []
            skip = False
            for c in cmd:
                if skip:
                    skip = False
                    continue
                if c == "h264_mf":
                    fallback_cmd.append("libx264")
                elif c in ("-rate_control", "-quality", "-b:v", "-maxrate", "-bufsize"):
                    skip = True
                    continue
                else:
                    fallback_cmd.append(c)
            idx = fallback_cmd.index("libx264")
            fallback_cmd[idx + 1:idx + 1] = ["-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
            _run(fallback_cmd)
        else:
            raise

    tmp.replace(output_path)
    return output_path


def remix_video(
    video_path: Path,
    output_path: Path,
    anti_video: bool = True,
    anti_audio: bool = True,
    watermark_enabled: bool = False,
    watermark_path: Path | str | None = None,
    watermark_opacity: float = 0.18,
    watermark_motion: str = "drift",
    watermark_width: int = 180,
    video_quality: str = "high",
    srt_path: Path | None = None,
    burn_sub: bool = False,
    font_name: str = "Arial",
    font_size: int = 16,
    sub_style: str = "solid_black",
    sub_position: str = "bottom",
    sub_margin_v: int = 30,
    box_padding: int = 5,
    box_opacity: float | int = 100,
) -> Path:
    """Xử lý video nhanh không cần dịch:
    - Biến điệu âm thanh gốc (giữ tiếng gốc nhưng phá vỡ Acoustic Fingerprint).
    - Xử lý hình ảnh chống quét (Micro-Crop 1.5%, Film grain, Micro-EQ).
    - Chèn Watermark/Logo mờ chuyển động.
    - Tùy chọn in phụ đề nếu có file srt.
    - Mã hóa chất lượng cao (mặc định CRF 18).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_name(output_path.stem + ".tmp" + output_path.suffix)

    cmd = ["ffmpeg", "-y", "-hwaccel", "auto", "-i", str(video_path)]

    has_wm = bool(watermark_enabled and watermark_path and Path(watermark_path).exists())
    if has_wm:
        cmd += ["-loop", "1", "-i", str(Path(watermark_path).resolve())]

    filter_complex_parts: list[str] = []
    cur_v = "0:v"
    need_video_encode = False

    # 1. Bộ lọc hình ảnh chống quét bản quyền
    if anti_video:
        filter_complex_parts.append(f"[{cur_v}]{get_visual_anti_detect_filter()}[v_anti]")
        cur_v = "v_anti"
        need_video_encode = True

    # 2. Chèn Logo chuyển động
    if has_wm:
        from .watermark import get_watermark_motion_expr

        x_expr, y_expr = get_watermark_motion_expr(watermark_motion)
        op = max(0.03, min(1.0, float(watermark_opacity or 0.18)))
        wm_w = max(50, min(800, int(watermark_width or 180)))
        filter_complex_parts.append(
            f"[1:v]format=rgba,colorchannelmixer=aa={op:.2f},scale={wm_w}:-1[wm_ready]"
        )
        filter_complex_parts.append(
            f"[{cur_v}][wm_ready]overlay=x='{x_expr}':y='{y_expr}':shortest=1[v_wm]"
        )
        cur_v = "v_wm"
        need_video_encode = True

    # 3. Chèn phụ đề nếu có
    if burn_sub and srt_path is not None and Path(srt_path).exists():
        srt_escaped = (
            str(Path(srt_path).resolve())
            .replace("\\", "/")
            .replace(":", "\\:")
            .replace("'", r"\'")
        )
        style = get_subtitle_ass_style(
            font_name=font_name,
            font_size=font_size,
            sub_style=sub_style,
            sub_position=sub_position,
            sub_margin_v=sub_margin_v,
            box_padding=box_padding,
            box_opacity=box_opacity,
        )
        filter_complex_parts.append(f"[{cur_v}]subtitles='{srt_escaped}':force_style='{style}'[v_sub]")
        cur_v = "v_sub"
        need_video_encode = True

    # 4. Biến điệu âm thanh gốc
    audio_map = "0:a:0"
    if anti_audio:
        filter_complex_parts.append(f"[0:a]{get_audio_anti_detect_filter()}[a_anti]")
        audio_map = "[a_anti]"

    if filter_complex_parts:
        cmd += ["-filter_complex", ";".join(filter_complex_parts)]
        if cur_v.startswith("v_"):
            cmd += ["-map", f"[{cur_v}]"]
        else:
            cmd += ["-map", "0:v:0"]
        cmd += ["-map", audio_map]
    else:
        cmd += ["-map", "0:v:0", "-map", "0:a:0"]

    if need_video_encode:
        cmd += _get_video_encode_args(video_quality=video_quality)
    else:
        cmd += ["-c:v", "copy"]

    if anti_audio:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-c:a", "copy"]

    cmd += ["-movflags", "+faststart", str(tmp)]

    try:
        _run(cmd)
    except Exception:
        if need_video_encode and "h264_mf" in cmd:
            fallback_cmd = []
            skip = False
            for c in cmd:
                if skip:
                    skip = False
                    continue
                if c == "h264_mf":
                    fallback_cmd.append("libx264")
                elif c in ("-rate_control", "-quality", "-b:v", "-maxrate", "-bufsize"):
                    skip = True
                    continue
                else:
                    fallback_cmd.append(c)
            idx = fallback_cmd.index("libx264")
            fallback_cmd[idx + 1:idx + 1] = ["-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
            _run(fallback_cmd)
        else:
            raise

    tmp.replace(output_path)
    return output_path



def burn_subtitles(
    video_path: Path,
    srt_path: Path,
    output_path: Path,
    font_name: str = "Arial",
    font_size: int = 11,
    sub_style: str = "solid_black",
    sub_position: str = "bottom",
    sub_margin_v: int = 30,
    box_padding: int = 5,
    box_opacity: float | int = 100,
    video_quality: str = "high",
    anti_video: bool = False,
    anti_audio: bool = False,
    watermark_enabled: bool = False,
    watermark_path: Path | str | None = None,
    watermark_opacity: float = 0.18,
    watermark_motion: str = "drift",
    watermark_width: int = 180,
    **kwargs: Any,
) -> Path:
    return remix_video(
        video_path=video_path,
        output_path=output_path,
        anti_video=anti_video,
        anti_audio=anti_audio,
        watermark_enabled=watermark_enabled,
        watermark_path=watermark_path,
        watermark_opacity=watermark_opacity,
        watermark_motion=watermark_motion,
        watermark_width=watermark_width,
        video_quality=video_quality,
        srt_path=srt_path,
        burn_sub=True,
        font_name=font_name,
        font_size=font_size,
        sub_style=sub_style,
        sub_position=sub_position,
        sub_margin_v=sub_margin_v,
        box_padding=box_padding,
        box_opacity=box_opacity,
    )




def soft_subs(video_path: Path, srt_path: Path, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_name(output_path.stem + ".tmp" + output_path.suffix)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(srt_path),
        "-c",
        "copy",
        "-c:s",
        "mov_text",
        "-metadata:s:s:0",
        "language=vie",
        "-movflags",
        "+faststart",
        str(tmp),
    ]
    _run(cmd)
    tmp.replace(output_path)
    return output_path


def change_tempo(audio_path: Path, output_path: Path, tempo: float) -> Path:
    if abs(tempo - 1.0) < 0.02:
        if audio_path.resolve() != output_path.resolve():
            shutil.copy2(audio_path, output_path)
        return output_path

    filters: list[str] = []
    remaining = tempo
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.4f}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(".tmp" + output_path.suffix)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(audio_path),
        "-filter:a",
        ",".join(filters),
        str(tmp),
    ]
    _run(cmd)
    tmp.replace(output_path)
    return output_path
