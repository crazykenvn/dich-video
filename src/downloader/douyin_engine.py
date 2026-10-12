"""Module tải video Douyin không logo (Watermark-Free) từ trang cá nhân hoặc link chia sẻ."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import requests

from ..config import PROJECT_ROOT

COOKIES_DIR = PROJECT_ROOT / "cookies"
COOKIES_DIR.mkdir(parents=True, exist_ok=True)
DOUYIN_COOKIE_FILE = COOKIES_DIR / "douyin_cookies.txt"
DOUYIN_PROFILE_DIR = COOKIES_DIR / "douyin_profile"
DOUYIN_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

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


DOUYIN_LOGIN_INDICATORS = [
    "sessionid",
    "sid_guard",
    "sessionid_ss",
    "uid_tt",
    "uid_tt_ss",
    "passport_assist_user",
    "login_time",
    "FOLLOW_LIVE_POINT_INFO",
    "FOLLOW_NUMBER_YELLOW_POINT_INFO",
]


def is_douyin_logged_in() -> bool:
    """Kiểm tra nhanh xem phiên duyệt Douyin trong cookies/douyin_cookies.txt hoặc cookies/douyin_profile đã đăng nhập hay chưa."""
    # 1. Kiểm tra file cookies/douyin_cookies.txt
    if DOUYIN_COOKIE_FILE.exists() and DOUYIN_COOKIE_FILE.stat().st_size > 0:
        try:
            content = DOUYIN_COOKIE_FILE.read_text(encoding="utf-8", errors="ignore")
            if any(k in content for k in DOUYIN_LOGIN_INDICATORS):
                return True
        except Exception:
            pass

    # 2. Kiểm tra SQLite cookie trong cookies/douyin_profile
    import sqlite3, shutil, tempfile
    profile_dir = COOKIES_DIR / "douyin_profile"
    cookie_db = profile_dir / "Default" / "Network" / "Cookies"
    if not cookie_db.exists():
        return False
    try:
        tmp = Path(tempfile.gettempdir()) / f"dy_check_cookies_{int(time.time())}.db"
        shutil.copy2(cookie_db, tmp)
        c = sqlite3.connect(tmp)
        names = [r[0] for r in c.execute("SELECT name FROM cookies").fetchall()]
        c.close()
        tmp.unlink(missing_ok=True)
        return any(n in DOUYIN_LOGIN_INDICATORS for n in names)
    except Exception:
        return False


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

    def get_user_videos(
        self,
        sec_uid_or_url: str,
        max_count: int | None = None,
        stop_after_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Lấy danh sách video của tài khoản Douyin qua sec_uid.
        - max_count=None: Quét toàn bộ video của kênh (lần đầu quét).
        - stop_after_id: Dừng quét ngay khi gặp mốc video ID của lần quét trước (lần 2 quét trở đi).
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
        videos = self._get_videos_via_browser(full_user_url, max_count=max_count, stop_after_id=stop_after_id)
        if videos:
            return videos

        # 2. Fallback dùng requests nếu browser không khả dụng
        return self._get_videos_via_requests(sec_uid, max_count=max_count, stop_after_id=stop_after_id)

    def _get_videos_via_browser(
        self,
        user_url: str,
        max_count: int | None = None,
        stop_after_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Dùng Headless Browser (Edge/Chrome) với cơ chế Stealth để vượt qua WAF và bắt gói tin /aweme/post/."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return []

        captured_videos: list[dict[str, Any]] = []
        hit_stop_id = False

        def handle_response(response: Any) -> None:
            nonlocal hit_stop_id
            if hit_stop_id:
                return
            url = response.url
            if "aweme/post" in url and response.status == 200:
                try:
                    data = response.json()
                    aweme_list = data.get("aweme_list", [])
                    has_more = data.get("has_more")
                    if has_more == 0 and not aweme_list:
                        hit_stop_id = True
                    for item in aweme_list:
                        vid_id = str(item.get("aweme_id"))
                        is_top = 1 if (item.get("is_top") == 1 or item.get("tag", {}).get("is_top") == 1 or bool(item.get("label_top"))) else 0

                        # Không dừng nếu gặp video ghim ở đầu trang
                        if stop_after_id and vid_id == str(stop_after_id) and not is_top:
                            hit_stop_id = True
                            break

                        desc = item.get("desc") or f"Douyin_{vid_id}"
                        video_info = item.get("video", {})
                        url_list = (
                            video_info.get("play_addr_h264", {}).get("url_list")
                            or video_info.get("play_addr", {}).get("url_list")
                            or []
                        )
                        clean_url = None
                        if url_list:
                            clean_url = url_list[0].replace("playwm", "play")

                        cover = (
                            video_info.get("cover", {}).get("url_list", [""])[0]
                            or video_info.get("origin_cover", {}).get("url_list", [""])[0]
                        )

                        create_time = item.get("create_time")
                        if not create_time and vid_id.isdigit():
                            try:
                                create_time = int(vid_id) >> 32
                            except Exception:
                                pass

                        published_at = None
                        if create_time:
                            try:
                                published_at = datetime.fromtimestamp(int(create_time), tz=timezone.utc).isoformat()
                            except Exception:
                                pass

                        if vid_id and clean_url:
                            if not any(v["id"] == vid_id for v in captured_videos):
                                captured_videos.append(
                                    {
                                        "id": vid_id,
                                        "title": desc.strip().replace("\n", " "),
                                        "url": f"https://www.douyin.com/video/{vid_id}",
                                        "play_url": clean_url,
                                        "cover": cover,
                                        "thumbnail": cover,
                                        "duration": item.get("duration", 0) / 1000.0,
                                        "published_at": published_at,
                                        "is_pinned": is_top,
                                    }
                                )
                except Exception:
                    pass


        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                context = None
                launch_args = [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                ]
                for channel in ["msedge", "chrome", None]:
                    try:
                        context = p.chromium.launch_persistent_context(
                            user_data_dir=str(DOUYIN_PROFILE_DIR),
                            channel=channel,
                            headless=True,
                            args=launch_args,
                            user_agent=DOUYIN_PC_UA,
                            viewport={"width": 1280, "height": 800},
                            locale="zh-CN",
                        )
                        break
                    except Exception:
                        continue

                if not context:
                    return []

                context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
                
                # Nạp thêm cookie từ file cookies/douyin_cookies.txt nếu có
                try:
                    cookie_str = load_cookie_header(DOUYIN_COOKIE_FILE)
                    if cookie_str:
                        cookies_to_add = []
                        for part in cookie_str.split(";"):
                            if "=" in part:
                                k, v = part.strip().split("=", 1)
                                if k.strip():
                                    cookies_to_add.append({
                                        "name": k.strip(),
                                        "value": v.strip(),
                                        "domain": ".douyin.com",
                                        "path": "/",
                                    })
                        if cookies_to_add:
                            context.add_cookies(cookies_to_add)
                except Exception:
                    pass

                page = context.pages[0] if context.pages else context.new_page()
                page.on("response", handle_response)

                try:
                    page.goto(user_url, wait_until="domcontentloaded", timeout=25000)
                except Exception:
                    pass

                page.wait_for_timeout(2000)

                # Tự động đóng modal đăng nhập nếu có
                try:
                    page.keyboard.press("Escape")
                    page.evaluate('''() => {
                        document.querySelectorAll('div[role="dialog"], [class*="login-mask"], [class*="login-guide"], [class*="modal-mask"]').forEach(el => el.remove());
                        document.body.style.overflow = "auto";
                        document.documentElement.style.overflow = "auto";
                    }''')
                except Exception:
                    pass

                scroll_limit = 350 if (max_count is None or max_count > 50) else 30
                prev_count = 0
                no_growth_ticks = 0
                for _ in range(scroll_limit):
                    if hit_stop_id:
                        break
                    if max_count and len(captured_videos) >= max_count:
                        break
                    curr_count = len(captured_videos)
                    if curr_count > 0 and curr_count == prev_count:
                        no_growth_ticks += 1
                        if no_growth_ticks >= 8:
                            # Đã cuộn 8 lần (~18 giây) không có thêm video -> kênh đã hết
                            break
                    else:
                        no_growth_ticks = 0
                    prev_count = curr_count

                    # 1. Cuộn mượt container nội dung video chính của Douyin (.parent-route-container)
                    try:
                        page.evaluate('''() => {
                            const c = document.querySelector('.parent-route-container') ||
                                      document.querySelector('[class*="parent-route"]') ||
                                      document.querySelector('[class*="route-scroll"]');
                            if (c) {
                                c.scrollBy({ top: 1200, behavior: 'smooth' });
                            }
                        }''')
                    except Exception:
                        pass

                    # 2. Hover và lăn chuột thực tế trong vùng nội dung (tránh kẹt ở sidebar cố định bên trái)
                    try:
                        loc = page.locator('.parent-route-container')
                        if loc.count() > 0:
                            loc.hover()
                            page.mouse.wheel(0, 1200)
                        else:
                            page.mouse.move(700, 500)
                            page.mouse.wheel(0, 1200)
                    except Exception:
                        pass

                    # 3. Phím PageDown bổ trợ
                    try:
                        page.keyboard.press("PageDown")
                    except Exception:
                        pass

                    # 4. Delay an toàn giữa các lần cuộn (2.2s) để tránh kích hoạt anti-spam WAF và đợi API trả về
                    page.wait_for_timeout(2200)

                # Lưu cookies phiên duyệt (chỉ lưu nếu có chứa cookie đăng nhập để không đè mất cookie người dùng dán)
                try:
                    cookies = context.cookies()
                    if cookies and any(c.get("name") in ["sessionid", "sid_guard", "sessionid_ss", "uid_tt"] for c in cookies):
                        save_netscape_cookies(cookies, DOUYIN_COOKIE_FILE)
                except Exception:
                    pass

                context.close()
        except Exception as e:
            print(f"[DouyinDownloader] Lỗi Playwright: {e}")

        return captured_videos if max_count is None else captured_videos[:max_count]

    def _get_videos_via_requests(
        self,
        sec_uid: str,
        max_count: int | None = None,
        stop_after_id: str | None = None,
    ) -> list[dict[str, Any]]:
        api_url = "https://www.douyin.com/aweme/v1/web/aweme/post/"
        headers = {
            "User-Agent": DOUYIN_PC_UA,
            "Referer": f"https://www.douyin.com/user/{sec_uid}",
        }

        videos = []
        cursor = 0
        has_more = True
        limit_count = max_count or 1000

        while has_more and len(videos) < limit_count:
            batch_count = min(30, limit_count - len(videos))
            params = {
                "sec_user_id": sec_uid,
                "count": batch_count,
                "max_cursor": cursor,
                "device_platform": "webapp",
                "aid": "6383",
            }
            try:
                resp = self.session.get(api_url, params=params, headers=headers, timeout=15)
                if resp.status_code != 200 or not resp.text.strip():
                    break
                data = resp.json()
                aweme_list = data.get("aweme_list", [])
                if not aweme_list:
                    break

                for item in aweme_list:
                    aweme_id = str(item.get("aweme_id"))
                    is_top = 1 if (item.get("is_top") == 1 or item.get("tag", {}).get("is_top") == 1 or bool(item.get("label_top"))) else 0

                    if stop_after_id and aweme_id == str(stop_after_id) and not is_top:
                        has_more = False
                        break

                    desc = item.get("desc", f"Douyin_{aweme_id}")
                    video_info = item.get("video", {})
                    play_addr = video_info.get("play_addr", {})
                    url_list = play_addr.get("url_list", [])
                    clean_play_url = url_list[0].replace("playwm", "play") if url_list else None

                    cover = (
                        video_info.get("cover", {}).get("url_list", [""])[0]
                        or video_info.get("origin_cover", {}).get("url_list", [""])[0]
                    )

                    create_time = item.get("create_time")
                    if not create_time and aweme_id.isdigit():
                        try:
                            create_time = int(aweme_id) >> 32
                        except Exception:
                            pass

                    published_at = None
                    if create_time:
                        try:
                            published_at = datetime.fromtimestamp(int(create_time), tz=timezone.utc).isoformat()
                        except Exception:
                            pass

                    if aweme_id and clean_play_url:
                        videos.append(
                            {
                                "id": aweme_id,
                                "title": desc,
                                "url": f"https://www.douyin.com/video/{aweme_id}",
                                "play_url": clean_play_url,
                                "cover": cover,
                                "thumbnail": cover,
                                "duration": item.get("duration", 0) / 1000.0,
                                "published_at": published_at,
                                "is_pinned": is_top,
                            }
                        )
                        if len(videos) >= limit_count:
                            has_more = False
                            break

                cursor = data.get("max_cursor", 0)
                has_more = has_more and bool(data.get("has_more", 0)) and cursor != 0
            except Exception:
                break

        return videos

    def download_clean_video(self, play_url: str, output_file: Path) -> Path:
        """Tải video sạch không logo từ play_url."""
        output_file.parent.mkdir(parents=True, exist_ok=True)
        headers = {
            "User-Agent": DOUYIN_PC_UA,
            "Referer": "https://www.douyin.com/",
            "Accept": "*/*",
            "Accept-Encoding": "identity;q=1, *;q=0",
        }
        # Lưu ý: Tuyệt đối KHÔNG gửi kèm Cookie phiên của douyin.com tới máy chủ CDN (zjcdn/douyinvod)
        # vì dung lượng cookie quá lớn (>16KB) sẽ khiến CDN trả về lỗi HTTP 400 Bad Request.
        # CDN token đã được mã hóa đầy đủ trong URL query params.
        tmp_file = output_file.with_suffix(".tmp.mp4")
        try:
            with requests.get(play_url, headers=headers, stream=True, timeout=60) as res:
                if res.status_code not in (200, 206):
                    headers["User-Agent"] = DOUYIN_MOBILE_UA
                    with requests.get(play_url, headers=headers, stream=True, timeout=60) as res2:
                        res2.raise_for_status()
                        with open(tmp_file, "wb") as f:
                            for chunk in res2.iter_content(chunk_size=1024 * 128):
                                if chunk:
                                    f.write(chunk)
                else:
                    with open(tmp_file, "wb") as f:
                        for chunk in res.iter_content(chunk_size=1024 * 128):
                            if chunk:
                                f.write(chunk)

            if tmp_file.exists() and tmp_file.stat().st_size > 1024 * 50:
                tmp_file.replace(output_file)
                return output_file
        except Exception:
            tmp_file.unlink(missing_ok=True)
            raise

        tmp_file.unlink(missing_ok=True)
        raise RuntimeError(f"File video tải về không hợp lệ hoặc quá nhỏ: {output_file.name}")

    def download_single_video(
        self,
        video_url_or_id: str,
        output_file: Path,
        play_url: str | None = None,
    ) -> Path:
        """Tải một video Douyin hoàn chỉnh sạch không watermark.
        1. Thử tải ngay qua play_url (nếu có sẵn từ lúc scan).
        2. Nếu không có hoặc play_url hết hạn: Dùng Playwright với Context đăng nhập bắt gói aweme/detail để lấy play_url mới nhất rồi tải.
        """
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # 1. Thử tải qua play_url trực tiếp (nhanh nhất)
        if play_url:
            try:
                self.download_clean_video(play_url, output_file)
                if output_file.exists() and output_file.stat().st_size > 1024 * 50:
                    return output_file
            except Exception as e:
                print(f"[DouyinDownloader] Tải qua play_url có sẵn thất bại: {e}, chuyển sang lấy play_url mới...")

        # 2. Trích xuất aweme_id từ video_url_or_id
        vid_id = None
        match = re.search(r"video/(\d+)", video_url_or_id)
        if match:
            vid_id = match.group(1)
        elif video_url_or_id.isdigit():
            vid_id = video_url_or_id
        elif "v.douyin.com" in video_url_or_id:
            try:
                resolved = self.resolve_share_url(video_url_or_id)
                m2 = re.search(r"video/(\d+)", resolved)
                if m2:
                    vid_id = m2.group(1)
            except Exception:
                pass

        if not vid_id:
            raise ValueError(f"Không thể nhận diện Video ID từ: {video_url_or_id}")

        page_url = f"https://www.douyin.com/video/{vid_id}"

        # 3. Dùng Playwright với Persistent Context đã đăng nhập để bắt gói aweme/detail
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                context = None
                launch_args = [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                ]
                for channel in ["msedge", "chrome", None]:
                    try:
                        context = p.chromium.launch_persistent_context(
                            user_data_dir=str(DOUYIN_PROFILE_DIR),
                            channel=channel,
                            headless=True,
                            args=launch_args,
                            user_agent=DOUYIN_PC_UA,
                            viewport={"width": 1280, "height": 800},
                            locale="zh-CN",
                        )
                        break
                    except Exception:
                        continue

                if not context:
                    raise RuntimeError("Không thể khởi động trình duyệt để lấy link video")

                context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

                # Nạp thêm cookie từ file cookies/douyin_cookies.txt nếu có
                try:
                    cookie_str = load_cookie_header(DOUYIN_COOKIE_FILE)
                    if cookie_str:
                        cookies_to_add = []
                        for part in cookie_str.split(";"):
                            if "=" in part:
                                k, v = part.strip().split("=", 1)
                                if k.strip():
                                    cookies_to_add.append({
                                        "name": k.strip(),
                                        "value": v.strip(),
                                        "domain": ".douyin.com",
                                        "path": "/",
                                    })
                        if cookies_to_add:
                            context.add_cookies(cookies_to_add)
                except Exception:
                    pass

                page = context.pages[0] if context.pages else context.new_page()
                captured_play_url = None

                def handle_detail_resp(response: Any) -> None:
                    nonlocal captured_play_url
                    if ("aweme/detail" in response.url or "aweme/post" in response.url) and response.status == 200:
                        try:
                            d = response.json()
                            aweme_detail = d.get("aweme_detail") or (d.get("aweme_list", [{}])[0] if d.get("aweme_list") else {})
                            urls = (
                                aweme_detail.get("video", {}).get("play_addr_h264", {}).get("url_list")
                                or aweme_detail.get("video", {}).get("play_addr", {}).get("url_list")
                                or []
                            )
                            if urls:
                                captured_play_url = urls[0].replace("playwm", "play")
                        except Exception:
                            pass

                page.on("response", handle_detail_resp)

                try:
                    page.goto(page_url, wait_until="domcontentloaded", timeout=20000)
                except Exception:
                    pass

                page.wait_for_timeout(3500)
                context.close()

                if captured_play_url:
                    self.download_clean_video(captured_play_url, output_file)
                    if output_file.exists() and output_file.stat().st_size > 1024 * 50:
                        return output_file
        except Exception as e:
            print(f"[DouyinDownloader] Lỗi lấy video qua browser: {e}")

        if output_file.exists() and output_file.stat().st_size > 1024 * 50:
            return output_file
        raise RuntimeError(f"Không thể tải video Douyin ID {vid_id}")

