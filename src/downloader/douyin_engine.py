"""Module tải video Douyin không logo (Watermark-Free) từ trang cá nhân hoặc link chia sẻ."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any
import requests

from ..config import PROJECT_ROOT

COOKIES_DIR = PROJECT_ROOT / "cookies"
COOKIES_DIR.mkdir(parents=True, exist_ok=True)
DOUYIN_COOKIE_FILE = COOKIES_DIR / "douyin_cookies.txt"

DOUYIN_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
)

DOUYIN_PC_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


class DouyinDownloader:
    """Tải video Douyin không watermark kết hợp Browser Context Hooking để vượt WAF."""

    def __init__(self, cookies: str | None = None) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": DOUYIN_PC_UA})
        if cookies:
            self.session.headers.update({"Cookie": cookies})
        elif DOUYIN_COOKIE_FILE.exists() and DOUYIN_COOKIE_FILE.stat().st_size > 0:
            saved_cookie = DOUYIN_COOKIE_FILE.read_text(encoding="utf-8", errors="ignore").strip()
            if saved_cookie:
                self.session.headers.update({"Cookie": saved_cookie})

    def extract_sec_uid(self, url: str) -> str | None:
        """Trích xuất sec_uid từ URL trang cá nhân Douyin."""
        match = re.search(r"user/([a-zA-Z0-9_\-]+)", url)
        if match:
            return match.group(1)
        if url.startswith("MS4wLjABAAAA"):
            return url
        return None

    def resolve_share_url(self, share_url: str) -> str:
        """Theo dõi redirect từ link rút gọn v.douyin.com/..."""
        res = self.session.get(share_url, headers={"User-Agent": DOUYIN_MOBILE_UA}, allow_redirects=True)
        return res.url

    def get_user_videos(self, sec_uid_or_url: str, max_count: int = 15) -> list[dict[str, Any]]:
        """Lấy danh sách video mới nhất của tài khoản Douyin qua sec_uid.
        Áp dụng cơ chế Browser Hooking để giải mã chữ ký WAF và lấy link video sạch.
        """
        sec_uid = self.extract_sec_uid(sec_uid_or_url)
        if not sec_uid:
            if "v.douyin.com" in sec_uid_or_url:
                real_url = self.resolve_share_url(sec_uid_or_url)
                sec_uid = self.extract_sec_uid(real_url)

        if not sec_uid:
            return []

        full_user_url = f"https://www.douyin.com/user/{sec_uid}"

        # 1. Thử dùng Playwright Headless Edge/Chrome để bắt API tự nhiên
        videos = self._get_videos_via_browser(full_user_url, max_count=max_count)
        if videos:
            return videos

        # 2. Fallback dùng requests nếu browser không khả dụng
        return self._get_videos_via_requests(sec_uid, max_count=max_count)

    def _get_videos_via_browser(self, user_url: str, max_count: int = 15) -> list[dict[str, Any]]:
        """Dùng Headless Browser (Edge/Chrome) mở trang và bắt gói tin /aweme/post/."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return []

        captured_videos: list[dict[str, Any]] = []

        def handle_response(response: Any) -> None:
            url = response.url
            if "/aweme/v1/web/aweme/post/" in url:
                try:
                    data = response.json()
                    aweme_list = data.get("aweme_list", [])
                    for item in aweme_list:
                        vid_id = item.get("aweme_id")
                        desc = item.get("desc") or f"Douyin_{vid_id}"
                        video_info = item.get("video", {})
                        play_addr = video_info.get("play_addr", {})
                        url_list = play_addr.get("url_list", [])
                        clean_url = None
                        if url_list:
                            clean_url = url_list[0].replace("playwm", "play")

                        if vid_id and clean_url:
                            captured_videos.append(
                                {
                                    "id": str(vid_id),
                                    "title": desc,
                                    "url": f"https://www.douyin.com/video/{vid_id}",
                                    "play_url": clean_url,
                                    "cover": video_info.get("cover", {}).get("url_list", [""])[0],
                                    "duration": item.get("duration", 0) / 1000.0,
                                }
                            )
                except Exception:
                    pass

        try:
            with sync_playwright() as p:
                browser = None
                for channel in ["msedge", "chrome", None]:
                    try:
                        if channel:
                            browser = p.chromium.launch(channel=channel, headless=True)
                        else:
                            browser = p.chromium.launch(headless=True)
                        break
                    except Exception:
                        continue

                if not browser:
                    return []

                context = browser.new_context(
                    user_agent=DOUYIN_PC_UA,
                    viewport={"width": 1280, "height": 800},
                    locale="zh-CN",
                )
                page = context.new_page()
                page.on("response", handle_response)

                page.goto(user_url, wait_until="domcontentloaded", timeout=25000)

                # Chờ tối đa 8 giây để nhận API phản hồi
                for _ in range(8):
                    if captured_videos:
                        break
                    time.sleep(1)

                if not captured_videos:
                    page.mouse.wheel(0, 600)
                    time.sleep(2)

                # Lưu cookies để tái sử dụng
                try:
                    cookies = context.cookies()
                    cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
                    if cookie_str:
                        DOUYIN_COOKIE_FILE.write_text(cookie_str, encoding="utf-8")
                except Exception:
                    pass

                browser.close()
        except Exception as e:
            print(f"[DouyinDownloader] Lỗi Playwright: {e}")

        return captured_videos[:max_count]

    def _get_videos_via_requests(self, sec_uid: str, max_count: int = 15) -> list[dict[str, Any]]:
        api_url = "https://www.douyin.com/aweme/v1/web/aweme/post/"
        params = {
            "sec_user_id": sec_uid,
            "count": min(max_count, 30),
            "max_cursor": 0,
            "device_platform": "webapp",
            "aid": "6383",
        }
        headers = {
            "User-Agent": DOUYIN_PC_UA,
            "Referer": f"https://www.douyin.com/user/{sec_uid}",
        }

        videos = []
        try:
            resp = self.session.get(api_url, params=params, headers=headers, timeout=15)
            if resp.status_code == 200 and resp.text.strip():
                data = resp.json()
                aweme_list = data.get("aweme_list", [])
                for item in aweme_list[:max_count]:
                    aweme_id = item.get("aweme_id")
                    desc = item.get("desc", f"Douyin_{aweme_id}")
                    video_info = item.get("video", {})
                    play_addr = video_info.get("play_addr", {})
                    url_list = play_addr.get("url_list", [])
                    clean_play_url = url_list[0].replace("playwm", "play") if url_list else None

                    if aweme_id and clean_play_url:
                        videos.append(
                            {
                                "id": str(aweme_id),
                                "title": desc,
                                "url": f"https://www.douyin.com/video/{aweme_id}",
                                "play_url": clean_play_url,
                                "cover": video_info.get("cover", {}).get("url_list", [""])[0],
                                "duration": item.get("duration", 0) / 1000.0,
                            }
                        )
        except Exception:
            pass

        return videos

    def download_clean_video(self, play_url: str, output_file: Path) -> Path:
        """Tải video sạch không logo từ play_url."""
        output_file.parent.mkdir(parents=True, exist_ok=True)
        headers = {
            "User-Agent": DOUYIN_MOBILE_UA,
            "Referer": "https://www.douyin.com/",
        }
        res = self.session.get(play_url, headers=headers, stream=True, timeout=60)
        res.raise_for_status()

        tmp_file = output_file.with_suffix(".tmp.mp4")
        with open(tmp_file, "wb") as f:
            for chunk in res.iter_content(chunk_size=1024 * 64):
                if chunk:
                    f.write(chunk)

        tmp_file.replace(output_file)
        return output_file
