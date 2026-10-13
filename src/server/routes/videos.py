"""Endpoints quản lý video nguồn, thu thập Douyin/TikTok và quét thư mục máy."""

from __future__ import annotations

import mimetypes
import os
import shutil
from pathlib import Path
from typing import Any
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from ...config import OUTPUT_DIR, PROJECT_ROOT, SUPPORTED_VIDEO_EXT
from ...downloader.db import (
    add_account,
    delete_account,
    delete_discovered_videos,
    delete_video_by_id,
    get_accounts,
    get_account_videos_from_db,
    get_connection,
    get_video_by_id,
    init_db,
    is_video_downloaded,
    mark_video_downloaded,
    record_download,
    reset_account_scan,
    update_account_info,
    update_account_status,
)
from ...downloader.manager import DownloadManager, cleanup_thumbnail_file, sanitize_filename
from ...downloader.douyin_engine import (
    DouyinDownloader,
    is_douyin_logged_in,
    DOUYIN_COOKIE_FILE,
    DOUYIN_COOKIE_JSON,
    DOUYIN_PROFILE_DIR,
    DOUYIN_LOGIN_INDICATORS,
    save_imported_cookies,
    save_netscape_cookies,
)
from ...downloader.ytdlp_engine import YtDlpEngine
from ...downloader.settings import load_settings, save_settings
from ..fs_provider import count_video_files, scan_local_videos_recursive
from ..models import (
    AddAccountRequest,
    ClearThumbnailsRequest,
    DeleteVideoRequest,
    DownloadDiscoveredRequest,
    QuickDownloadRequest,
    RemoveFolderRequest,
    ResetScanRequest,
    SaveDouyinCookieRequest,
    ScanAccountsRequest,
    ScanLocalFolderRequest,
    ToggleAccountRequest,
    UpdateAccountRequest,
    VideoItemResponse,
)

router = APIRouter(prefix="/videos", tags=["Videos Ingestion"])


def format_duration(seconds: float | int | None) -> str:
    """Đổi số giây sang định dạng MM:SS hoặc HH:MM:SS."""
    if not seconds or seconds <= 0:
        return "00:15"
    s = int(seconds)
    m = s // 60
    sec = s % 60
    h = m // 60
    m = m % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


def get_download_root() -> Path:
    settings = load_settings()
    root_str = settings.get("download_root_dir")
    if root_str and Path(root_str).exists():
        return Path(root_str).resolve()
    default_dir = (OUTPUT_DIR / "downloads").resolve()
    default_dir.mkdir(parents=True, exist_ok=True)
    return default_dir


def resolve_video_path(video_path: str) -> Path:
    """Tìm và trả về đường dẫn Path tuyệt đối của file video trên ổ đĩa.
    Hỗ trợ cả đường dẫn tương đối, tên file, hoặc đường dẫn trong thư mục downloads/local.
    """
    if not video_path:
        raise HTTPException(status_code=400, detail="Đường dẫn video không được để trống")

    # 1. Thử đường dẫn tuyệt đối trực tiếp
    p = Path(video_path).resolve()
    if p.exists() and p.is_file():
        return p

    download_root = get_download_root()

    # 2. Thử trong download_root
    cand = (download_root / video_path).resolve()
    if cand.exists() and cand.is_file():
        return cand

    # 3. Thử trong download_root/general_inbox/
    cand = (download_root / "general_inbox" / Path(video_path).name).resolve()
    if cand.exists() and cand.is_file():
        return cand

    # 4. Thử trong thư mục OUTPUT_DIR
    cand = (OUTPUT_DIR / video_path).resolve()
    if cand.exists() and cand.is_file():
        return cand

    # 5. Thử trong tất cả local_source_folders đã lưu
    settings = load_settings()
    for loc in settings.get("local_source_folders", []):
        loc_dir = Path(loc["path"])
        cand1 = (loc_dir / video_path).resolve()
        if cand1.exists() and cand1.is_file():
            return cand1
        cand2 = (loc_dir / Path(video_path).name).resolve()
        if cand2.exists() and cand2.is_file():
            return cand2

    # 6. Thử trong ready_to_upload
    cand = (OUTPUT_DIR / "ready_to_upload" / video_path).resolve()
    if cand.exists() and cand.is_file():
        return cand

    # 7. Quét đệ quy các subfolder trong download_root tìm theo tên file
    target_name = Path(video_path).name
    if download_root.exists():
        for sub in download_root.iterdir():
            if sub.is_dir():
                sub_cand = sub / target_name
                if sub_cand.exists() and sub_cand.is_file():
                    return sub_cand.resolve()

    return p


def pick_native_folder() -> str:
    """Mở hộp thoại Windows Explorer để người dùng chọn thư mục video."""
    # Thử qua tkinter
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title="Chọn thư mục chứa video trên máy tính")
        root.destroy()
        if folder:
            return str(folder)
    except Exception:
        pass

    # Fallback qua PowerShell Windows Forms
    try:
        import subprocess
        ps_cmd = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
            "$f.Description = 'Chọn thư mục chứa video trên máy tính'; "
            "if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $f.SelectedPath }"
        )
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, timeout=120)
        out = res.stdout.strip()
        if out:
            return out
    except Exception as e:
        print(f"[videos] Lỗi mở FolderBrowserDialog: {e}")
    return ""


def pick_native_files() -> list[str]:
    """Mở hộp thoại Windows Explorer để người dùng chọn các file video."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        files = filedialog.askopenfilenames(
            title="Chọn các file video từ máy tính",
            filetypes=[
                ("Video files", "*.mp4 *.mkv *.mov *.webm *.avi *.flv *.ts *.wmv *.m4v"),
                ("All files", "*.*"),
            ],
        )
        root.destroy()
        if files:
            return [str(f) for f in files]
    except Exception:
        pass

    try:
        import subprocess
        ps_cmd = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$f = New-Object System.Windows.Forms.OpenFileDialog; "
            "$f.Filter = 'Video files (*.mp4;*.mkv;*.mov;*.webm;*.avi;*.flv;*.ts;*.wmv;*.m4v)|*.mp4;*.mkv;*.mov;*.webm;*.avi;*.flv;*.ts;*.wmv;*.m4v|All files (*.*)|*.*'; "
            "$f.Multiselect = $true; "
            "$f.Title = 'Chọn các file video từ máy tính'; "
            "if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { $f.FileNames | ForEach-Object { Write-Output $_ } }"
        )
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, timeout=120)
        lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        if lines:
            return lines
    except Exception as e:
        print(f"[videos] Lỗi mở OpenFileDialog: {e}")
    return []


@router.get("/sources")
def get_sources() -> dict[str, Any]:
    """Lấy cây thư mục nguồn gồm các subfolder tài khoản đã tải và các thư mục máy tính đã nạp."""
    download_root = get_download_root()
    download_root.mkdir(parents=True, exist_ok=True)
    init_db()

    # 1. Các subfolder trong thư mục download cha
    download_subfolders = []
    seen_folder_names: set[str] = set()
    try:
        with os.scandir(str(download_root)) as entries:
            for entry in entries:
                if entry.is_dir() and not entry.name.startswith((".", "$")):
                    folder_path = Path(entry.path)
                    v_count = count_video_files(folder_path)
                    # Cũng đếm số video trong DB (cả discovered lẫn downloaded)
                    db_vids = get_account_videos_from_db(entry.name)
                    if not db_vids and "_" in entry.name:
                        acc_part = entry.name.split("_", 1)[1]
                        db_vids = get_account_videos_from_db(acc_part)
                    total_v = max(v_count, len(db_vids))

                    download_subfolders.append({
                        "id": entry.name,
                        "name": f"downloads/{entry.name}/",
                        "folder_name": entry.name,
                        "path": str(folder_path.resolve()),
                        "video_count": total_v,
                        "type": "account_download",
                    })
                    seen_folder_names.add(entry.name)
    except Exception as e:
        print(f"[videos] Lỗi quét subfolders download: {e}")

    # Bổ sung các tài khoản trong monitored_accounts chưa tạo thư mục vật lý trên đĩa
    for acc in get_accounts(active_only=False):
        f_name = f"{acc['platform']}_{sanitize_filename(acc['account_id'])}"
        if f_name not in seen_folder_names:
            db_vids = get_account_videos_from_db(acc["account_id"])
            acc_dir = download_root / f_name
            download_subfolders.append({
                "id": f_name,
                "name": f"downloads/{f_name}/",
                "folder_name": f_name,
                "path": str(acc_dir.resolve()),
                "video_count": len(db_vids),
                "type": "account_download",
            })
            seen_folder_names.add(f_name)

    # Nếu chưa có subfolder nào, tạo sẵn subfolder mặc định
    if not download_subfolders:
        inbox_dir = download_root / "general_inbox"
        inbox_dir.mkdir(parents=True, exist_ok=True)
        download_subfolders.append({
            "id": "general_inbox",
            "name": "downloads/general_inbox/",
            "folder_name": "general_inbox",
            "path": str(inbox_dir.resolve()),
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
                "id": str(p.resolve()),
                "name": item.get("name", p.name),
                "path": str(p.resolve()),
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
    p = resolve_video_path(video_path)
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
    """Lấy danh sách video theo nguồn được chọn (bao gồm cả video đã tải về máy và video mới quét metadata/thumbnail)."""
    download_root = get_download_root()
    video_items: list[VideoItemResponse] = []
    init_db()

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
        if not loc_dir.exists() or not loc_dir.is_dir():
            # Check theo tên trong settings
            settings = load_settings()
            for loc in settings.get("local_source_folders", []):
                if loc.get("name") == source_id or loc.get("path") == source_id:
                    loc_dir = Path(loc["path"])
                    break
        if loc_dir.exists() and loc_dir.is_dir():
            target_paths.append((loc_dir, loc_dir.name, "local"))
        elif loc_dir.exists() and loc_dir.is_file():
            # Trường hợp source_id là một file cụ thể
            stat = loc_dir.stat()
            size_mb = round(stat.st_size / (1024 * 1024), 2)
            name_lower = loc_dir.name.lower()
            suggest_remix = any(k in name_lower for k in ["dance", "remix", "music", "beat", "trend"])
            return [VideoItemResponse(
                filename=loc_dir.name,
                path=str(loc_dir.resolve()),
                subfolder="local_files",
                size_mb=size_mb,
                duration_str="00:15",
                has_sub=not suggest_remix,
                suggest_remix=suggest_remix,
                status="inbox",
                source_type="local",
                download_status="downloaded",
            )]

    # Lấy thông tin video từ DB để map metadata / thumbnail / id
    db_videos: list[dict[str, Any]] = []
    if source_type == "subfolder" and source_id != "all":
        acc_cand = source_id.split("_", 1)[1] if "_" in source_id else source_id
        db_videos = get_account_videos_from_db(acc_cand)
        if not db_videos and acc_cand != source_id:
            db_videos = get_account_videos_from_db(source_id)
    elif source_type == "all" or source_id == "all":
        db_videos = get_account_videos_from_db(None)

    # Index db_videos theo platform_video_id và filename
    db_by_id: dict[str, dict[str, Any]] = {}
    db_by_path: dict[str, dict[str, Any]] = {}
    for db_v in db_videos:
        p_vid = str(db_v.get("platform_video_id") or "")
        if p_vid:
            db_by_id[p_vid] = db_v
        raw_p = db_v.get("raw_video_path") or ""
        if raw_p:
            db_by_path[Path(raw_p).name.lower()] = db_v

    seen_db_ids: set[int] = set()

    # 1. Quét các file video thực tế trên ổ cứng
    for folder_path, sub_name, stype in target_paths:
        try:
            for item in folder_path.iterdir():
                if item.is_file() and item.suffix.lower() in SUPPORTED_VIDEO_EXT:
                    stat = item.stat()
                    size_mb = round(stat.st_size / (1024 * 1024), 2)
                    name_lower = item.name.lower()
                    suggest_remix = any(k in name_lower for k in ["dance", "remix", "music", "beat", "trend"])
                    has_sub = not suggest_remix

                    # Tìm record tương ứng trong DB
                    matched_db = db_by_path.get(name_lower)
                    if not matched_db:
                        for vid_key, db_v in db_by_id.items():
                            if vid_key in item.name:
                                matched_db = db_v
                                break

                    v_id = None
                    thumb_url = None
                    vid_url = None
                    plat = None
                    plat_vid = None
                    acc_id = None
                    duration_s = "00:15"
                    pub_at = None
                    is_pin = 0

                    proc_status = "inbox"
                    proc_path = None
                    is_uploaded = False

                    if matched_db:
                        v_id = matched_db["id"]
                        seen_db_ids.add(v_id)
                        thumb_url = matched_db.get("thumbnail_url")
                        vid_url = matched_db.get("video_url")
                        plat = matched_db.get("platform")
                        plat_vid = matched_db.get("platform_video_id")
                        acc_id = matched_db.get("account_id")
                        duration_s = format_duration(matched_db.get("duration", 0))
                        pub_at = matched_db.get("published_at")
                        is_pin = int(matched_db.get("is_pinned") or 0)
                        proc_status = matched_db.get("processed_status") or "inbox"
                        proc_path = matched_db.get("processed_video_path")
                        is_uploaded = bool(matched_db.get("is_uploaded"))
                    else:
                        try:
                            from datetime import datetime, timezone
                            pub_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
                        except Exception:
                            pass

                    # Kiểm tra file thành phẩm xuất trong ready_to_upload
                    ready_sub_dir = (OUTPUT_DIR / "ready_to_upload" / sub_name).resolve()
                    exported_file = None
                    if proc_path and Path(proc_path).exists() and Path(proc_path).is_file():
                        exported_file = str(Path(proc_path).resolve())
                    elif ready_sub_dir.exists():
                        for f in ready_sub_dir.glob(f"{item.stem}*.*"):
                            if f.is_file() and f.suffix.lower() in SUPPORTED_VIDEO_EXT:
                                exported_file = str(f.resolve())
                                break

                    # Kiểm tra file phụ đề & lồng tiếng đã tạo
                    sub_dir = (OUTPUT_DIR / "subtitles").resolve()
                    has_sub_file = (
                        (item.parent / f"{item.stem}_meta.json").exists()
                        or (item.parent / f"{item.stem}_vi.srt").exists()
                        or (sub_dir / f"{item.stem}_meta.json").exists()
                        or (sub_dir / f"{item.stem}_vi.srt").exists()
                    )
                    has_dub_file = (
                        (item.parent / f"{item.stem}_dub_vi.wav").exists()
                        or (sub_dir / f"{item.stem}_dub_vi.wav").exists()
                    )

                    is_processed = bool(
                        exported_file
                        or proc_status in ("ready", "completed", "published")
                        or is_uploaded
                    )
                    if is_processed and proc_status == "inbox":
                        proc_status = "ready"

                    video_items.append(VideoItemResponse(
                        id=v_id,
                        filename=item.name,
                        path=str(item.resolve()),
                        subfolder=sub_name,
                        size_mb=size_mb,
                        duration_str=duration_s,
                        has_sub=has_sub,
                        suggest_remix=suggest_remix,
                        status=proc_status,
                        processed_status=proc_status,
                        is_processed=is_processed,
                        processed_video_path=exported_file or proc_path,
                        has_sub_file=has_sub_file,
                        has_dub_file=has_dub_file,
                        is_uploaded=is_uploaded,
                        source_type=stype,
                        thumbnail_url=thumb_url,
                        video_url=vid_url,
                        download_status="downloaded",
                        platform=plat,
                        platform_video_id=plat_vid,
                        account_id=acc_id,
                        published_at=pub_at,
                        is_pinned=is_pin,
                    ))
        except Exception:
            continue

    # 2. Thêm các video mới quét metadata/thumbnail trong DB (chưa tải file mp4 vật lý)
    if source_type in ("all", "subfolder"):
        for db_v in db_videos:
            db_id = db_v["id"]
            if db_id in seen_db_ids:
                continue

            # Nếu status là 'discovered' hoặc file trên đĩa chưa tồn tại
            is_downloaded = (
                db_v.get("download_status") == "downloaded"
                and db_v.get("raw_video_path")
                and Path(db_v["raw_video_path"]).exists()
            )
            if not is_downloaded:
                acc_id = db_v.get("account_id") or "general_inbox"
                plat = db_v.get("platform") or "video"
                sub_folder_name = f"{plat}_{sanitize_filename(acc_id)}" if acc_id != "general_inbox" else "general_inbox"

                # Nếu lọc theo subfolder cụ thể, đảm bảo subfolder khớp
                if source_type == "subfolder" and source_id != "all":
                    if source_id != sub_folder_name and source_id != acc_id:
                        continue

                title = db_v.get("title") or f"{plat}_{db_v.get('platform_video_id')}"
                name_lower = title.lower()
                suggest_remix = any(k in name_lower for k in ["dance", "remix", "music", "beat", "trend"])

                proc_status = db_v.get("processed_status") or "inbox"
                proc_path = db_v.get("processed_video_path")
                is_uploaded = bool(db_v.get("is_uploaded"))
                is_processed = bool(
                    proc_status in ("ready", "completed", "published")
                    or (proc_path and Path(proc_path).exists())
                    or is_uploaded
                )

                video_items.append(VideoItemResponse(
                    id=db_id,
                    filename=title,
                    path="",
                    subfolder=sub_folder_name,
                    size_mb=0.0,
                    duration_str=format_duration(db_v.get("duration", 0)),
                    has_sub=not suggest_remix,
                    suggest_remix=suggest_remix,
                    status=proc_status,
                    processed_status=proc_status,
                    is_processed=is_processed,
                    processed_video_path=proc_path,
                    has_sub_file=False,
                    has_dub_file=False,
                    is_uploaded=is_uploaded,
                    source_type="downloaded",
                    thumbnail_url=db_v.get("thumbnail_url"),
                    video_url=db_v.get("video_url"),
                    download_status="discovered",
                    platform=plat,
                    platform_video_id=db_v.get("platform_video_id"),
                    account_id=acc_id,
                    published_at=db_v.get("published_at"),
                    is_pinned=int(db_v.get("is_pinned") or 0),
                ))

    # Sắp xếp video chuẩn như Douyin: Video ghim lên đầu (is_pinned DESC), video mới nhất lên trước (published_at DESC), fallback id DESC
    video_items.sort(
        key=lambda x: (
            getattr(x, "is_pinned", 0) or 0,
            x.published_at or "",
            x.id or 0,
        ),
        reverse=True,
    )
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


@router.post("/pick-folder")
def pick_folder_dialog() -> dict[str, Any]:
    """Mở hộp thoại Windows Explorer để người dùng chọn thư mục chứa video trên máy."""
    folder = pick_native_folder()
    if not folder:
        return {"success": False, "message": "Người dùng đã hủy chọn thư mục"}

    target_path = Path(folder).resolve()
    if not target_path.exists() or not target_path.is_dir():
        return {"success": False, "message": f"Thư mục không tồn tại: {folder}"}

    videos = scan_local_videos_recursive(str(target_path))
    settings = load_settings()
    local_folders = settings.get("local_source_folders", [])
    
    folder_name = target_path.name
    existing = next((f for f in local_folders if Path(f["path"]).resolve() == target_path), None)
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

    # Lấy danh sách video items để trả về luôn
    video_items = []
    for item in target_path.iterdir():
        if item.is_file() and item.suffix.lower() in SUPPORTED_VIDEO_EXT:
            stat = item.stat()
            size_mb = round(stat.st_size / (1024 * 1024), 2)
            name_lower = item.name.lower()
            suggest_remix = any(k in name_lower for k in ["dance", "remix", "music", "beat", "trend"])
            video_items.append({
                "filename": item.name,
                "path": str(item.resolve()),
                "subfolder": folder_name,
                "size_mb": size_mb,
                "duration_str": "00:15",
                "has_sub": not suggest_remix,
                "suggest_remix": suggest_remix,
                "status": "inbox",
                "source_type": "local",
            })

    video_items.sort(key=lambda x: x["filename"].lower())

    return {
        "success": True,
        "folder_name": folder_name,
        "path": str(target_path),
        "video_count": len(videos),
        "videos": video_items,
    }


@router.post("/pick-files")
def pick_files_dialog() -> dict[str, Any]:
    """Mở hộp thoại Windows Explorer để người dùng chọn trực tiếp các file video."""
    files = pick_native_files()
    if not files:
        return {"success": False, "message": "Người dùng đã hủy chọn file", "videos": []}

    video_items = []
    for f in files:
        p = Path(f).resolve()
        if p.exists() and p.is_file():
            stat = p.stat()
            size_mb = round(stat.st_size / (1024 * 1024), 2)
            name_lower = p.name.lower()
            suggest_remix = any(k in name_lower for k in ["dance", "remix", "music", "beat", "trend"])
            video_items.append({
                "filename": p.name,
                "path": str(p),
                "subfolder": p.parent.name,
                "size_mb": size_mb,
                "duration_str": "00:15",
                "has_sub": not suggest_remix,
                "suggest_remix": suggest_remix,
                "status": "inbox",
                "source_type": "local",
            })

    return {
        "success": True,
        "count": len(video_items),
        "videos": video_items,
    }


@router.post("/upload")
async def upload_local_video(file: UploadFile = File(...)) -> dict[str, Any]:
    """Tải trực tiếp một file video lên máy chủ lưu vào general_inbox/ để mở ngay trong Studio."""
    download_root = get_download_root()
    inbox_dir = download_root / "general_inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    dest_path = inbox_dir / file.filename
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    stat = dest_path.stat()
    size_mb = round(stat.st_size / (1024 * 1024), 2)
    name_lower = dest_path.name.lower()
    suggest_remix = any(k in name_lower for k in ["dance", "remix", "music", "beat", "trend"])

    video_item = {
        "filename": dest_path.name,
        "path": str(dest_path.resolve()),
        "subfolder": "general_inbox",
        "size_mb": size_mb,
        "duration_str": "00:15",
        "has_sub": not suggest_remix,
        "suggest_remix": suggest_remix,
        "status": "inbox",
        "source_type": "downloaded",
    }

    return {
        "success": True,
        "message": f"Đã nạp file video thành công: {dest_path.name}",
        "video": video_item,
    }


@router.post("/remove-folder")
def remove_folder(req: RemoveFolderRequest) -> dict[str, Any]:
    """Gỡ bỏ một thư mục khỏi danh sách nguồn (Local folders hoặc Subfolder downloads)."""
    settings = load_settings()
    local_folders = settings.get("local_source_folders", [])

    if req.folder_type == "local":
        target_path_str = req.path.strip()
        norm_target = str(Path(target_path_str).resolve()).lower()
        new_local = []
        removed = False
        for f in local_folders:
            f_norm = str(Path(f["path"]).resolve()).lower()
            if f_norm == norm_target or f.get("name") == target_path_str:
                removed = True
            else:
                new_local.append(f)

        settings["local_source_folders"] = new_local
        save_settings(settings)
        return {
            "success": True,
            "removed": removed,
            "message": f"Đã gỡ bỏ thư mục máy tính: {req.path}",
        }

    elif req.folder_type == "subfolder":
        download_root = get_download_root()
        sub_dir = (download_root / req.path).resolve()

        if sub_dir == download_root or req.path in ["general_inbox", "", "."]:
            raise HTTPException(status_code=400, detail="Không thể xóa thư mục mặc định này!")

        if sub_dir.exists() and sub_dir.is_dir():
            try:
                shutil.rmtree(sub_dir)
                return {"success": True, "message": f"Đã xóa thư mục tải về: {req.path}"}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Không thể xóa thư mục: {e}")
        else:
            return {"success": True, "message": "Thư mục không tồn tại hoặc đã được xóa"}

    raise HTTPException(status_code=400, detail="Loại thư mục không hợp lệ")


# =============================================================================
# CRAWLER: QUẢN LÝ TÀI KHOẢN VÀ CÀO VIDEO ĐA NỀN TẢNG (DOUYIN, TIKTOK, BILIBILI)
# =============================================================================

@router.get("/crawler/accounts")
def get_crawler_accounts() -> list[dict[str, Any]]:
    """Lấy danh sách các tài khoản đang theo dõi từ cơ sở dữ liệu."""
    init_db()
    return get_accounts(active_only=False)


@router.post("/crawler/accounts")
def add_crawler_account(req: AddAccountRequest) -> dict[str, Any]:
    """Thêm tài khoản mới vào danh sách theo dõi."""
    init_db()
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp link kênh / tài khoản!")

    import time
    acc_id = req.account_id
    if not acc_id:
        acc_id = url.rstrip("/").split("/")[-1].split("?")[0]
        if not acc_id:
            acc_id = f"{req.platform}_{int(time.time())}"

    name = (req.name or "").strip() or acc_id

    add_account(
        platform=req.platform.lower(),
        account_id=acc_id,
        account_url=url,
        account_name=name,
        auto_process=req.auto_process,
        process_mode=req.mode,
    )

    # Đảm bảo tạo thư mục tương ứng trong downloads/
    download_root = get_download_root()
    sub_dir = download_root / f"{req.platform.lower()}_{sanitize_filename(acc_id)}"
    sub_dir.mkdir(parents=True, exist_ok=True)

    return {
        "success": True,
        "message": f"Đã thêm tài khoản [{req.platform.upper()}] {name} vào danh sách theo dõi!",
        "account_id": acc_id,
        "folder": sub_dir.name,
    }


@router.post("/crawler/toggle")
def toggle_crawler_account(req: ToggleAccountRequest) -> dict[str, Any]:
    """Bật / Tắt trạng thái tự động quét của tài khoản."""
    init_db()
    update_account_status(req.account_id, req.is_active)
    return {
        "success": True,
        "account_id": req.account_id,
        "is_active": req.is_active,
    }


@router.put("/crawler/accounts/{account_id}")
def update_crawler_account(account_id: str, req: UpdateAccountRequest) -> dict[str, Any]:
    """Cập nhật thông tin kênh theo dõi (tên gợi nhớ, link, chế độ xử lý)."""
    init_db()
    accounts = get_accounts(active_only=False)
    target = next((a for a in accounts if a["account_id"] == account_id), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy tài khoản {account_id}")

    ok = update_account_info(
        account_id=account_id,
        account_name=req.account_name,
        account_url=req.account_url,
        process_mode=req.process_mode,
        auto_process=req.auto_process,
    )
    if not ok:
        raise HTTPException(status_code=400, detail="Không có thông tin nào được cập nhật hoặc dữ liệu không đổi")

    updated_accs = get_accounts(active_only=False)
    updated_target = next((a for a in updated_accs if a["account_id"] == account_id), None)
    return {
        "success": True,
        "message": f"Đã cập nhật kênh {req.account_name or account_id} thành công!",
        "account": updated_target,
    }


@router.delete("/crawler/accounts/{account_id}")
def delete_crawler_account(account_id: str) -> dict[str, Any]:
    """Xóa tài khoản khỏi danh sách theo dõi."""
    init_db()
    delete_account(account_id)
    return {
        "success": True,
        "message": f"Đã xóa tài khoản {account_id} khỏi danh sách theo dõi",
    }


@router.post("/crawler/scan")
def scan_crawler_accounts(req: ScanAccountsRequest) -> dict[str, Any]:
    """Quét và lấy metadata + thumbnail từ kênh (không tự động tải file video mp4 vật lý).
    Hỗ trợ force_full_scan=True để reset mốc quét và quét lại toàn bộ kênh từ đầu."""
    init_db()
    manager = DownloadManager()

    if req.force_full_scan:
        reset_account_scan(req.account_id)

    if req.account_id:
        accounts = get_accounts(active_only=False)
        target = next((a for a in accounts if a["account_id"] == req.account_id), None)
        if not target:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy tài khoản: {req.account_id}")
        discovered = manager.scan_account(
            target,
            max_videos=req.max_videos,
            force_full_scan=req.force_full_scan,
        )
    else:
        discovered = manager.scan_all_accounts(
            max_videos_per_account=req.max_videos,
            force_full_scan=req.force_full_scan,
        )

    scan_mode_msg = "toàn bộ kênh từ đầu" if req.force_full_scan else "video mới"
    dy_logged = is_douyin_logged_in()
    warning_msg = None
    if len(discovered) <= 21 and not dy_logged:
        warning_msg = (
            "Douyin giới hạn khách vãng lai chỉ lấy được 21 video đầu ('登录后查看更多作品'). "
            "Để cào toàn bộ các video còn lại của kênh, vui lòng bấm nút [🔑 Đăng Nhập Douyin] trên thanh công cụ để quét mã QR một lần duy nhất!"
        )

    return {
        "success": True,
        "discovered_count": len(discovered),
        "discovered_videos": discovered,
        "douyin_logged_in": dy_logged,
        "warning": warning_msg,
        "message": f"Quét hoàn tất ({scan_mode_msg}): Đã tìm thấy {len(discovered)} video và tải thumbnail!" + (f"\nLƯU Ý: {warning_msg}" if warning_msg else ""),
    }


@router.get("/crawler/douyin-status")
def douyin_status() -> dict[str, Any]:
    """Kiểm tra trạng thái đăng nhập Douyin trong profile cookies."""
    logged = is_douyin_logged_in()
    return {
        "logged_in": logged,
        "message": "✓ Douyin đã đăng nhập thành công" if logged else "Douyin chưa đăng nhập (giới hạn 21 video)",
    }


@router.post("/crawler/reset-scan")
def reset_crawler_scan(req: ResetScanRequest) -> dict[str, Any]:
    """Reset mốc quét của tài khoản để lần quét tiếp theo sẽ quét lại toàn bộ kênh từ đầu.
    Nếu delete_discovered=True, cũng xóa các thumbnail và video chờ tải cũ."""
    init_db()
    reset_account_scan(req.account_id)

    cleared_count = 0
    if req.delete_discovered:
        deleted_rows = delete_discovered_videos(req.account_id)
        cleared_count = len(deleted_rows)
        for row in deleted_rows:
            cleanup_thumbnail_file(
                thumbnail_url=row.get("thumbnail_url") or "",
                platform=row.get("platform") or "",
                vid_id=str(row.get("platform_video_id") or ""),
            )

    target_name = req.account_id if req.account_id else "tất cả các kênh"
    return {
        "success": True,
        "cleared_thumbnails": cleared_count,
        "message": f"Đã reset mốc quét cho {target_name}. Lần quét tới sẽ quét lại toàn bộ kênh từ đầu!",
    }


@router.post("/crawler/douyin-cookie")
def save_douyin_cookie(req: SaveDouyinCookieRequest) -> dict[str, Any]:
    """Nhận chuỗi cookie (JSON từ extension Cookie-Editor, Netscape, hoặc header string) và lưu vào hệ thống."""
    raw = req.cookie.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp chuỗi cookie hoặc JSON hợp lệ!")

    res = save_imported_cookies(raw)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message", "Không thể xử lý cookie"))

    return res


@router.post("/crawler/douyin-cookie-file")
async def save_douyin_cookie_file(file: UploadFile = File(...)) -> dict[str, Any]:
    """Nhận file cookie (.json hoặc .txt) được export từ trình duyệt (Cookie-Editor, J2Team...) và lưu vào hệ thống."""
    try:
        content_bytes = await file.read()
        raw_text = content_bytes.decode("utf-8", errors="ignore").strip()
        if not raw_text:
            raise HTTPException(status_code=400, detail="File cookie tải lên bị trống!")

        res = save_imported_cookies(raw_text)
        if not res.get("success"):
            raise HTTPException(status_code=400, detail=res.get("message", "Không thể xử lý file cookie"))

        return res
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi đọc file cookie: {e}")


@router.post("/crawler/douyin-login")
def douyin_login_open() -> dict[str, Any]:
    """Mở cửa sổ trình duyệt Edge độc lập trên Windows để người dùng quét mã QR đăng nhập Douyin."""
    import subprocess
    profile_dir = str(DOUYIN_PROFILE_DIR.resolve())

    try:
        # Khởi chạy Edge thật độc lập qua Windows cmd start để chắc chắn cửa sổ hiện trên màn hình desktop
        subprocess.Popen([
            "cmd", "/c", "start", "msedge",
            f"--user-data-dir={profile_dir}",
            "--new-window",
            "https://www.douyin.com/"
        ], shell=False)
    except Exception as e:
        print(f"[douyin_login_open] Lỗi mở Edge: {e}")
        return {
            "success": False,
            "message": f"Không thể khởi chạy Edge: {e}",
        }

    return {
        "success": True,
        "message": "Đã mở cửa sổ trình duyệt Edge trên màn hình máy tính của bạn. Hãy quét mã QR đăng nhập Douyin!",
    }


@router.post("/crawler/douyin-confirm")
def douyin_login_confirm() -> dict[str, Any]:
    """Xác nhận đăng nhập: Tự động đóng cửa sổ Edge quét QR (nếu còn mở) để giải phóng file SQLite và lưu cookie."""
    import subprocess, time

    # Đóng tiến trình msedge chạy douyin_profile để Edge giải phóng lock file Cookies SQLite
    ps_cmd = 'Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*douyin_profile*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }'
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, timeout=10)
    except Exception as e:
        print(f"[douyin_confirm] Lỗi đóng Edge: {e}")

    time.sleep(1.2)
    logged = is_douyin_logged_in()
    return {
        "success": logged,
        "logged_in": logged,
        "message": "🎉 Đăng nhập Douyin thành công! Cửa sổ Edge đã lưu phiên duyệt và hệ thống đã sẵn sàng cào toàn bộ video." if logged else "Chưa ghi nhận đăng nhập trên Douyin. Vui lòng quét mã QR trên Edge hoặc dán chuỗi cookie!",
    }


@router.post("/clear-thumbnails")
def clear_thumbnails(req: ClearThumbnailsRequest) -> dict[str, Any]:
    """Xóa tất cả các thumbnail và video đang ở trạng thái chờ tải ('discovered')."""
    init_db()
    deleted_rows = delete_discovered_videos(req.account_id)
    for row in deleted_rows:
        cleanup_thumbnail_file(
            thumbnail_url=row.get("thumbnail_url") or "",
            platform=row.get("platform") or "",
            vid_id=str(row.get("platform_video_id") or ""),
        )

    # Nếu xóa tất cả, cũng quét dọn thư mục output/thumbnails
    if not req.account_id or req.account_id == "all":
        thumb_dir = OUTPUT_DIR / "thumbnails"
        if thumb_dir.exists():
            for f in thumb_dir.glob("*.jpg"):
                try:
                    f.unlink(missing_ok=True)
                except Exception:
                    pass

    return {
        "success": True,
        "deleted_count": len(deleted_rows),
        "message": f"Đã xóa thành công {len(deleted_rows)} thumbnail video đang chờ tải!",
    }


@router.post("/delete-item")
def delete_video_item_endpoint(req: DeleteVideoRequest) -> dict[str, Any]:
    """Xóa một video: Xóa thumbnail, bản ghi trong DB và tùy chọn xóa file MP4 nếu có."""
    init_db()

    if req.video_id:
        deleted_info = delete_video_by_id(req.video_id)
        if deleted_info:
            cleanup_thumbnail_file(
                thumbnail_url=deleted_info.get("thumbnail_url") or "",
                platform=deleted_info.get("platform") or "",
                vid_id=str(deleted_info.get("platform_video_id") or ""),
            )
            if req.delete_file and deleted_info.get("raw_video_path"):
                p = Path(deleted_info["raw_video_path"])
                if p.exists() and p.is_file():
                    try:
                        p.unlink(missing_ok=True)
                    except Exception as e:
                        print(f"[delete_video_item] Không thể xóa file mp4: {e}")

    if req.path and req.delete_file:
        p = Path(req.path)
        if p.exists() and p.is_file():
            try:
                p.unlink(missing_ok=True)
            except Exception as e:
                print(f"[delete_video_item] Không thể xóa file path: {e}")

    return {
        "success": True,
        "message": "Đã xóa thumbnail và bản ghi video thành công!",
    }


@router.post("/download-discovered", response_model=VideoItemResponse)
def download_discovered(req: DownloadDiscoveredRequest) -> VideoItemResponse:
    """Tải file video vật lý về máy khi người dùng quyết định tải một video đã quét metadata."""
    init_db()
    video_row = get_video_by_id(req.video_id)
    if not video_row:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy video với ID {req.video_id}")

    # Chống tải trùng: Nếu video đã có file mp4 sẵn trên đĩa thì trả về ngay lập tức
    if video_row.get("download_status") == "downloaded" and video_row.get("raw_video_path"):
        raw_p = Path(video_row["raw_video_path"])
        if raw_p.exists() and raw_p.is_file() and raw_p.stat().st_size > 1024 * 50:
            stat = raw_p.stat()
            size_mb = round(stat.st_size / (1024 * 1024), 2)
            name_lower = raw_p.name.lower()
            suggest_remix = any(k in name_lower for k in ["dance", "remix", "music", "beat", "trend"])
            return VideoItemResponse(
                id=video_row["id"],
                filename=raw_p.name,
                path=str(raw_p.resolve()),
                subfolder=raw_p.parent.name,
                size_mb=size_mb,
                duration_str=format_duration(video_row.get("duration", 0)),
                has_sub=not suggest_remix,
                suggest_remix=suggest_remix,
                status="inbox",
                source_type="downloaded",
                thumbnail_url=video_row.get("thumbnail_url"),
                video_url=video_row.get("video_url"),
                download_status="downloaded",
                platform=video_row.get("platform"),
                platform_video_id=video_row.get("platform_video_id"),
                account_id=video_row.get("account_id"),
                published_at=video_row.get("published_at"),
                is_pinned=int(video_row.get("is_pinned") or 0),
            )

    manager = DownloadManager()
    try:
        dest_file = manager.download_discovered_video(video_row)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi tải video: {e}")

    stat = dest_file.stat()
    size_mb = round(stat.st_size / (1024 * 1024), 2)
    name_lower = dest_file.name.lower()
    suggest_remix = any(k in name_lower for k in ["dance", "remix", "music", "beat", "trend"])

    return VideoItemResponse(
        id=video_row["id"],
        filename=dest_file.name,
        path=str(dest_file.resolve()),
        subfolder=dest_file.parent.name,
        size_mb=size_mb,
        duration_str=format_duration(video_row.get("duration", 0)),
        has_sub=not suggest_remix,
        suggest_remix=suggest_remix,
        status="inbox",
        source_type="downloaded",
        thumbnail_url=video_row.get("thumbnail_url"),
        video_url=video_row.get("video_url"),
        download_status="downloaded",
        platform=video_row.get("platform"),
        platform_video_id=video_row.get("platform_video_id"),
        account_id=video_row.get("account_id"),
        published_at=video_row.get("published_at"),
        is_pinned=int(video_row.get("is_pinned") or 0),
    )


@router.post("/quick-download")
def quick_download(req: QuickDownloadRequest) -> dict[str, Any]:
    """Tải một video đơn lẻ từ link Douyin / TikTok / YouTube / Bilibili / Facebook về subfolder."""
    download_root = get_download_root()
    subfolder_dir = download_root / req.subfolder
    subfolder_dir.mkdir(parents=True, exist_ok=True)

    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp link video hợp lệ!")

    import time
    safe_base = f"video_{int(time.time())}"
    dest_file = subfolder_dir / f"{safe_base}.mp4"

    downloaded_file: Path | None = None
    try:
        if "douyin.com" in url:
            # 1. Douyin
            try:
                dy = DouyinDownloader()
                downloaded_file = dy.download_single_video(url, dest_file)
            except Exception as e_dy:
                print(f"[videos quick-download] Douyin tải lỗi: {e_dy}")
                raise HTTPException(status_code=500, detail=f"Không thể tải video Douyin: {e_dy}")
        else:
            # 2. Đa nền tảng khác qua YtDlpEngine
            ytdlp = YtDlpEngine("generic")
            downloaded_file = ytdlp.download_video(url, dest_file)

        if downloaded_file and Path(downloaded_file).exists():
            final_p = Path(downloaded_file)
            stat = final_p.stat()
            size_mb = round(stat.st_size / (1024 * 1024), 2)
            name_lower = final_p.name.lower()
            suggest_remix = any(k in name_lower for k in ["dance", "remix", "music", "beat", "trend"])

            record_download(
                account_id=req.subfolder,
                platform="direct_url",
                platform_video_id=final_p.stem,
                title=final_p.name,
                raw_video_path=str(final_p.resolve()),
                processed_status="inbox",
            )

            video_item = {
                "filename": final_p.name,
                "path": str(final_p.resolve()),
                "subfolder": req.subfolder,
                "size_mb": size_mb,
                "duration_str": "00:15",
                "has_sub": not suggest_remix,
                "suggest_remix": suggest_remix,
                "status": "inbox",
                "source_type": "downloaded",
            }
            return {
                "success": True,
                "message": f"✓ Đã tải xong video: {final_p.name}",
                "video": video_item,
            }
        else:
            raise RuntimeError("Không tìm thấy file sau khi tải xong.")
    except Exception as e:
        print(f"[videos quick-download] Lỗi tải video: {e}")
        raise HTTPException(status_code=500, detail=f"Không thể tải video từ link: {e}")
