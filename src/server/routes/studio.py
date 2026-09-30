"""Endpoints phục vụ Studio Biên Tập, Timeline, Preview Frame và A/B Testing Lab."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from ...config import OUTPUT_DIR
from ...downloader.db import get_connection, init_db
from ...downloader.lab import LAB_PRESETS
from ...downloader.settings import load_settings, save_settings
from ...media import (
    burn_subtitles,
    duration_seconds,
    extract_audio,
    extract_preview_frame,
    get_video_resolution,
    remix_video,
)
from ...subtitles import read_srt, write_srt
from ...transcribe import Segment, Transcriber
from ...translate import Translator
from ..models import AutoTranslateRequest, RenderConfigRequest
from .videos import resolve_video_path

router = APIRouter(prefix="/studio", tags=["Studio & Editor"])

ACTIVE_TRANSLATIONS: dict[str, dict[str, Any]] = {}


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


def _do_auto_translate(req: AutoTranslateRequest) -> dict[str, Any]:
    target_p = resolve_video_path(req.video_path)
    if not target_p.exists() or not target_p.is_file():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy video: {req.video_path}")

    video_key = str(target_p)
    settings = load_settings()
    model_size = req.model_size or settings.get("model_size", "medium")
    device = req.device or settings.get("device", "cuda")
    source_lang = req.source_lang or settings.get("source_lang", "zh-CN")
    target_lang = req.target_lang or settings.get("target_lang", "vi")

    ACTIVE_TRANSLATIONS[video_key] = {
        "status": "running",
        "step": 1,
        "progress": 10,
        "message": "Đang trích xuất âm thanh từ video...",
        "segments": [],
    }

    try:
        # 1. Trích xuất audio
        wav_dir = OUTPUT_DIR / "temp" / "audio"
        wav_dir.mkdir(parents=True, exist_ok=True)
        wav_path = wav_dir / f"{target_p.stem}_studio.wav"
        extract_audio(target_p, wav_path)

        # 2. Whisper nhận diện
        ACTIVE_TRANSLATIONS[video_key] = {
            "status": "running",
            "step": 2,
            "progress": 30,
            "message": f"Whisper AI ({model_size}) đang nhận diện giọng nói...",
            "segments": [],
        }

        def whisper_progress(msg: str, p: float):
            mapped = 30 + int(p * 60)
            ACTIVE_TRANSLATIONS[video_key] = {
                "status": "running",
                "step": 2,
                "progress": min(65, mapped),
                "message": msg,
                "segments": [],
            }

        transcriber = Transcriber(model_size=model_size, device=device)
        raw_segments, detected_lang = transcriber.run(
            wav_path, source_lang=source_lang, progress=whisper_progress
        )

        if not raw_segments:
            ACTIVE_TRANSLATIONS[video_key] = {
                "status": "completed",
                "step": 3,
                "progress": 100,
                "message": "Không tìm thấy giọng nói trong video.",
                "segments": [],
                "detected_language": detected_lang,
            }
            return {
                "success": True,
                "message": "Không tìm thấy giọng nói trong video.",
                "detected_language": detected_lang,
                "segments": [],
                "count": 0,
            }

        # 3. Gemini dịch sang tiếng Việt
        ACTIVE_TRANSLATIONS[video_key] = {
            "status": "running",
            "step": 3,
            "progress": 68,
            "message": f"Gemini đang dịch {len(raw_segments)} câu sang tiếng Việt...",
            "segments": [],
        }

        def translate_progress(msg: str, p: float):
            mapped = int(p * 100)
            ACTIVE_TRANSLATIONS[video_key] = {
                "status": "running",
                "step": 3,
                "progress": min(95, max(68, mapped)),
                "message": msg,
                "segments": [],
            }

        src_for_mt = source_lang if source_lang != "auto" else detected_lang
        translator = Translator(target_lang=target_lang, source_lang=src_for_mt)
        translated_segments = translator.translate_segments(
            raw_segments, progress=translate_progress
        )

        # 4. Ghi file SRT
        srt_path = target_p.parent / f"{target_p.stem}_vi.srt"
        write_srt(translated_segments, srt_path, use_translated=True)

        formatted_segments = [
            {
                "id": s.index,
                "start": round(s.start, 2),
                "end": round(s.end, 2),
                "text": s.translated or s.text,
            }
            for s in translated_segments
        ]

        ACTIVE_TRANSLATIONS[video_key] = {
            "status": "completed",
            "step": 3,
            "progress": 100,
            "message": f"Dịch thành công {len(formatted_segments)} đoạn hội thoại!",
            "segments": formatted_segments,
            "detected_language": detected_lang,
        }

        return {
            "success": True,
            "message": f"Đã nhận diện và dịch thành công {len(formatted_segments)} câu!",
            "detected_language": detected_lang,
            "segments": formatted_segments,
            "count": len(formatted_segments),
            "srt_path": str(srt_path),
        }
    except Exception as e:
        ACTIVE_TRANSLATIONS[video_key] = {
            "status": "error",
            "step": 1,
            "progress": 0,
            "message": f"Lỗi dịch thuật: {e}",
            "segments": [],
        }
        raise


@router.post("/auto-translate")
async def auto_translate_video(req: AutoTranslateRequest) -> dict[str, Any]:
    """Tự động trích xuất âm thanh, nhận diện Whisper và dịch phụ đề bằng Gemini/Google."""
    try:
        res = await asyncio.to_thread(_do_auto_translate, req)
        return res
    except HTTPException:
        raise
    except Exception as e:
        print(f"[studio auto-translate] Lỗi: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/translate-progress")
def get_translate_progress(video_path: str = Query(..., description="Đường dẫn file video")) -> dict[str, Any]:
    """Kiểm tra tiến độ dịch thuật theo thời gian thực."""
    try:
        target_p = resolve_video_path(video_path)
        video_key = str(target_p)
    except Exception:
        video_key = video_path

    info = ACTIVE_TRANSLATIONS.get(video_key)
    if not info:
        return {"status": "idle", "step": 0, "progress": 0, "message": "", "segments": []}
    return info


@router.post("/import-srt")
async def import_srt_file(
    file: UploadFile = File(...),
    video_path: str = Form(...),
) -> dict[str, Any]:
    """Tải lên file .srt từ máy tính và gán vào video hiện tại."""
    if not file.filename.lower().endswith(".srt"):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file phụ đề định dạng .srt")

    try:
        target_p = resolve_video_path(video_path)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy video: {video_path}")

    if not target_p.exists() or not target_p.is_file():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy video: {video_path}")

    # Ghi nội dung vào file {stem}_vi.srt cạnh video
    dest_srt = target_p.parent / f"{target_p.stem}_vi.srt"
    content = await file.read()
    dest_srt.write_bytes(content)

    # Đọc lại và trả về segments
    try:
        segs = read_srt(dest_srt)
        formatted_segments = [
            {
                "id": s.index,
                "start": round(s.start, 2),
                "end": round(s.end, 2),
                "text": s.translated or s.text,
            }
            for s in segs
        ]
        return {
            "success": True,
            "message": f"Đã nhập thành công {len(formatted_segments)} đoạn phụ đề!",
            "segments": formatted_segments,
            "count": len(formatted_segments),
            "srt_path": str(dest_srt),
        }
    except Exception as e:
        print(f"[studio import-srt] Lỗi đọc srt: {e}")
        raise HTTPException(status_code=400, detail=f"Không thể đọc file SRT: {e}")


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
