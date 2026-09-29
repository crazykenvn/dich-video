"""Module chuyên dụng tải Bilibili hỗ trợ Wbi Signature & ghép luồng DASH (tham khảo Bili23-Downloader)."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
import urllib.parse
from functools import reduce
from pathlib import Path
from typing import Any
import requests

BILIBILI_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# Bảng mã hóa WBI của Bilibili
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
    26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
    20, 34, 44, 52
]


def get_mixin_key(orig: str) -> str:
    return reduce(lambda s, i: s + orig[i], MIXIN_KEY_ENC_TAB, "")[:32]


def enc_wbi(params: dict[str, Any], img_key: str, sub_key: str) -> dict[str, Any]:
    """Tạo chữ ký w_rid và wts theo chuẩn Wbi của Bilibili."""
    mixin_key = get_mixin_key(img_key + sub_key)
    curr_time = round(time.time())
    params["wts"] = curr_time
    params = dict(sorted(params.items()))
    # Lọc ký tự đặc biệt
    params = {
        k: "".join(filter(lambda chr: chr not in "!'()*", str(v)))
        for k, v in params.items()
    }
    query = urllib.parse.urlencode(params)
    wbi_sign = hashlib.md5((query + mixin_key).encode()).hexdigest()
    params["w_rid"] = wbi_sign
    return params


class BilibiliDownloader:
    """Tải video Bilibili chất lượng cao qua Wbi API và DASH."""

    def __init__(self, sessdata: str | None = None) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": BILIBILI_UA, "Referer": "https://www.bilibili.com/"})
        self.sessdata = sessdata
        if sessdata:
            self.session.cookies.set("SESSDATA", sessdata, domain=".bilibili.com")

    def get_wbi_keys(self) -> tuple[str, str]:
        """Lấy img_key và sub_key từ nav API."""
        try:
            resp = self.session.get("https://api.bilibili.com/x/web-interface/nav", timeout=10)
            data = resp.json().get("data", {})
            wbi_img = data.get("wbi_img", {})
            img_url = wbi_img.get("img_url", "")
            sub_url = wbi_img.get("sub_url", "")
            img_key = img_url.rsplit("/", 1)[1].split(".")[0]
            sub_key = sub_url.rsplit("/", 1)[1].split(".")[0]
            return img_key, sub_key
        except Exception:
            # Fallback keys mặc định nếu mạng chậm
            return "7cd08448135d4853ae16478d860c2340", "4301550c6092497d979b007945d72f10"

    def extract_mid(self, url_or_mid: str) -> str:
        """Trích xuất Member ID (mid / UID) của tài khoản Bilibili."""
        match = re.search(r"space\.bilibili\.com/(\d+)", url_or_mid)
        if match:
            return match.group(1)
        # Nếu nhập trực tiếp UID dạng số
        digits = re.findall(r"\d+", url_or_mid)
        return digits[0] if digits else url_or_mid

    def get_user_videos(self, space_url_or_mid: str, page_size: int = 15) -> list[dict[str, Any]]:
        """Lấy danh sách video từ không gian cá nhân (Space) của tác giả."""
        mid = self.extract_mid(space_url_or_mid)
        if not mid or not mid.isdigit():
            return []

        img_key, sub_key = self.get_wbi_keys()
        params = {
            "mid": mid,
            "ps": min(page_size, 30),
            "pn": 1,
            "order": "pubdate",
        }
        signed_params = enc_wbi(params, img_key, sub_key)

        videos = []
        try:
            url = "https://api.bilibili.com/x/space/wbi/arc/search"
            resp = self.session.get(url, params=signed_params, timeout=15)
            if resp.status_code == 200:
                vlist = resp.json().get("data", {}).get("list", {}).get("vlist", [])
                for v in vlist:
                    bvid = v.get("bvid")
                    title = v.get("title", f"bilibili_{bvid}")
                    if bvid:
                        videos.append(
                            {
                                "id": bvid,
                                "title": title,
                                "url": f"https://www.bilibili.com/video/{bvid}",
                                "cover": v.get("pic", ""),
                                "duration": v.get("length", 0),
                            }
                        )
        except Exception:
            pass

        return videos

    def download_video(self, bvid: str, output_path: Path) -> Path:
        """Tải video DASH (Video + Audio) và gộp bằng FFmpeg."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # 1. Lấy CID
        view_url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        view_res = self.session.get(view_url, timeout=10).json()
        cid = view_res.get("data", {}).get("cid")
        if not cid:
            raise RuntimeError(f"Không tìm thấy cid cho Bilibili BV: {bvid}")

        # 2. Lấy link stream DASH
        play_url = f"https://api.bilibili.com/x/player/wbi/playurl?bvid={bvid}&cid={cid}&fnval=4048"
        play_res = self.session.get(play_url, timeout=10).json()
        dash = play_res.get("data", {}).get("dash")
        if not dash:
            # Fallback link durl nếu không có DASH
            durl = play_res.get("data", {}).get("durl", [])
            if not durl:
                raise RuntimeError(f"Không lấy được stream cho Bilibili {bvid}")
            stream_url = durl[0]["url"]
            self._download_chunk(stream_url, output_path, bvid)
            return output_path

        # 3. Tải video stream và audio stream
        v_stream = dash.get("video", [])[0]["baseUrl"]
        a_stream = dash.get("audio", [])[0]["baseUrl"]

        tmp_v = output_path.with_suffix(".tmp_v.m4s")
        tmp_a = output_path.with_suffix(".tmp_a.m4s")

        self._download_chunk(v_stream, tmp_v, bvid)
        self._download_chunk(a_stream, tmp_a, bvid)

        # 4. Gộp bằng FFmpeg (copy codec không re-encode cực nhanh)
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(tmp_v),
            "-i", str(tmp_a),
            "-c", "copy",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)

        tmp_v.unlink(missing_ok=True)
        tmp_a.unlink(missing_ok=True)
        return output_path

    def _download_chunk(self, url: str, target: Path, bvid: str) -> None:
        headers = {
            "Referer": f"https://www.bilibili.com/video/{bvid}",
            "User-Agent": BILIBILI_UA,
        }
        res = self.session.get(url, headers=headers, stream=True, timeout=60)
        res.raise_for_status()
        with open(target, "wb") as f:
            for chunk in res.iter_content(chunk_size=1024 * 64):
                if chunk:
                    f.write(chunk)
