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


def save_netscape_cookies(cookies: list[dict[str, Any]], file_path: Path) -> None:
    """Lưu danh sách cookie từ Playwright theo đúng định dạng chuẩn Netscape HTTP Cookie File."""
    lines = ["# Netscape HTTP Cookie File\n"]
    for c in cookies:
        domain = c.get("domain", "")
        flag = "TRUE" if domain.startswith(".") else "FALSE"
        path = c.get("path", "/")
        secure = "TRUE" if c.get("secure", False) else "FALSE"
        expires = int(c.get("expires", -1))
        if expires <= 0:
            expires = int(time.time()) + 86400 * 365
        name = c.get("name", "")
        value = c.get("value", "")
        lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}\n")
    file_path.write_text("".join(lines), encoding="utf-8")


def load_cookie_header(file_path: Path) -> str:
    """Đọc file cookie (dù là Netscape hay chuỗi raw) thành Header Cookie dạng name=val; name2=val2."""
    if not file_path.exists() or file_path.stat().st_size == 0:
        return ""
    content = file_path.read_text(encoding="utf-8", errors="ignore").strip()
    if content.startswith("# Netscape") or "\t" in content:
        parts = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            cols = line.split("\t")
            if len(cols) >= 7:
                parts.append(f"{cols[5]}={cols[6]}")
        return "; ".join(parts)
    return content


class DouyinDownloader:
    """Tải video Douyin không watermark kết hợp Browser Context Hooking để vượt WAF."""

    def __init__(self, cookies: str | None = None) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": DOUYIN_PC_UA})
        if cookies:
            self.session.headers.update({"Cookie": cookies})
        elif DOUYIN_COOKIE_FILE.exists() and DOUYIN_COOKIE_FILE.stat().st_size > 0:
            saved_cookie = load_cookie_header(DOUYIN_COOKIE_FILE)
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
        """Dùng Headless Browser (Edge/Chrome) với cơ chế Stealth để vượt qua WAF và bắt gói tin /aweme/post/."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return []

        captured_videos: list[dict[str, Any]] = []

        def handle_response(response: Any) -> None:
            url = response.url
            if "aweme/post" in url and response.status == 200:
                try:
                    data = response.json()
                    aweme_list = data.get("aweme_list", [])
                    for item in aweme_list:
                        vid_id = item.get("aweme_id")
                        desc = item.get("desc") or f"Douyin_{vid_id}"
                        video_info = item.get("video", {})
                        # Ưu tiên luồng h264 chất lượng cao không watermark
                        url_list = (
                            video_info.get("play_addr_h264", {}).get("url_list")
                            or video_info.get("play_addr", {}).get("url_list")
                            or []
                        )
                        clean_url = None
                        if url_list:
                            clean_url = url_list[0].replace("playwm", "play")

                        if vid_id and clean_url:
                            if not any(v["id"] == str(vid_id) for v in captured_videos):
                                captured_videos.append(
                                    {
                                        "id": str(vid_id),
                                        "title": desc.strip().replace("\n", " "),
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
                launch_args = [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                ]
                for channel in ["msedge", "chrome", None]:
                    try:
                        if channel:
                            browser = p.chromium.launch(channel=channel, headless=True, args=launch_args)
                        else:
                            browser = p.chromium.launch(headless=True, args=launch_args)
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
                # Stealth injection để vượt qua kiểm tra webdriver của Douyin
                context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

                page = context.new_page()
                page.on("response", handle_response)

                try:
                    page.goto(user_url, wait_until="domcontentloaded", timeout=25000)
                except Exception:
                    pass

                # Chờ tải ban đầu và cuộn trang để kích hoạt API load video
                page.wait_for_timeout(2000)
                for _ in range(8):
                    if len(captured_videos) >= max_count:
                        break
                    page.mouse.wheel(0, 700)
                    page.wait_for_timeout(1000)

                # Fallback từ DOM nếu gói tin API bị trôi
                if not captured_videos:
                    try:
                        dom_links = page.evaluate(
                            "() => Array.from(document.querySelectorAll('a[href*=\"/video/\"]')).map(a => ({href: a.href, text: a.innerText}))"
                        )
                        for item in dom_links:
                            m = re.search(r"/video/(\d+)", item.get("href", ""))
                            if m:
                                vid_id = m.group(1)
                                if not any(v["id"] == vid_id for v in captured_videos):
                                    captured_videos.append(
                                        {
                                            "id": str(vid_id),
                                            "title": (item.get("text", "") or f"Douyin_{vid_id}").strip().replace("\n", " ")[:80],
                                            "url": f"https://www.douyin.com/video/{vid_id}",
                                            "play_url": None,
                                            "cover": "",
                                            "duration": 0.0,
                                        }
                                    )
                    except Exception:
                        pass

                # Lưu cookies phiên duyệt theo chuẩn Netscape để dùng cho cả requests và yt-dlp
                try:
                    cookies = context.cookies()
                    if cookies:
                        save_netscape_cookies(cookies, DOUYIN_COOKIE_FILE)
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
