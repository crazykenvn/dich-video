"""Endpoints phục vụ Studio Biên Tập, Timeline, Preview Frame và A/B Testing Lab."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from ...config import OUTPUT_DIR
from ...downloader.db import get_connection, init_db
from ...downloader.lab import LAB_PRESETS
from ...downloader.settings import load_settings, save_settings
from ...media import (
    burn_subtitles,
    duration_seconds,
    extract_preview_frame,
    get_video_resolution,
    remix_video,
)
from ...subtitles import write_srt
from ...transcribe import Segment
from ..models import RenderConfigRequest

router = APIRouter(prefix="/studio", tags=["Studio & Editor"])


@router.get("/presets")
def get_anti_detect_presets() -> list[dict[str, Any]]:
    """Lấy danh sách 4 Combos hoàng kim lách bản quyền từ Lab."""
    presets = []
    for k, v in LAB_PRESETS.items():
        presets.append({
            "id": v["id"],
            "name": v["name"],
            "tag": v["tag"],
            "description": v["description"],
            "recommended": v.get("recommended", False),
        })
    return presets


@router.get("/video-info")
def get_video_info(video_path: str = Query(..., description="Đường dẫn file video")) -> dict[str, Any]:
    """Lấy thông số kỹ thuật của video: độ dài, kích thước, tỉ lệ."""
    target_p = Path(video_path)
    if not target_p.exists():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy video: {video_path}")

    try:
        dur = duration_seconds(target_p)
        w, h = get_video_resolution(target_p)
        aspect = "9:16" if h > w else "16:9"

        # Format duration mm:ss
        mins = int(dur // 60)
        secs = int(dur % 60)
        dur_str = f"{mins:02d}:{secs:02d}"

        return {
            "video_path": str(target_p),
            "filename": target_p.name,
            "duration_sec": dur,
            "duration_str": dur_str,
            "width": w,
            "height": h,
            "aspect_ratio": aspect,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi đọc thông tin video: {e}")


@router.post("/preview-frame")
def preview_frame(
    video_path: str = Query(..., description="Đường dẫn video"),
    timestamp_sec: float = Query(1.0, description="Vị trí trích xuất (giây)"),
) -> dict[str, Any]:
    """Trích xuất 1 frame ảnh tại vị trí kim playhead trả về base64 data URL."""
    target_p = Path(video_path)
    if not target_p.exists():
        raise HTTPException(status_code=404, detail="Video không tồn tại")

    try:
        data_url = extract_preview_frame(target_p, timestamp_sec)
        return {"data_url": data_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi trích xuất frame: {e}")


@router.get("/timeline-frames")
def get_timeline_frames(
    video_path: str = Query(..., description="Đường dẫn file video"),
    count: int = Query(16, ge=4, le=32, description="Số lượng khung hình cần trích xuất")
) -> dict[str, Any]:
    """Trích xuất chuỗi các khung hình liên tiếp phân bổ theo độ dài video phục vụ dải filmstrip timeline."""
    import base64
    import subprocess
    from concurrent.futures import ThreadPoolExecutor
    from ...config import OUTPUT_DIR

    target_p = Path(video_path)
    if not target_p.exists():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy video: {video_path}")

    dur = duration_seconds(target_p)
    if dur <= 0:
        dur = 15.0

    stem_safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in target_p.stem)[:50]
    cache_dir = OUTPUT_DIR / "thumbnails" / f"filmstrip_{stem_safe}_{count}"
    cache_dir.mkdir(parents=True, exist_ok=True)

    timestamps = [
        round((i / max(1, count - 1)) * max(0.5, dur - 0.5) + 0.2, 1)
        for i in range(count)
    ]

    def extract_single_frame(idx_ts: tuple[int, float]) -> dict[str, Any]:
        idx, ts = idx_ts
        thumb_path = cache_dir / f"f_{idx:02d}.jpg"
        if thumb_path.exists() and thumb_path.stat().st_size > 0:
            b64 = base64.b64encode(thumb_path.read_bytes()).decode("ascii")
            return {"index": idx, "timestamp": ts, "data_url": f"data:image/jpeg;base64,{b64}"}

        cmd = [
            "ffmpeg", "-y", "-ss", str(ts), "-i", str(target_p),
            "-vframes", "1", "-vf", "scale=160:-1", "-q:v", "5",
            str(thumb_path)
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=10)
            b64 = base64.b64encode(thumb_path.read_bytes()).decode("ascii")
            return {"index": idx, "timestamp": ts, "data_url": f"data:image/jpeg;base64,{b64}"}
        except Exception:
            return {"index": idx, "timestamp": ts, "data_url": ""}

    with ThreadPoolExecutor(max_workers=6) as executor:
        frames = list(executor.map(extract_single_frame, enumerate(timestamps)))

    return {
        "video_path": str(target_p),
        "count": count,
        "duration_sec": dur,
        "frames": frames,
    }


@router.post("/upload-logo")
async def upload_watermark_logo(file: UploadFile = File(...)) -> dict[str, Any]:
    """Tải lên và lưu vĩnh viễn file ảnh logo thương hiệu (PNG/JPG) dùng cho mọi video."""
    branding_dir = OUTPUT_DIR / "branding"
    branding_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename or "logo.png").suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        ext = ".png"

    dest_path = branding_dir / f"watermark_logo{ext}"

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File ảnh rỗng!")

    dest_path.write_bytes(content)

    # Lưu vĩnh viễn vào settings.json
    settings = load_settings()
    settings["watermark_path"] = str(dest_path.resolve())
    settings["watermark_type"] = "image"
    settings["watermark_enabled"] = True
    save_settings(settings)

    return {
        "success": True,
        "message": "Đã lưu logo thương hiệu thành công!",
        "watermark_path": str(dest_path.resolve()),
        "filename": dest_path.name,
        "url": f"/branding/{dest_path.name}",
    }


@router.get("/logo-info")
def get_watermark_logo_info() -> dict[str, Any]:
    """Lấy thông tin file logo thương hiệu đã lưu."""
    settings = load_settings()
    wm_path_str = settings.get("watermark_path")
    exists = False
    filename = None
    url = None

    if wm_path_str:
        p = Path(wm_path_str)
        if p.exists() and p.is_file():
            exists = True
            filename = p.name
            url = f"/branding/{p.name}"

    return {
        "exists": exists,
        "watermark_path": wm_path_str if exists else None,
        "filename": filename,
        "url": url,
        "watermark_enabled": settings.get("watermark_enabled", True),
        "watermark_text": settings.get("watermark_text", "KEN STUDIO"),
        "watermark_type": settings.get("watermark_type", "image" if exists else "text"),
    }


@router.delete("/logo")
def delete_watermark_logo() -> dict[str, Any]:
    """Gỡ bỏ logo ảnh và quay về dùng chữ text."""
    settings = load_settings()
    settings["watermark_path"] = None
    settings["watermark_type"] = "text"
    save_settings(settings)
    return {"success": True, "message": "Đã gỡ bỏ logo ảnh"}


@router.post("/export")
def export_video(req: RenderConfigRequest) -> dict[str, Any]:
    """Xuất video thành phẩm theo cấu hình Studio và lưu vào thư mục ready_to_upload/."""
    target_p = Path(req.video_path).resolve()
    if not target_p.exists() or not target_p.is_file():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy video: {req.video_path}")

    settings = load_settings()
    out_root_str = settings.get("output_root_dir")
    if out_root_str and Path(out_root_str).exists():
        out_root = Path(out_root_str).resolve()
    else:
        out_root = (OUTPUT_DIR / "ready_to_upload").resolve()

    subfolder_name = req.subfolder or "general_inbox"
    dest_dir = out_root / subfolder_name
    dest_dir.mkdir(parents=True, exist_ok=True)

    stem = target_p.stem
    ext = target_p.suffix or ".mp4"

    # Xử lý text/image watermark logo nếu bật
    actual_wm_path = None
    if req.watermark_enabled:
        # Ưu tiên 1: File ảnh logo đã lưu trong settings.json
        saved_wm_path = settings.get("watermark_path")
        if saved_wm_path and Path(saved_wm_path).exists() and Path(saved_wm_path).is_file():
            actual_wm_path = Path(saved_wm_path)
        elif req.watermark_text and req.watermark_text.strip():
            # Ưu tiên 2: Tạo ảnh logo từ chữ text
            try:
                from ...watermark import generate_text_logo
                wm_dir = OUTPUT_DIR / "temp" / "wm"
                wm_dir.mkdir(parents=True, exist_ok=True)
                logo_file = wm_dir / f"logo_{stem[:20]}.png"
                generate_text_logo(req.watermark_text.strip(), logo_file)
                actual_wm_path = logo_file
            except Exception as e:
                print(f"[studio export] Lỗi tạo watermark text: {e}")

    try:
        if req.mode == "remix":
            out_filename = f"{stem}_{req.anti_combo}_remix{ext}"
            out_path = dest_dir / out_filename

            remix_video(
                video_path=target_p,
                output_path=out_path,
                anti_video=True,
                anti_audio=req.pitch_shift,
                watermark_enabled=req.watermark_enabled,
                watermark_path=actual_wm_path,
                video_quality="high",
            )
        else:
            out_filename = f"{stem}_sub_vi{ext}"
            out_path = dest_dir / out_filename

            srt_path = dest_dir / f"{stem}_vi.srt"
            if req.segments:
                seg_objs = [
                    Segment(id=s.id, start=s.start, end=s.end, text=s.text, translated_text=s.text)
                    for s in req.segments
                ]
                write_srt(seg_objs, srt_path, use_translated=True)
            else:
                srt_path.write_text("1\n00:00:00,000 --> 00:00:15,000\nVideo đã được xử lý biên tập và lách bản quyền\n", encoding="utf-8")

            burn_subtitles(
                video_path=target_p,
                srt_path=srt_path,
                output_path=out_path,
                font_size=req.font_size,
                sub_style=req.mask_style,
                sub_margin_v=req.margin_v,
                box_padding=req.box_padding,
                box_opacity=req.box_opacity,
                watermark_enabled=req.watermark_enabled,
                watermark_path=actual_wm_path,
                anti_video=True,
                anti_audio=req.pitch_shift,
                video_quality="high",
            )

        # Cập nhật DB
        init_db()
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM downloaded_videos WHERE raw_video_path = ?",
                (str(target_p),)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE downloaded_videos SET processed_status = 'ready', processed_video_path = ? WHERE id = ?",
                    (str(out_path), row["id"])
                )
            else:
                conn.execute(
                    """
                    INSERT INTO downloaded_videos (
                        account_id, platform, platform_video_id, title, raw_video_path,
                        downloaded_at, processed_status, processed_video_path
                    ) VALUES (?, ?, ?, ?, ?, datetime('now'), 'ready', ?)
                    """,
                    (subfolder_name, "local", stem, stem, str(target_p), str(out_path))
                )
            conn.commit()

        return {
            "success": True,
            "message": f"Đã xuất video thành phẩm thành công: {out_filename}",
            "filename": out_filename,
            "subfolder": subfolder_name,
            "output_path": str(out_path),
            "output_dir": str(dest_dir),
            "mode": req.mode,
        }
    except Exception as e:
        print(f"[studio export] Lỗi xử lý render: {e}")
        raise HTTPException(status_code=500, detail=f"Lỗi render video: {e}")


