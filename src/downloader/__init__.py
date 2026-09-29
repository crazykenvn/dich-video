"""Module Downloader: Tự động tải video đa nền tảng (Facebook, Instagram, Douyin, TikTok, Bilibili)."""

from .db import (
    init_db,
    add_account,
    get_accounts,
    delete_account,
    update_account_status,
    is_video_downloaded,
    record_download,
    update_video_processing,
    get_recent_videos,
)
from .manager import DownloadManager

__all__ = [
    "init_db",
    "add_account",
    "get_accounts",
    "delete_account",
    "update_account_status",
    "is_video_downloaded",
    "record_download",
    "update_video_processing",
    "get_recent_videos",
    "DownloadManager",
]
