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

_local_appdata = os.environ.get("LOCALAPPDATA", "")
_jellyfin_path = Path(_local_appdata) / "Microsoft/WinGet/Packages/Jellyfin.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"

for _cand in [
    _jellyfin_path,
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


def get_ffmpeg_bin() -> str:
    """Trả về đường dẫn tuyệt đối đến bản build FFmpeg tối ưu cho GPU (ưu tiên Jellyfin FFmpeg tương thích driver NVIDIA)."""
    if _jellyfin_path.exists() and (_jellyfin_path / "ffmpeg.exe").exists():
        return str((_jellyfin_path / "ffmpeg.exe").resolve())
    return "ffmpeg"


def get_ffprobe_bin() -> str:
    if _jellyfin_path.exists() and (_jellyfin_path / "ffprobe.exe").exists():
        return str((_jellyfin_path / "ffprobe.exe").resolve())
    return "ffprobe"


class FFmpegError(RuntimeError):
    pass


_NVENC_AVAILABLE: bool | None = None


def is_nvenc_available() -> bool:
    """Kiểm tra máy có card NVIDIA hỗ trợ NVENC phần cứng qua FFmpeg hay không."""
    global _NVENC_AVAILABLE
    if _NVENC_AVAILABLE is not None:
        return _NVENC_AVAILABLE
    try:
        ffmpeg_bin = get_ffmpeg_bin()
        res = subprocess.run(
            [ffmpeg_bin, "-hide_banner", "-f", "lavfi", "-i", "nullsrc=s=256x256:d=0.1", "-c:v", "h264_nvenc", "-f", "null", "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )
        _NVENC_AVAILABLE = (res.returncode == 0)
    except Exception:
        _NVENC_AVAILABLE = False
    return _NVENC_AVAILABLE


def _run(cmd: list[str], timeout: int = 3600) -> subprocess.CompletedProcess:
    if cmd and cmd[0] == "ffmpeg":
        cmd[0] = get_ffmpeg_bin()
    elif cmd and cmd[0] == "ffprobe":
        cmd[0] = get_ffprobe_bin()
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


def safe_replace(tmp_path: Path, dest_path: Path) -> Path:
    """Thay thế file an toàn trên Windows ngay cả khi file đích đang bị mở trong Player / Trình duyệt."""
    import time
    try:
        if dest_path.exists():
            try:
                dest_path.unlink()
            except Exception:
                pass
        tmp_path.replace(dest_path)
        return dest_path
    except PermissionError:
        alt_path = dest_path.with_name(f"{dest_path.stem}_{int(time.time())}{dest_path.suffix}")
        tmp_path.replace(alt_path)
        return alt_path


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


def _get_video_encode_args(video_quality: str = "gpu") -> list[str]:
    """Tùy chọn chất lượng encode:
    - 'gpu' / 'high' (Mặc định): Tự động ưu tiên card NVIDIA RTX qua NVENC (h264_nvenc) siêu tốc, giải phóng 100% CPU.
    - Fallback 1: Windows Media Foundation GPU (h264_mf).
    - Fallback 2: CPU libx264 (CRF 18) nếu máy không có card đồ họa rời.
    """
    import sys

    # 1. Ưu tiên hàng đầu: NVIDIA NVENC Hardware GPU Encoder
    if is_nvenc_available() and video_quality != "cpu":
        return [
            "-c:v", "h264_nvenc",
            "-preset", "p5",       # Fast / High Quality preset tối ưu cho kiến trúc RTX 30/40
            "-cq", "18",           # Constant Quality 18 visually lossless
            "-b:v", "0",           # VBR dựa trên chất lượng
            "-pix_fmt", "yuv420p",
        ]

    # 2. Ưu tiên thứ hai: Windows Media Foundation GPU
    if sys.platform == "win32" and video_quality != "cpu":
        return [
            "-c:v", "h264_mf",
            "-b:v", "18M",
            "-pix_fmt", "yuv420p",
        ]

    # 3. Fallback về CPU libx264 nếu máy không có GPU
    if video_quality == "medium":
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p"]
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


def to_ass_timestamp(seconds: float) -> str:
    s = max(0.0, float(seconds))
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = s % 60
    return f"{h}:{m:02d}:{sec:05.2f}"


def generate_studio_ass_file(
    srt_path: Path,
    output_ass_path: Path,
    video_width: int,
    video_height: int,
    font_name: str = "Arial",
    font_size: int = 13,
    sub_style: str = "blur_box",
    sub_position: str = "bottom",
    sub_margin_v: int = 38,
    box_width: int = 88,
    box_padding: int = 6,
    box_opacity: float | int = 100,
    ocr_blocks: list[dict[str, Any]] | None = None,
) -> tuple[Path, dict[str, int] | None]:
    """Tạo file phụ đề ASS và tính tọa độ blur box khớp 1:1 với màn hình Studio Preview:
    - PlayResX & PlayResY khóa theo tỉ lệ chuẩn Studio Canvas (260x462 dọc hoặc 520x292 ngang).
    - Hộp đè (Box) được vẽ chính xác theo box_width % và vị trí sub_margin_v.
    - Chữ phụ đề được căn giữa chuẩn xác bên trong hộp đè.
    - Hỗ trợ các khối OCR Text Blocks (chữ Trung trên video được dịch sang tiếng Việt).
    """
    font_map = {
        "font-bevietnam": "Be Vietnam Pro",
        "font-montserrat": "Montserrat",
        "font-oswald": "Oswald",
    }
    resolved_font = font_map.get(font_name, font_name or "Arial")

    is_portrait = video_height > video_width
    play_w = 260 if is_portrait else 520
    play_h = 462 if is_portrait else 292

    scale_x = video_width / float(play_w)
    scale_y = video_height / float(play_h)

    margin_v = max(0, int(sub_margin_v or 38))
    bw_pct = max(30, min(100, int(box_width or 88)))
    pad = max(2, int(box_padding or 6))
    fs = max(8, int(font_size or 13))

    box_w_ass = int(round(play_w * (bw_pct / 100.0)))
    box_x_ass = (play_w - box_w_ass) // 2

    from .subtitles import read_srt
    segments = []
    if srt_path.exists():
        try:
            segments = read_srt(srt_path)
        except Exception as e:
            print(f"[media generate_ass] Lỗi đọc SRT: {e}")

    has_multiline = any("\n" in (s.translated or s.text or "") or len(s.translated or s.text or "") > 32 for s in segments)
    line_factor = 2.2 if has_multiline else 1.5
    box_h_ass = max(32, int(round(fs * line_factor + pad * 2.2)))

    box_y2_ass = play_h - margin_v
    box_y1_ass = box_y2_ass - box_h_ass

    text_margin_v = margin_v + max(2, (box_h_ass - int(fs * (1.8 if has_multiline else 1.0))) // 2)

    blur_info = None
    if sub_style == "blur_box":
        vid_box_x = int(box_x_ass * scale_x)
        vid_box_w = int(box_w_ass * scale_x)
        vid_box_y = int(box_y1_ass * scale_y)
        vid_box_h = int(box_h_ass * scale_y)

        if vid_box_x % 2 != 0: vid_box_x -= 1
        if vid_box_w % 2 != 0: vid_box_w -= 1
        if vid_box_y % 2 != 0: vid_box_y -= 1
        if vid_box_h % 2 != 0: vid_box_h += 1

        blur_info = {
            "x": max(0, min(video_width - 10, vid_box_x)),
            "y": max(0, min(video_height - 10, vid_box_y)),
            "w": min(video_width - vid_box_x, vid_box_w),
            "h": min(video_height - vid_box_y, vid_box_h),
        }

    try:
        op_val = float(box_opacity)
        if op_val > 1.0:
            op = max(0.0, min(1.0, op_val / 100.0))
        else:
            op = max(0.0, min(1.0, op_val))
    except (ValueError, TypeError):
        op = 1.0

    alpha_int = int(round((1.0 - op) * 255))
    alpha_hex = f"{alpha_int:02X}"

    if sub_style == "blur_box":
        box_alpha = "4D" if op >= 0.7 else alpha_hex  # ~70% opacity default
        box_bgr = "251912"  # Slate Navy #121925
        text_color = "&H00FFFFFF"
        text_outline = "&H00000000"
        has_box = True
    elif sub_style in ("solid_black", "black_box"):
        box_alpha = alpha_hex
        box_bgr = "000000"
        text_color = "&H00FFFFFF"
        text_outline = "&H00000000"
        has_box = True
    elif sub_style in ("solid_white", "white_box"):
        box_alpha = alpha_hex
        box_bgr = "FFFFFF"
        text_color = "&H00000000"
        text_outline = "&H00FFFFFF"
        has_box = True
    else:  # classic
        has_box = False
        text_color = "&H00FFFFFF"
        text_outline = "&H00000000"

    ass_lines = [
        "[Script Info]",
        "Title: Studio Subtitles",
        "ScriptType: v4.00+",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        f"PlayResX: {play_w}",
        f"PlayResY: {play_h}",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
    ]

    if has_box:
        box_color = f"&H{box_alpha}{box_bgr}"
        ass_lines.append(
            f"Style: Default,{resolved_font},{fs},{text_color},&H000000FF,{text_outline},&H00000000,-1,0,0,0,100,100,0,0,1,0,0,2,10,10,{text_margin_v},1"
        )
        ass_lines.append(
            f"Style: BoxBg,Arial,10,{box_color},&H000000FF,{box_color},{box_color},0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1"
        )
    else:
        ass_lines.append(
            f"Style: Default,{resolved_font},{fs},{text_color},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,10,10,{margin_v},1"
        )

    # Styles chuyên biệt cho Video OCR Text Overlays
    ass_lines.append(
        f"Style: OCRDefault,{resolved_font},13,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,1.5,0.5,5,0,0,0,1"
    )
    ass_lines.append(
        "Style: OCRBoxBg,Arial,10,&H33251912,&H000000FF,&H33251912,&H33251912,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1"
    )

    ass_lines.append("")
    ass_lines.append("[Events]")
    ass_lines.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")

    # 1. Thêm các câu thoại phụ đề chính (SRT)
    for seg in segments:
        t_start = to_ass_timestamp(seg.start)
        t_end = to_ass_timestamp(seg.end)
        txt = (seg.translated or seg.text or "").strip().replace("\n", "\\N")
        if not txt:
            continue

        if has_box:
            cur_lines = txt.count("\\N") + 1
            if cur_lines > 1:
                cur_h = max(38, int(round(fs * 2.3 + pad * 2.2)))
                cur_y1 = box_y2_ass - cur_h
                cur_tmv = margin_v + max(2, (cur_h - int(fs * 2.0)) // 2)
            else:
                cur_h = box_h_ass
                cur_y1 = box_y1_ass
                cur_tmv = text_margin_v

            box_draw = (
                f"{{\\pos(0,0)\\p1\\1c&H{box_bgr}&\\1a&H{box_alpha}&\\3c&H{box_bgr}&\\3a&H{box_alpha}&\\bord0\\shad0}}"
                f"m {box_x_ass} {cur_y1} l {box_x_ass + box_w_ass} {cur_y1} "
                f"l {box_x_ass + box_w_ass} {box_y2_ass} l {box_x_ass} {box_y2_ass}{{\\p0}}"
            )
            ass_lines.append(f"Dialogue: 0,{t_start},{t_end},BoxBg,,0,0,0,,{box_draw}")
            ass_lines.append(f"Dialogue: 1,{t_start},{t_end},Default,,0,0,{cur_tmv},,{txt}")
        else:
            ass_lines.append(f"Dialogue: 0,{t_start},{t_end},Default,,0,0,{margin_v},,{txt}")

    # 2. Thêm các khối Video OCR Text Blocks (chữ trên hình ảnh video)
    if ocr_blocks:
        for block in ocr_blocks:
            if not block.get("is_enabled", True):
                continue
            txt = (block.get("text_vi") or block.get("text_zh") or "").strip().replace("\n", "\\N")
            if not txt:
                continue

            b_start = max(0.0, float(block.get("start", 0.0)))
            b_end = max(b_start + 0.1, float(block.get("end", 0.0)))
            t_start = to_ass_timestamp(b_start)
            t_end = to_ass_timestamp(b_end)

            box = block.get("box", {})
            bx = int(box.get("x", 0))
            by = int(box.get("y", 0))
            bw = int(box.get("w", 100))
            bh = int(box.get("h", 40))

            ass_x1 = max(0, min(play_w - 2, int(round(bx / scale_x))))
            ass_y1 = max(0, min(play_h - 2, int(round(by / scale_y))))
            ass_x2 = max(ass_x1 + 2, min(play_w, int(round((bx + bw) / scale_x))))
            ass_y2 = max(ass_y1 + 2, min(play_h, int(round((by + bh) / scale_y))))

            ass_cx = (ass_x1 + ass_x2) // 2
            ass_cy = (ass_y1 + ass_y2) // 2
            ass_bw = max(10, ass_x2 - ass_x1)
            ass_bh = max(10, ass_y2 - ass_y1)

            b_style = block.get("style", "blur_box")
            if b_style == "solid_black":
                ocr_box_bgr = "000000"
                ocr_box_alpha = "00"  # Đen đặc che hoàn toàn chữ gốc
                draw_box = True
            elif b_style == "blur_box":
                ocr_box_bgr = "251912"  # Slate Navy mờ
                ocr_box_alpha = "33"    # ~80% opacity
                draw_box = True
            else:
                draw_box = False

            if draw_box:
                box_draw = (
                    f"{{\\pos(0,0)\\p1\\1c&H{ocr_box_bgr}&\\1a&H{ocr_box_alpha}&\\3c&H{ocr_box_bgr}&\\3a&H{ocr_box_alpha}&\\bord0\\shad0}}"
                    f"m {ass_x1} {ass_y1} l {ass_x2} {ass_y1} "
                    f"l {ass_x2} {ass_y2} l {ass_x1} {ass_y2}{{\\p0}}"
                )
                ass_lines.append(f"Dialogue: 0,{t_start},{t_end},OCRBoxBg,,0,0,0,,{box_draw}")

            # Tính toán cỡ chữ vừa vặn trong bounding box
            cur_fs = max(8, min(24, int(round(ass_bh * 0.70))))
            clean_txt = txt.replace("\\N", "")
            est_w = len(clean_txt) * (cur_fs * 0.58)
            if est_w > ass_bw * 1.15 and cur_fs > 8:
                cur_fs = max(8, int(round(cur_fs * (ass_bw * 1.15 / est_w))))

            ass_lines.append(
                f"Dialogue: 2,{t_start},{t_end},OCRDefault,,0,0,0,,{{\\pos({ass_cx},{ass_cy})\\an5\\fs{cur_fs}}}{txt}"
            )

    output_ass_path.parent.mkdir(parents=True, exist_ok=True)
    output_ass_path.write_text("\n".join(ass_lines), encoding="utf-8")
    return output_ass_path, blur_info


def get_subtitle_ass_style(
    font_name: str = "Arial",
    font_size: int = 16,
    sub_style: str = "solid_black",
    sub_position: str = "bottom",
    sub_margin_v: int = 30,
    box_padding: int = 5,
    box_opacity: float | int = 100,
) -> str:
    """Tạo chuỗi force_style cho libass (tương thích ngược)."""
    align = 2
    if sub_position == "middle":
        align = 5
    elif sub_position == "top":
        align = 8

    margin_v = max(0, int(sub_margin_v or 30))
    outline = max(1, int(box_padding or 5))

    try:
        op_val = float(box_opacity)
        if op_val > 1.0:
            op = max(0.0, min(1.0, op_val / 100.0))
        else:
            op = max(0.0, min(1.0, op_val))
    except (ValueError, TypeError):
        op = 1.0

    alpha_int = int(round((1.0 - op) * 255))
    alpha_hex = f"{alpha_int:02X}"

    res_prefix = "PlayResY=462,PlayResX=260,"

    if sub_style == "blur_box":
        blur_alpha = "58"
        blur_bg = f"&H{blur_alpha}251912"
        return (
            f"{res_prefix}FontName={font_name},FontSize={font_size},"
            f"PrimaryColour=&H00FFFFFF,OutlineColour={blur_bg},BackColour={blur_bg},"
            f"BorderStyle=3,Outline={outline},Shadow=0,Alignment={align},MarginV={margin_v}"
        )
    elif sub_style in ("solid_black", "black_box"):
        return (
            f"{res_prefix}FontName={font_name},FontSize={font_size},"
            f"PrimaryColour=&H00FFFFFF,OutlineColour=&H{alpha_hex}000000,BackColour=&H{alpha_hex}000000,"
            f"BorderStyle=3,Outline={outline},Shadow=0,Alignment={align},MarginV={margin_v}"
        )
    elif sub_style in ("solid_white", "white_box"):
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
    box_width: int = 88,
    box_opacity: float | int = 100,
    watermark_enabled: bool = False,
    watermark_path: Path | str | None = None,
    watermark_opacity: float = 0.18,
    watermark_motion: str = "drift",
    watermark_width: int = 180,
    video_quality: str = "high",
    anti_video: bool = False,
    anti_audio: bool = False,
    ocr_blocks: list[dict[str, Any]] | None = None,
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
    - ocr_blocks: danh sách khối chữ cứng trên video cần làm mờ & đè text tiếng Việt.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_name(output_path.stem + ".tmp" + output_path.suffix)
    mix = max(0.0, min(1.0, float(original_mix or 0.0)))

    cmd = [
        "ffmpeg", "-y",
        "-threads", "6",
        "-filter_threads", "4",
        "-hwaccel", "auto",
        "-i", str(video_path),
        "-i", str(audio_path),
    ]

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

    # 3. Dynamic OCR Blur Filter Complex (với các khối OCR style == blur_box)
    if ocr_blocks:
        vw, vh = get_video_resolution(video_path)
        blur_candidates = [
            b for b in ocr_blocks
            if b.get("is_enabled", True) and b.get("style", "blur_box") == "blur_box"
        ]
        for idx, block in enumerate(blur_candidates[:12]):
            box = block.get("box", {})
            bx = int(box.get("x", 0))
            by = int(box.get("y", 0))
            bw = int(box.get("w", 100))
            bh = int(box.get("h", 40))

            bx = max(0, min(vw - 4, bx))
            by = max(0, min(vh - 4, by))
            bw = min(vw - bx, max(4, bw))
            bh = min(vh - by, max(4, bh))

            if bx % 2 != 0: bx -= 1
            if by % 2 != 0: by -= 1
            if bw % 2 != 0: bw += 1
            if bh % 2 != 0: bh += 1

            t_start = max(0.0, float(block.get("start", 0.0)))
            t_end = max(t_start + 0.1, float(block.get("end", 0.0)))

            filter_complex_parts.append(
                f"[{cur_v}]split=2[{cur_v}_base][{cur_v}_crop_{idx}];"
                f"[{cur_v}_crop_{idx}]crop={bw}:{bh}:{bx}:{by},avgblur=18[{cur_v}_blur_{idx}];"
                f"[{cur_v}_base][{cur_v}_blur_{idx}]overlay={bx}:{by}:enable='between(t,{t_start},{t_end})'[{cur_v}_done_{idx}]"
            )
            cur_v = f"{cur_v}_done_{idx}"
            need_video_encode = True

    # 4. In phụ đề cứng & các khối Video OCR khớp chuẩn 1:1 Preview Canvas Studio
    ass_tmp_file: Path | None = None
    has_sub_source = (burn_sub and srt_path is not None and Path(srt_path).exists()) or bool(ocr_blocks)
    if has_sub_source:
        vw, vh = get_video_resolution(video_path)
        ass_tmp_file = output_path.parent / f"{output_path.stem}_render.ass"
        dummy_srt = srt_path if (burn_sub and srt_path is not None and Path(srt_path).exists()) else (output_path.parent / "empty.srt")
        ass_file, blur_info = generate_studio_ass_file(
            srt_path=Path(dummy_srt),
            output_ass_path=ass_tmp_file,
            video_width=vw,
            video_height=vh,
            font_name=font_name,
            font_size=font_size,
            sub_style=sub_style,
            sub_position=sub_position,
            sub_margin_v=sub_margin_v,
            box_width=box_width,
            box_padding=box_padding,
            box_opacity=box_opacity,
            ocr_blocks=ocr_blocks,
        )
        ass_escaped = str(ass_file.resolve()).replace("\\", "/").replace(":", r"\:")

        if blur_info and burn_sub:
            bx, by, bw, bh = blur_info["x"], blur_info["y"], blur_info["w"], blur_info["h"]
            filter_complex_parts.append(
                f"[{cur_v}]split=2[{cur_v}_base][{cur_v}_blur_src];"
                f"[{cur_v}_blur_src]crop={bw}:{bh}:{bx}:{by},avgblur=18[{cur_v}_blurred];"
                f"[{cur_v}_base][{cur_v}_blurred]overlay={bx}:{by}[{cur_v}_blur_done]"
            )
            cur_v = f"{cur_v}_blur_done"

        filter_complex_parts.append(f"[{cur_v}]ass='{ass_escaped}'[v_sub]")
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
        if need_video_encode and any(enc in cmd for enc in ("h264_nvenc", "h264_mf")):
            fallback_cmd = []
            skip = False
            for c in cmd:
                if skip:
                    skip = False
                    continue
                if c in ("h264_nvenc", "h264_mf"):
                    fallback_cmd.append("libx264")
                elif c in ("-rate_control", "-quality", "-b:v", "-maxrate", "-bufsize", "-preset", "-cq"):
                    skip = True
                    continue
                else:
                    fallback_cmd.append(c)
            idx = fallback_cmd.index("libx264")
            fallback_cmd[idx + 1:idx + 1] = ["-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
            _run(fallback_cmd)
        else:
            raise
    finally:
        if ass_tmp_file and ass_tmp_file.exists():
            try:
                ass_tmp_file.unlink(missing_ok=True)
            except Exception:
                pass

    return safe_replace(tmp, output_path)


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
    box_width: int = 88,
    box_opacity: float | int = 100,
    ocr_blocks: list[dict[str, Any]] | None = None,
) -> Path:
    """Xử lý video nhanh không cần dịch:
    - Biến điệu âm thanh gốc (giữ tiếng gốc nhưng phá vỡ Acoustic Fingerprint).
    - Xử lý hình ảnh chống quét (Micro-Crop 1.5%, Film grain, Micro-EQ).
    - Chèn Watermark/Logo mờ chuyển động.
    - Tùy chọn in phụ đề nếu có file srt hoặc ocr_blocks.
    - Mã hóa chất lượng cao (mặc định CRF 18).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_name(output_path.stem + ".tmp" + output_path.suffix)

    cmd = [
        "ffmpeg", "-y",
        "-threads", "6",
        "-filter_threads", "4",
        "-hwaccel", "auto",
        "-i", str(video_path),
    ]

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

    # 3. Dynamic OCR Blur Filter Complex (với các khối OCR style == blur_box)
    if ocr_blocks:
        vw, vh = get_video_resolution(video_path)
        blur_candidates = [
            b for b in ocr_blocks
            if b.get("is_enabled", True) and b.get("style", "blur_box") == "blur_box"
        ]
        for idx, block in enumerate(blur_candidates[:12]):
            box = block.get("box", {})
            bx = int(box.get("x", 0))
            by = int(box.get("y", 0))
            bw = int(box.get("w", 100))
            bh = int(box.get("h", 40))

            bx = max(0, min(vw - 4, bx))
            by = max(0, min(vh - 4, by))
            bw = min(vw - bx, max(4, bw))
            bh = min(vh - by, max(4, bh))

            if bx % 2 != 0: bx -= 1
            if by % 2 != 0: by -= 1
            if bw % 2 != 0: bw += 1
            if bh % 2 != 0: bh += 1

            t_start = max(0.0, float(block.get("start", 0.0)))
            t_end = max(t_start + 0.1, float(block.get("end", 0.0)))

            filter_complex_parts.append(
                f"[{cur_v}]split=2[{cur_v}_base][{cur_v}_crop_{idx}];"
                f"[{cur_v}_crop_{idx}]crop={bw}:{bh}:{bx}:{by},avgblur=18[{cur_v}_blur_{idx}];"
                f"[{cur_v}_base][{cur_v}_blur_{idx}]overlay={bx}:{by}:enable='between(t,{t_start},{t_end})'[{cur_v}_done_{idx}]"
            )
            cur_v = f"{cur_v}_done_{idx}"
            need_video_encode = True

    # 4. Chèn phụ đề & Video OCR nếu có
    ass_tmp_file: Path | None = None
    has_sub_source = (burn_sub and srt_path is not None and Path(srt_path).exists()) or bool(ocr_blocks)
    if has_sub_source:
        vw, vh = get_video_resolution(video_path)
        ass_tmp_file = output_path.parent / f"{output_path.stem}_render.ass"
        dummy_srt = srt_path if (burn_sub and srt_path is not None and Path(srt_path).exists()) else (output_path.parent / "empty.srt")
        ass_file, blur_info = generate_studio_ass_file(
            srt_path=Path(dummy_srt),
            output_ass_path=ass_tmp_file,
            video_width=vw,
            video_height=vh,
            font_name=font_name,
            font_size=font_size,
            sub_style=sub_style,
            sub_position=sub_position,
            sub_margin_v=sub_margin_v,
            box_width=box_width,
            box_padding=box_padding,
            box_opacity=box_opacity,
            ocr_blocks=ocr_blocks,
        )
        ass_escaped = str(ass_file.resolve()).replace("\\", "/").replace(":", r"\:")

        if blur_info and burn_sub:
            bx, by, bw, bh = blur_info["x"], blur_info["y"], blur_info["w"], blur_info["h"]
            filter_complex_parts.append(
                f"[{cur_v}]split=2[{cur_v}_base][{cur_v}_blur_src];"
                f"[{cur_v}_blur_src]crop={bw}:{bh}:{bx}:{by},avgblur=18[{cur_v}_blurred];"
                f"[{cur_v}_base][{cur_v}_blurred]overlay={bx}:{by}[{cur_v}_blur_done]"
            )
            cur_v = f"{cur_v}_blur_done"

        filter_complex_parts.append(f"[{cur_v}]ass='{ass_escaped}'[v_sub]")
        cur_v = "v_sub"
        need_video_encode = True

    # 5. Biến điệu âm thanh gốc
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
        if need_video_encode and any(enc in cmd for enc in ("h264_nvenc", "h264_mf")):
            fallback_cmd = []
            skip = False
            for c in cmd:
                if skip:
                    skip = False
                    continue
                if c in ("h264_nvenc", "h264_mf"):
                    fallback_cmd.append("libx264")
                elif c in ("-rate_control", "-quality", "-b:v", "-maxrate", "-bufsize", "-preset", "-cq"):
                    skip = True
                    continue
                else:
                    fallback_cmd.append(c)
            idx = fallback_cmd.index("libx264")
            fallback_cmd[idx + 1:idx + 1] = ["-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
            _run(fallback_cmd)
        else:
            raise
    finally:
        if ass_tmp_file and ass_tmp_file.exists():
            try:
                ass_tmp_file.unlink(missing_ok=True)
            except Exception:
                pass

    return safe_replace(tmp, output_path)



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
    box_width: int = 88,
    box_opacity: float | int = 100,
    video_quality: str = "high",
    anti_video: bool = False,
    anti_audio: bool = False,
    watermark_enabled: bool = False,
    watermark_path: Path | str | None = None,
    watermark_opacity: float = 0.18,
    watermark_motion: str = "drift",
    watermark_width: int = 180,
    ocr_blocks: list[dict[str, Any]] | None = None,
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
        box_width=box_width,
        box_opacity=box_opacity,
        ocr_blocks=ocr_blocks,
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
