"""Module cung cấp tiện ích File System, quét ổ đĩa và thư mục trên Windows."""

from __future__ import annotations

import os
import shutil
import string
import subprocess
from pathlib import Path
from typing import Any

from ..config import SUPPORTED_VIDEO_EXT


def get_windows_drives() -> list[dict[str, Any]]:
    """Phát hiện và lấy thông tin dung lượng các ổ đĩa trên máy tính Windows (C:, D:, E:, ...)."""
    drives = []
    drive_names = {
        "C": "Ổ C: [Hệ Thống]",
        "D": "Ổ D: [Dữ Liệu & Code]",
        "E": "Ổ E: [Kho Video Thô]",
        "F": "Ổ F: [SSD Rời Di Động]",
    }

    for letter in string.ascii_uppercase:
        drive_path = f"{letter}:\\"
        if os.path.exists(drive_path):
            try:
                usage = shutil.disk_usage(drive_path)
                total_gb = round(usage.total / (1024**3), 1)
                free_gb = round(usage.free / (1024**3), 1)
                name = drive_names.get(letter, f"Ổ {letter}: [Đĩa Cục Bộ]")
                drives.append({
                    "letter": letter,
                    "path": drive_path,
                    "name": name,
                    "total_gb": total_gb,
                    "free_gb": free_gb,
                })
            except Exception:
                pass
    return drives


def count_video_files(dir_path: Path) -> int:
    """Đếm số file video hợp lệ trong thư mục (không đệ quy, chạy siêu tốc)."""
    try:
        count = 0
        with os.scandir(str(dir_path)) as entries:
            for entry in entries:
                if entry.is_file():
                    _, ext = os.path.splitext(entry.name)
                    if ext.lower() in SUPPORTED_VIDEO_EXT:
                        count += 1
        return count
    except Exception:
        return 0


def browse_directory(path_str: str) -> dict[str, Any]:
    """Duyệt danh sách các thư mục con trong một đường dẫn chỉ định."""
    target_path = Path(path_str).resolve()
    if not target_path.exists() or not target_path.is_dir():
        raise FileNotFoundError(f"Thư mục không tồn tại: {path_str}")

    folders = []
    try:
        with os.scandir(str(target_path)) as entries:
            for entry in entries:
                try:
                    if entry.is_dir():
                        # Bỏ qua các thư mục ẩn hệ thống
                        if entry.name.startswith((".", "$")):
                            continue
                        sub_path = Path(entry.path)
                        video_count = count_video_files(sub_path)
                        has_children = False
                        try:
                            with os.scandir(entry.path) as sub_entries:
                                has_children = any(e.is_dir() for e in sub_entries)
                        except Exception:
                            pass

                        folders.append({
                            "name": entry.name,
                            "path": str(sub_path),
                            "video_count": video_count,
                            "has_subfolders": has_children,
                        })
                except Exception:
                    continue
    except PermissionError:
        pass

    # Sắp xếp thư mục theo tên A-Z
    folders.sort(key=lambda x: x["name"].lower())

    parent_path = str(target_path.parent) if target_path.parent != target_path else None

    return {
        "path": str(target_path),
        "parent": parent_path,
        "folders": folders,
        "total_folders": len(folders),
    }


def open_in_windows_explorer(path_str: str) -> bool:
    """Mở thư mục trực tiếp trong Windows Explorer của hệ điều hành."""
    target_path = Path(path_str).resolve()
    if not target_path.exists():
        # Nếu thư mục chưa có thì cố gắng tạo
        target_path.mkdir(parents=True, exist_ok=True)

    try:
        if os.name == "nt":
            os.startfile(str(target_path))
            return True
        else:
            subprocess.Popen(["xdg-open", str(target_path)])
            return True
    except Exception as e:
        print(f"[fs_provider] Lỗi mở Explorer: {e}")
        return False


def open_native_folder_picker(initial_dir: str | None = None) -> str | None:
    """Mở hộp thoại Browse For Folder native của Windows bằng Tkinter."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        init_path = initial_dir if (initial_dir and Path(initial_dir).exists()) else "D:\\"
        selected = filedialog.askdirectory(initialdir=init_path, title="Chọn thư mục chứa video")
        root.destroy()
        return str(Path(selected).resolve()) if selected else None
    except Exception as e:
        print(f"[fs_provider] Lỗi gọi native dialog: {e}")
        return None


def scan_local_videos_recursive(folder_path: str) -> list[dict[str, Any]]:
    """Quét đệ quy toàn bộ file video trong thư mục máy tính."""
    root_dir = Path(folder_path).resolve()
    if not root_dir.exists() or not root_dir.is_dir():
        return []

    videos = []
    for item in root_dir.rglob("*"):
        if item.is_file() and item.suffix.lower() in SUPPORTED_VIDEO_EXT:
            try:
                stat = item.stat()
                videos.append({
                    "filename": item.name,
                    "rel_path": str(item.relative_to(root_dir)),
                    "full_path": str(item),
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "modified_at": stat.st_mtime,
                })
            except Exception:
                continue

    videos.sort(key=lambda x: x["filename"].lower())
    return videos
