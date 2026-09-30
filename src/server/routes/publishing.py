"""Endpoints quản lý Phân Phối Đa Nền Tảng (Publishing Matrix & Chống Up Trùng)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from fastapi import APIRouter, HTTPException, Query

from ...config import OUTPUT_DIR, SUPPORTED_VIDEO_EXT
from ...downloader.db import (
    get_connection,
    get_platform_publish_status,
    init_db,
    toggle_platform_publish_status,
)
from ...downloader.settings import load_settings
from ..models import TogglePublishStatusRequest

router = APIRouter(prefix="/publishing", tags=["Multi-Platform Publishing"])


def get_output_root() -> Path:
    settings = load_settings()
    root_str = settings.get("output_root_dir")
    if root_str and Path(root_str).exists():
        return Path(root_str).resolve()
    default_dir = (OUTPUT_DIR / "ready_to_upload").resolve()
    default_dir.mkdir(parents=True, exist_ok=True)
    return default_dir


@router.get("/subfolders")
def get_output_subfolders() -> list[dict[str, Any]]:
    """Lấy danh sách các subfolder thành phẩm trong thư mục ready_to_upload cha."""
    output_root = get_output_root()
    subfolders = []

    if output_root.exists():
        for item in output_root.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                # Đếm số lượng video trong subfolder
                count = sum(1 for f in item.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_VIDEO_EXT)
                subfolders.append({
                    "id": item.name,
                    "name": f"ready_to_upload/{item.name}/",
                    "folder_name": item.name,
                    "path": str(item),
                    "video_count": count,
                })
    return subfolders


@router.get("/videos")
def get_publishing_videos(
    subfolder: str = Query("all", description="Lọc theo subfolder thành phẩm (all | <subfolder_name>)"),
    filter_pending: str = Query("none", description="Lọc chống trùng: none | tiktok | reels | shorts"),
) -> list[dict[str, Any]]:
    """Lấy danh sách video thành phẩm kèm ma trận trạng thái đăng lên từng nền tảng."""
    init_db()
    output_root = get_output_root()
    video_list: list[dict[str, Any]] = []

    target_folders: list[Path] = []
    if subfolder == "all":
        if output_root.exists():
            for item in output_root.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    target_folders.append(item)
    else:
        target_dir = output_root / subfolder
        if target_dir.exists() and target_dir.is_dir():
            target_folders.append(target_dir)

    # Đọc thông tin từ DB để lấy trạng thái publish nếu có
    with get_connection() as conn:
        db_rows = conn.execute("SELECT id, raw_video_path, processed_video_path, platform_publish_status FROM downloaded_videos").fetchall()
        db_map = {}
        for r in db_rows:
            p_path = r["processed_video_path"]
            if p_path:
                db_map[Path(p_path).name.lower()] = r

    for folder in target_folders:
        try:
            for f in folder.iterdir():
                if f.is_file() and f.suffix.lower() in SUPPORTED_VIDEO_EXT:
                    stat = f.stat()
                    size_mb = round(stat.st_size / (1024 * 1024), 2)
                    
                    db_entry = db_map.get(f.name.lower())
                    video_id = db_entry["id"] if db_entry else None
                    platforms = {}
                    if video_id:
                        platforms = get_platform_publish_status(video_id)

                    # Mặc định cấu trúc cho các nền tảng
                    tk_published = platforms.get("tiktok", {}).get("is_published", False)
                    reels_published = platforms.get("reels", {}).get("is_published", False)
                    shorts_published = platforms.get("shorts", {}).get("is_published", False)

                    # Áp dụng bộ lọc chống up trùng nếu có yêu cầu
                    if filter_pending == "tiktok" and tk_published:
                        continue
                    if filter_pending == "reels" and reels_published:
                        continue
                    if filter_pending == "shorts" and shorts_published:
                        continue

                    # Kiểu xử lý
                    is_remix = "remix" in f.name.lower() or "stealth" in f.name.lower()
                    process_type = "⚡ Remix Lách BQ" if is_remix else "🌐 Hardsub + AI Dub"

                    video_list.append({
                        "video_id": video_id or hash(str(f)) % 1000000,
                        "filename": f.name,
                        "path": str(f),
                        "subfolder": folder.name,
                        "size_mb": size_mb,
                        "process_type": process_type,
                        "tiktok": {"is_published": tk_published},
                        "reels": {"is_published": reels_published},
                        "shorts": {"is_published": shorts_published},
                    })
        except Exception:
            continue

    video_list.sort(key=lambda x: x["filename"].lower())
    return video_list


@router.post("/toggle-status")
def toggle_publish_status(req: TogglePublishStatusRequest) -> dict[str, Any]:
    """Cập nhật trạng thái đăng tải video lên một nền tảng (TikTok, Reels, Shorts)."""
    try:
        updated = toggle_platform_publish_status(req.video_id, req.platform, req.is_published)
        return {
            "success": True,
            "video_id": req.video_id,
            "platform": req.platform,
            "publish_status": updated,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi cập nhật trạng thái xuất bản: {e}")


@router.get("/stats")
def get_publishing_stats() -> dict[str, Any]:
    """Thống kê tổng quan số video đã render, đã up và đang chờ up."""
    videos = get_publishing_videos(subfolder="all", filter_pending="none")
    total = len(videos)
    published_tk = sum(1 for v in videos if v["tiktok"]["is_published"])
    published_reels = sum(1 for v in videos if v["reels"]["is_published"])
    published_shorts = sum(1 for v in videos if v["shorts"]["is_published"])
    pending_any = sum(1 for v in videos if not (v["tiktok"]["is_published"] or v["reels"]["is_published"] or v["shorts"]["is_published"]))

    return {
        "total_rendered": total,
        "published_tiktok": published_tk,
        "published_reels": published_reels,
        "published_shorts": published_shorts,
        "pending_any": pending_any,
    }
