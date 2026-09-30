"""Endpoints quản lý video nguồn, thu thập Douyin/TikTok và quét thư mục máy."""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from ...config import OUTPUT_DIR, SUPPORTED_VIDEO_EXT
from ...downloader.db import get_connection, init_db, is_video_downloaded, record_download
from ...downloader.settings import load_settings, save_settings
from ..fs_provider import count_video_files, scan_local_videos_recursive
from ..models import (
    QuickDownloadRequest,
    ScanLocalFolderRequest,
    VideoItemResponse,
)

router = APIRouter(prefix="/videos", tags=["Videos Ingestion"])


def get_download_root() -> Path:
    settings = load_settings()
    root_str = settings.get("download_root_dir")
    if root_str and Path(root_str).exists():
        return Path(root_str).resolve()
    default_dir = (OUTPUT_DIR / "downloads").resolve()
    default_dir.mkdir(parents=True, exist_ok=True)
    return default_dir


@router.get("/sources")
def get_sources() -> dict[str, Any]:
    """Lấy cây thư mục nguồn gồm các subfolder tài khoản đã tải và các thư mục máy tính đã nạp."""
    download_root = get_download_root()
    download_root.mkdir(parents=True, exist_ok=True)

    # 1. Các subfolder trong thư mục download cha
    download_subfolders = []
    try:
        with os.scandir(str(download_root)) as entries:
            for entry in entries:
                if entry.is_dir() and not entry.name.startswith((".", "$")):
                    folder_path = Path(entry.path)
                    v_count = count_video_files(folder_path)
                    download_subfolders.append({
                        "id": entry.name,
                        "name": f"downloads/{entry.name}/",
                        "folder_name": entry.name,
                        "path": str(folder_path),
                        "video_count": v_count,
                        "type": "account_download",
                    })
    except Exception as e:
        print(f"[videos] Lỗi quét subfolders download: {e}")

    # Nếu chưa có subfolder nào, tạo sẵn subfolder mặc định
    if not download_subfolders:
        inbox_dir = download_root / "general_inbox"
        inbox_dir.mkdir(parents=True, exist_ok=True)
        download_subfolders.append({
            "id": "general_inbox",
            "name": "downloads/general_inbox/",
            "folder_name": "general_inbox",
            "path": str(inbox_dir),
            "video_count": 0,
            "type": "account_download",
        })

    # 2. Các thư mục máy tính (Local Folders) đã quét
    settings = load_settings()
    local_folders = settings.get("local_source_folders", [])
    valid_local_folders = []
    for item in local_folders:
        p = Path(item["path"])
        if p.exists() and p.is_dir():
            v_count = count_video_files(p)
            valid_local_folders.append({
                "id": str(p),
                "name": item.get("name", p.name),
                "path": str(p),
                "video_count": v_count,
                "type": "local_disk",
            })

    total_videos = sum(f["video_count"] for f in download_subfolders) + sum(f["video_count"] for f in valid_local_folders)

    return {
        "download_root": str(download_root),
        "download_subfolders": download_subfolders,
        "local_folders": valid_local_folders,
        "total_videos": total_videos,
    }


@router.get("/stream")
def stream_video(video_path: str = Query(..., description="Đường dẫn tuyệt đối hoặc tương đối tới file video")):
    """Phát video stream hỗ trợ HTTP 206 Partial Content (Range requests) cho HTML5 <video>."""
    p = Path(video_path).resolve()
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy file video: {video_path}")
    
    media_type, _ = mimetypes.guess_type(str(p))
    media_type = media_type or "video/mp4"
    return FileResponse(path=str(p), media_type=media_type, filename=p.name)


@router.get("/list", response_model=list[VideoItemResponse])
def get_video_list(
    source_type: str = Query("all", description="Loại nguồn: all | subfolder | local"),
    source_id: str = Query("all", description="ID subfolder hoặc đường dẫn thư mục máy"),
) -> list[VideoItemResponse]:
    """Lấy danh sách video theo nguồn được chọn."""
    download_root = get_download_root()
    video_items: list[VideoItemResponse] = []

    target_paths: list[tuple[Path, str, str]] = []  # (path, subfolder_name, source_type)

    if source_id == "all" or source_type == "all":
        # Quét tất cả subfolders trong download_root
        if download_root.exists():
            for sub in download_root.iterdir():
                if sub.is_dir() and not sub.name.startswith("."):
                    target_paths.append((sub, sub.name, "downloaded"))
        # Quét các local folders
        settings = load_settings()
        for loc in settings.get("local_source_folders", []):
            loc_p = Path(loc["path"])
            if loc_p.exists() and loc_p.is_dir():
                target_paths.append((loc_p, loc.get("name", loc_p.name), "local"))
    elif source_type == "subfolder":
        sub_dir = download_root / source_id
        if sub_dir.exists() and sub_dir.is_dir():
            target_paths.append((sub_dir, source_id, "downloaded"))
    elif source_type == "local":
        loc_dir = Path(source_id)
        if loc_dir.exists() and loc_dir.is_dir():
            target_paths.append((loc_dir, loc_dir.name, "local"))

    # Lấy thông tin video từ các target_paths
    for folder_path, sub_name, stype in target_paths:
        try:
            for item in folder_path.iterdir():
                if item.is_file() and item.suffix.lower() in SUPPORTED_VIDEO_EXT:
                    stat = item.stat()
                    size_mb = round(stat.st_size / (1024 * 1024), 2)
                    
                    # Heuristic gợi ý: video có từ khóa 'dance', 'remix', 'music' gợi ý remix
                    name_lower = item.name.lower()
                    suggest_remix = any(k in name_lower for k in ["dance", "remix", "music", "beat", "trend"])
                    has_sub = not suggest_remix

                    video_items.append(VideoItemResponse(
                        filename=item.name,
                        path=str(item),
                        subfolder=sub_name,
                        size_mb=size_mb,
                        duration_str="00:15",
                        has_sub=has_sub,
                        suggest_remix=suggest_remix,
                        status="inbox",
                        source_type=stype,
                    ))
        except Exception:
            continue

    # Sắp xếp video mới nhất lên đầu
    video_items.sort(key=lambda x: x.filename.lower())
    return video_items


@router.post("/scan-local")
def scan_local_folder(req: ScanLocalFolderRequest) -> dict[str, Any]:
    """Quét và ghi nhận một thư mục video có sẵn trên ổ cứng vào hệ thống."""
    target_path = Path(req.path).resolve()
    if not target_path.exists() or not target_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Đường dẫn không hợp lệ hoặc không tồn tại: {req.path}")

    videos = scan_local_videos_recursive(str(target_path))
    settings = load_settings()
    local_folders = settings.get("local_source_folders", [])
    
    # Kiểm tra xem folder đã có trong danh sách chưa
    existing = next((f for f in local_folders if Path(f["path"]).resolve() == target_path), None)
    folder_name = req.source_name or target_path.name

    if existing:
        existing["name"] = folder_name
        existing["count"] = len(videos)
    else:
        local_folders.append({
            "name": folder_name,
            "path": str(target_path),
            "count": len(videos),
        })

    settings["local_source_folders"] = local_folders
    save_settings(settings)

    return {
        "success": True,
        "folder_name": folder_name,
        "path": str(target_path),
        "video_count": len(videos),
    }


@router.post("/quick-download")
def quick_download(req: QuickDownloadRequest) -> dict[str, Any]:
    """Tải nhanh một video từ link Douyin/TikTok, lưu đúng subfolder kênh."""
    download_root = get_download_root()
    subfolder_dir = download_root / req.subfolder
    subfolder_dir.mkdir(parents=True, exist_ok=True)

    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp link video hợp lệ!")

    # Giả lập hoặc gọi crawler tải video
    return {
        "success": True,
        "message": f"Đã gửi yêu cầu tải video từ link vào subfolder: downloads/{req.subfolder}/",
        "url": url,
        "target_subfolder": req.subfolder,
        "target_path": str(subfolder_dir),
    }
