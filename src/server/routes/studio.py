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
from ...subtitles import read_srt, write_srt
from ...transcribe import Segment
from ..models import RenderConfigRequest
from .videos import resolve_video_path

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
    try:
        target_p = resolve_video_path(video_path)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy video: {video_path}")

    if not target_p.exists() or not target_p.is_file():
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
            "video_path": str(target_p.resolve()),
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
    try:
        target_p = resolve_video_path(video_path)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Video không tồn tại: {video_path}")

    if not target_p.exists() or not target_p.is_file():
        raise HTTPException(status_code=404, detail=f"Video không tồn tại: {video_path}")

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

    try:
        target_p = resolve_video_path(video_path)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Video không tồn tại: {video_path}")

    if not target_p.exists() or not target_p.is_file():
        raise HTTPException(status_code=404, detail=f"Video không tồn tại: {video_path}")

    try:
        dur = duration_seconds(target_p)
        if dur <= 0:
            dur = 15.0

        timestamps = [round((i / (count - 1)) * max(0.1, dur - 0.2), 2) for i in range(count)]
        frames_dir = OUTPUT_DIR / "temp" / "filmstrips" / target_p.stem
        frames_dir.mkdir(parents=True, exist_ok=True)

        def extract_single(t_sec: float, idx: int) -> dict[str, Any]:
            thumb_path = frames_dir / f"f_{idx:02d}.jpg"
            if not thumb_path.exists() or thumb_path.stat().st_size == 0:
                cmd = [
                    "ffmpeg", "-y", "-ss", str(t_sec),
                    "-i", str(target_p),
                    "-vframes", "1",
                    "-vf", "scale=-2:100",
                    "-q:v", "5",
                    str(thumb_path)
                ]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

            if thumb_path.exists() and thumb_path.stat().st_size > 0:
                with open(thumb_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                return {"index": idx, "timestamp": t_sec, "data_url": f"data:image/jpeg;base64,{b64}"}
            return {"index": idx, "timestamp": t_sec, "data_url": None}

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(extract_single, t, i) for i, t in enumerate(timestamps)]
            results = [f.result() for f in futures]

        results.sort(key=lambda x: x["index"])
        return {"video_path": str(target_p), "duration": dur, "frames": results}
    except Exception as e:
        print(f"[studio] Lỗi trích xuất timeline frames: {e}")
        return {"video_path": str(target_p), "duration": 15.0, "frames": []}


@router.get("/subtitles")
def get_video_subtitles(video_path: str = Query(..., description="Đường dẫn file video")) -> list[dict[str, Any]]:
    """Tìm và đọc các câu phụ đề từ file .srt có sẵn đi kèm với video (nếu có)."""
    try:
        target_p = resolve_video_path(video_path)
    except Exception:
        return []

    if not target_p.exists() or not target_p.is_file():
        return []

    stem = target_p.stem
    parent = target_p.parent

    # Các file srt có thể có: stem.srt, stem_vi.srt, stem_sub.srt
    candidate_srts = [
        parent / f"{stem}_vi.srt",
        parent / f"{stem}.srt",
        parent / f"{stem}_sub.srt",
        parent / f"{stem}.zh.srt",
    ]

    found_srt = None
    for srt in candidate_srts:
        if srt.exists() and srt.is_file():
            found_srt = srt
            break

    if not found_srt:
        return []

    try:
        segs = read_srt(found_srt)
        return [
            {
                "id": s.index,
                "start": round(s.start, 2),
                "end": round(s.end, 2),
                "text": s.translated or s.text,
            }
            for s in segs
        ]
    except Exception as e:
        print(f"[studio subtitles] Lỗi đọc srt: {e}")
        return []


@router.post("/upload-logo")
async def upload_watermark_logo(file: UploadFile = File(...)) -> dict[str, Any]:
    """Tải lên file ảnh logo/watermark thương hiệu (.png, .jpg) lưu vĩnh viễn trong settings."""
    if not file.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file ảnh .png, .jpg, .webp")

    save_dir = OUTPUT_DIR / "branding"
    save_dir.mkdir(parents=True, exist_ok=True)
    dest_path = save_dir / f"brand_logo_{Path(file.filename).name}"

    with open(dest_path, "wb") as buffer:
        import shutil
        shutil.copyfileobj(file.file, buffer)

    # Lưu vĩnh viễn đường dẫn vào settings.json
    settings = load_settings()
    settings["watermark_path"] = str(dest_path.resolve())
    settings["watermark_type"] = "image"
    settings["watermark_enabled"] = True
    save_settings(settings)

    return {
        "success": True,
        "message": "Đã lưu ảnh logo thương hiệu thành công",
        "filename": dest_path.name,
        "path": str(dest_path),
        "url": f"/api/fs/file?path={dest_path}",
    }


@router.get("/logo-info")
def get_watermark_logo_info() -> dict[str, Any]:
    """Lấy thông tin logo thương hiệu đang được kích hoạt."""
    settings = load_settings()
    wm_path = settings.get("watermark_path")
    exists = False
    url = None
    filename = None
    if wm_path:
        p = Path(wm_path)
        if p.exists() and p.is_file():
            exists = True
            filename = p.name
            url = f"/api/fs/file?path={p}"

    return {
        "exists": exists,
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
    try:
        target_p = resolve_video_path(req.video_path)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy video: {req.video_path}")

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
        saved_wm_path = settings.get("watermark_path")
        if saved_wm_path and Path(saved_wm_path).exists() and Path(saved_wm_path).is_file():
            actual_wm_path = Path(saved_wm_path)
        elif req.watermark_text and req.watermark_text.strip():
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
        # Nếu là chế độ Remix HOẶC người dùng xóa hết phụ đề (không có segments) -> Không đè phụ đề rác
        if req.mode == "remix" or not req.segments:
            out_filename = f"{stem}_{req.anti_combo}_remix{ext}" if req.mode == "remix" else f"{stem}_nosub{ext}"
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
            seg_objs = [
                Segment(index=s.id, start=s.start, end=s.end, text=s.text, translated=s.text)
                for s in req.segments
            ]
            write_srt(seg_objs, srt_path, use_translated=True)

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
