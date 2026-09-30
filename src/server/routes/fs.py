"""Endpoints quản lý hệ thống file, duyệt thư mục và gọi Windows Explorer."""

from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from ...config import OUTPUT_DIR
from ...downloader.settings import load_settings, save_settings
from ..fs_provider import (
    browse_directory,
    get_windows_drives,
    open_in_windows_explorer,
    open_native_folder_picker,
)
from ..models import (
    BrowseFolderResponse,
    DriveInfo,
    OpenFolderRequest,
    PathConfigRequest,
    PathConfigResponse,
)

router = APIRouter(prefix="/fs", tags=["File System"])


@router.get("/drives", response_model=list[DriveInfo])
def get_drives() -> list[DriveInfo]:
    """Lấy danh sách các ổ đĩa trên máy tính Windows (C:, D:, E:, F:)."""
    return get_windows_drives()


@router.get("/browse", response_model=BrowseFolderResponse)
def browse(path: str = Query(..., description="Đường dẫn thư mục cần duyệt")) -> BrowseFolderResponse:
    """Duyệt danh sách các thư mục con và đếm số lượng video trong từng thư mục."""
    try:
        return browse_directory(path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi duyệt thư mục: {e}")


@router.get("/file")
def get_local_file(path: str = Query(..., description="Đường dẫn file trên máy tính")):
    """Phục vụ file tĩnh trên hệ thống file nội bộ."""
    clean_path = path.split("?")[0].strip('"\'')
    p = Path(clean_path)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy file: {clean_path}")
    return FileResponse(str(p))


@router.post("/open-folder")
def open_folder(req: OpenFolderRequest) -> dict[str, str | bool]:
    """Mở thư mục trong Windows Explorer của máy tính."""
    success = open_in_windows_explorer(req.path)
    if not success:
        raise HTTPException(status_code=500, detail="Không thể mở thư mục trong Windows Explorer")
    return {"success": True, "path": req.path}


@router.post("/native-picker")
def native_picker(initial_dir: str | None = None) -> dict[str, str | None]:
    """Mở hộp thoại chọn folder gốc của Windows Explorer (Tkinter dialog)."""
    selected = open_native_folder_picker(initial_dir)
    return {"selected_path": selected}


@router.get("/config", response_model=PathConfigResponse)
def get_path_config() -> PathConfigResponse:
    """Lấy đường dẫn thư mục tải về gốc (Cha) và thư mục xuất thành phẩm gốc (Cha)."""
    settings = load_settings()
    default_download = str((OUTPUT_DIR / "downloads").resolve())
    default_output = str((OUTPUT_DIR / "ready_to_upload").resolve())

    return PathConfigResponse(
        download_root_dir=settings.get("download_root_dir", default_download),
        output_root_dir=settings.get("output_root_dir", default_output),
    )


@router.post("/config", response_model=PathConfigResponse)
def update_path_config(req: PathConfigRequest) -> PathConfigResponse:
    """Cập nhật đường dẫn thư mục gốc tải về và xuất thành phẩm."""
    settings = load_settings()
    if req.download_root_dir:
        target_dir = Path(req.download_root_dir).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        settings["download_root_dir"] = str(target_dir)

    if req.output_root_dir:
        target_dir = Path(req.output_root_dir).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        settings["output_root_dir"] = str(target_dir)

    save_settings(settings)
    return get_path_config()
