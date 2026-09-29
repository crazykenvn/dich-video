"""Module yt-dlp Engine: Động cơ tải vạn năng cho TikTok, Facebook, Instagram, YouTube, Bilibili."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..config import PROJECT_ROOT

COOKIES_DIR = PROJECT_ROOT / "cookies"
COOKIES_DIR.mkdir(parents=True, exist_ok=True)


def find_cookie_file(platform: str) -> Path | None:
    """Tìm file cookie tương ứng cho từng nền tảng nếu có."""
    candidates = [
        COOKIES_DIR / f"{platform.lower()}_cookies.txt",
        COOKIES_DIR / f"{platform.lower()}.txt",
        COOKIES_DIR / "cookies.txt",
    ]
    for c in candidates:
        if c.exists() and c.stat().st_size > 0:
            return c
    return None


class YtDlpEngine:
    """Trình bao bọc yt-dlp để cào danh sách video và tải về."""

    def __init__(self, platform: str = "generic") -> None:
        self.platform = platform.lower()
        self.cookie_file = find_cookie_file(self.platform)

    def is_available(self) -> bool:
        try:
            import yt_dlp  # noqa: F401
            return True
        except ImportError:
            return False

    def fetch_account_videos(self, account_url: str, max_count: int = 15) -> list[dict[str, Any]]:
        """Lấy danh sách video mới nhất từ URL tài khoản / kênh."""
        if not self.is_available():
            raise RuntimeError("Chưa cài đặt thư viện yt-dlp. Vui lòng chạy: pip install yt-dlp")

        import yt_dlp

        ydl_opts: dict[str, Any] = {
            "extract_flat": "in_playlist",
            "playlistend": max_count,
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
        }
        if self.cookie_file:
            ydl_opts["cookiefile"] = str(self.cookie_file)

        videos = []
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(account_url, download=False)
                if not info:
                    return []
                entries = info.get("entries") or [info]
                for item in entries:
                    if not item:
                        continue
                    vid_id = item.get("id") or item.get("url")
                    title = item.get("title") or f"{self.platform}_{vid_id}"
                    webpage_url = item.get("url")
                    if webpage_url and not webpage_url.startswith("http"):
                        # Xử lý ID thành link đầy đủ tùy nền tảng
                        if self.platform == "tiktok":
                            webpage_url = f"https://www.tiktok.com/video/{vid_id}"
                        elif self.platform == "bilibili":
                            webpage_url = f"https://www.bilibili.com/video/{vid_id}"
                        elif self.platform == "facebook":
                            webpage_url = f"https://www.facebook.com/watch/?v={vid_id}"
                        elif self.platform == "instagram":
                            webpage_url = f"https://www.instagram.com/p/{vid_id}/"

                    if vid_id and webpage_url:
                        videos.append(
                            {
                                "id": str(vid_id),
                                "title": title,
                                "url": webpage_url,
                                "duration": item.get("duration", 0),
                            }
                        )
            except Exception as e:
                print(f"[YtDlpEngine] Lỗi lấy danh sách video: {e}")

        return videos[:max_count]

    def download_video(self, video_url: str, output_file: Path) -> Path:
        """Tải một video đơn lẻ với chất lượng cao nhất MP4."""
        if not self.is_available():
            raise RuntimeError("Chưa cài đặt thư viện yt-dlp. Vui lòng chạy: pip install yt-dlp")

        import yt_dlp

        output_file.parent.mkdir(parents=True, exist_ok=True)
        outtmpl = str(output_file.with_suffix("")) + ".%(ext)s"

        ydl_opts: dict[str, Any] = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": outtmpl,
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
        }
        if self.cookie_file:
            ydl_opts["cookiefile"] = str(self.cookie_file)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        if output_file.exists():
            return output_file

        # Kiểm tra xem có file mp4 nào được sinh ra với cùng tên gốc không
        for ext in [".mp4", ".mkv", ".webm"]:
            alt = output_file.with_suffix(ext)
            if alt.exists():
                return alt

        raise RuntimeError(f"Tải video không thành công: {video_url}")
