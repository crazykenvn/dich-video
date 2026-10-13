"""Endpoints quản lý Phân Phối Đa Nền Tảng (Publishing Matrix & Chống Up Trùng)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from fastapi import APIRouter, HTTPException, Query

from ...config import OUTPUT_DIR, SUPPORTED_VIDEO_EXT
from ...downloader.db import (
    bulk_toggle_platform_publish_status,
    get_connection,
    get_platform_publish_status,
    init_db,
    toggle_platform_publish_status,
)
from ...downloader.settings import load_settings
from ..models import BulkPublishStatusRequest, TogglePublishStatusRequest

router = APIRouter(prefix="/publishing", tags=["Multi-Platform Publishing"])


def get_output_root() -> Path:
    settings = load_settings()
    root_str = settings.get("output_root_dir")
    if root_str and Path(root_str).exists():
        return Path(root_str).resolve()
    default_dir = (OUTPUT_DIR / "ready_to_upload").resolve()
    default_dir.mkdir(parents=True, exist_ok=True)
    return default_dir


def is_valid_rendered_video(file_path: Path) -> bool:
    """Kiểm tra file video thành phẩm hợp lệ (bỏ qua file tạm .tmp.mp4, .part)."""
    name_lower = file_path.name.lower()
    if name_lower.endswith(".tmp.mp4") or name_lower.endswith(".part"):
        return False
    return file_path.is_file() and file_path.suffix.lower() in SUPPORTED_VIDEO_EXT and file_path.stat().st_size > 1024 * 50


@router.get("/subfolders")
def get_output_subfolders() -> list[dict[str, Any]]:
    """Lấy danh sách các subfolder thành phẩm trong thư mục ready_to_upload cha."""
    output_root = get_output_root()
    subfolders = []

    if output_root.exists():
        # Kiểm tra video ở ngay thư mục gốc ready_to_upload/
        root_video_count = sum(1 for f in output_root.iterdir() if is_valid_rendered_video(f))
        if root_video_count > 0:
            subfolders.append({
                "id": "_root_",
                "name": "ready_to_upload/ (Thư mục gốc)",
                "folder_name": "ready_to_upload (gốc)",
                "path": str(output_root),
                "video_count": root_video_count,
            })

        for item in output_root.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                count = sum(1 for f in item.iterdir() if is_valid_rendered_video(f))
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
    subfolder: str = Query("all", description="Lọc theo subfolder thành phẩm (all | _root_ | <subfolder_name>)"),
    filter_pending: str = Query("none", description="Lọc chống trùng: none | tiktok | reels | shorts | all_pending | all_published"),
) -> list[dict[str, Any]]:
    """Lấy danh sách video thành phẩm kèm ma trận trạng thái đăng lên từng nền tảng."""
    if not isinstance(subfolder, str):
        subfolder = getattr(subfolder, "default", "all")
    if not isinstance(filter_pending, str):
        filter_pending = getattr(filter_pending, "default", "none")

    init_db()
    output_root = get_output_root()
    video_list: list[dict[str, Any]] = []

    # Thu thập danh sách các thư mục cần quét
    scan_targets: list[tuple[Path, str]] = []  # (folder_path, subfolder_display_name)
    if output_root.exists():
        if subfolder == "all":
            # Quét cả thư mục gốc và tất cả subfolders
            scan_targets.append((output_root, "ready_to_upload"))
            for item in output_root.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    scan_targets.append((item, item.name))
        elif subfolder == "_root_":
            scan_targets.append((output_root, "ready_to_upload"))
        else:
            target_dir = output_root / subfolder
            if target_dir.exists() and target_dir.is_dir():
                scan_targets.append((target_dir, subfolder))

    # Đọc bản ghi từ DB để ánh xạ trạng thái xuất bản
    with get_connection() as conn:
        db_rows = conn.execute(
            "SELECT id, platform_video_id, raw_video_path, processed_video_path, platform_publish_status FROM downloaded_videos"
        ).fetchall()
        db_by_proc_path = {}
        db_by_raw_path = {}
        for r in db_rows:
            p_path = r["processed_video_path"]
            if p_path:
                try:
                    db_by_proc_path[str(Path(p_path).resolve()).lower()] = r
                except Exception:
                    pass
            raw_p = r["raw_video_path"]
            if raw_p:
                try:
                    db_by_raw_path[str(Path(raw_p).resolve()).lower()] = r
                except Exception:
                    pass

    for folder, folder_name in scan_targets:
        try:
            for f in folder.iterdir():
                # Nếu đang quét thư mục gốc thì chỉ lấy file, không đệ quy vào thư mục con
                if folder == output_root and f.is_dir():
                    continue

                if not is_valid_rendered_video(f):
                    continue

                stat = f.stat()
                size_mb = round(stat.st_size / (1024 * 1024), 2)
                f_name_lower = f.name.lower()
                f_path_resolved_str = str(f.resolve())
                f_path_lower = f_path_resolved_str.lower()

                # Tìm bản ghi khớp trong DB theo đường dẫn chính xác
                db_entry = db_by_proc_path.get(f_path_lower)
                if not db_entry:
                    raw_entry = db_by_raw_path.get(f_path_lower)
                    # Nếu raw_entry chưa có processed_video_path hoặc trùng thì gán luôn
                    if raw_entry:
                        existing_proc = raw_entry["processed_video_path"]
                        if not existing_proc or str(Path(existing_proc).resolve()).lower() == f_path_lower:
                            db_entry = raw_entry

                video_id: int | None = None
                if db_entry:
                    video_id = db_entry["id"]
                else:
                    # Tự động đồng bộ file thành phẩm chưa có vào DB để cấp ID cố định
                    try:
                        with get_connection() as conn:
                            cur = conn.execute(
                                """
                                INSERT INTO downloaded_videos (
                                    account_id, platform, platform_video_id, title, raw_video_path,
                                    processed_status, processed_video_path, download_status, platform_publish_status
                                ) VALUES (?, 'rendered', ?, ?, ?, 'completed', ?, 'downloaded', '{}')
                                """,
                                (folder_name, f.stem[:80], f.name, f_path_resolved_str, f_path_resolved_str),
                            )
                            conn.commit()
                            video_id = cur.lastrowid
                            # Cache lại để các lần lặp tiếp theo nhận diện được
                            new_row = {
                                "id": video_id,
                                "platform_video_id": f.stem[:80],
                                "raw_video_path": f_path_resolved_str,
                                "processed_video_path": f_path_resolved_str,
                                "platform_publish_status": "{}",
                            }
                            db_by_proc_path[f_path_lower] = new_row
                    except Exception as err:
                        print(f"[get_publishing_videos] Lỗi insert DB video {f.name}: {err}")
                        video_id = None

                platforms = get_platform_publish_status(video_id) if video_id else {}
                tk_published = platforms.get("tiktok", {}).get("is_published", False)
                reels_published = platforms.get("reels", {}).get("is_published", False)
                shorts_published = platforms.get("shorts", {}).get("is_published", False)

                # Bộ lọc trạng thái phân phối
                if filter_pending == "tiktok" and tk_published:
                    continue
                if filter_pending == "reels" and reels_published:
                    continue
                if filter_pending == "shorts" and shorts_published:
                    continue
                if filter_pending == "all_pending" and (tk_published or reels_published or shorts_published):
                    continue
                if filter_pending == "all_published" and not (tk_published and reels_published and shorts_published):
                    continue

                is_remix = "remix" in f_name_lower or "stealth" in f_name_lower
                process_type = "⚡ Remix Lách BQ" if is_remix else "🌐 Hardsub + AI Dub"

                video_item = {
                    "id": video_id or hash(str(f)) % 1000000,
                    "video_id": video_id or hash(str(f)) % 1000000,
                    "filename": f.name,
                    "path": str(f.resolve()),
                    "subfolder": folder_name,
                    "size_mb": size_mb,
                    "duration_str": "00:15",
                    "process_type": process_type,
                    "platforms": {
                        "tiktok": {"is_published": tk_published},
                        "reels": {"is_published": reels_published},
                        "shorts": {"is_published": shorts_published},
                    },
                    "tiktok": {"is_published": tk_published},
                    "reels": {"is_published": reels_published},
                    "shorts": {"is_published": shorts_published},
                }
                video_list.append(video_item)
        except Exception as e:
            print(f"[get_publishing_videos] Lỗi quét thư mục {folder}: {e}")
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


@router.post("/bulk-status")
def bulk_publish_status(req: BulkPublishStatusRequest) -> dict[str, Any]:
    """Cập nhật trạng thái xuất bản hàng loạt cho nhiều video."""
    try:
        results = bulk_toggle_platform_publish_status(req.video_ids, req.platform, req.is_published)
        return {
            "success": True,
            "updated_count": len(results),
            "platform": req.platform,
            "is_published": req.is_published,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi cập nhật hàng loạt: {e}")


@router.get("/stats")
def get_publishing_stats() -> dict[str, Any]:
    """Thống kê tổng quan số video đã render, đã up và đang chờ up."""
    videos = get_publishing_videos(subfolder="all", filter_pending="none")
    total = len(videos)
    published_tk = sum(1 for v in videos if v["tiktok"]["is_published"])
    published_reels = sum(1 for v in videos if v["reels"]["is_published"])
    published_shorts = sum(1 for v in videos if v["shorts"]["is_published"])
    all_published = sum(1 for v in videos if (v["tiktok"]["is_published"] and v["reels"]["is_published"] and v["shorts"]["is_published"]))
    pending_any = sum(1 for v in videos if not (v["tiktok"]["is_published"] or v["reels"]["is_published"] or v["shorts"]["is_published"]))

    return {
        "total_rendered": total,
        "published_tiktok": published_tk,
        "published_reels": published_reels,
        "published_shorts": published_shorts,
        "all_published": all_published,
        "pending_any": pending_any,
    }
