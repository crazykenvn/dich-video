"""Trình điều phối trung tâm (Download Manager): Cào, tải không trùng lặp và kích hoạt xử lý hậu kỳ video."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from ..config import OUTPUT_DIR
from ..gemini_rotator import get_shared_rotator
from .bilibili_engine import BilibiliDownloader
from .db import (
    get_accounts,
    init_db,
    is_video_downloaded,
    record_download,
    record_discovered_video,
    mark_video_downloaded,
    get_video_by_id,
    update_account_last_checked,
    update_video_processing,
)
from .douyin_engine import DouyinDownloader
from .ytdlp_engine import YtDlpEngine

def get_download_root() -> Path:
    from .settings import load_settings
    settings = load_settings()
    root_str = settings.get("download_root_dir")
    if root_str and Path(root_str).exists():
        return Path(root_str).resolve()
    default_dir = (OUTPUT_DIR / "downloads").resolve()
    default_dir.mkdir(parents=True, exist_ok=True)
    return default_dir


DOWNLOADS_DIR = (OUTPUT_DIR / "downloads").resolve()

ProgressFn = Callable[[str, float], None]


def sanitize_filename(name: str) -> str:
    """Loại bỏ ký tự không hợp lệ trong tên file trên Windows."""
    clean = re.sub(r'[\\/*?:"<>|]', "_", name).strip()
    return clean[:80] if clean else "video"


def cache_thumbnail(thumbnail_url: str, platform: str, vid_id: str) -> str:
    """Tải và lưu thumbnail vào thư mục output/thumbnails để tránh lỗi CDN/hotlink."""
    if not thumbnail_url:
        return ""
    if Path(thumbnail_url).exists():
        return thumbnail_url
    try:
        thumb_dir = (OUTPUT_DIR / "thumbnails").resolve()
        thumb_dir.mkdir(parents=True, exist_ok=True)
        local_path = thumb_dir / f"{platform}_{sanitize_filename(vid_id)}.jpg"
        if local_path.exists() and local_path.stat().st_size > 500:
            return str(local_path)

        import requests
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        if platform == "bilibili":
            headers["Referer"] = "https://www.bilibili.com/"
        elif platform == "douyin":
            headers["Referer"] = "https://www.douyin.com/"

        r = requests.get(thumbnail_url, headers=headers, timeout=12)
        if r.status_code == 200 and len(r.content) > 500:
            local_path.write_bytes(r.content)
            return str(local_path)
    except Exception as e:
        print(f"[cache_thumbnail] Không tải được thumbnail {vid_id}: {e}")
    return thumbnail_url


def cleanup_thumbnail_file(thumbnail_url: str = "", platform: str = "", vid_id: str = "") -> None:
    """Xóa file thumbnail đã lưu trên đĩa."""
    if thumbnail_url:
        p = Path(thumbnail_url)
        if p.exists() and p.is_file():
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass
    if platform and vid_id:
        thumb_path = OUTPUT_DIR / "thumbnails" / f"{platform}_{sanitize_filename(vid_id)}.jpg"
        if thumb_path.exists() and thumb_path.is_file():
            try:
                thumb_path.unlink(missing_ok=True)
            except Exception:
                pass


class DownloadManager:
    """Quản lý quét tài khoản, tải thumbnail/metadata và tải video theo yêu cầu."""

    def __init__(self, pipeline: Any | None = None) -> None:
        init_db()
        self.pipeline = pipeline

    def scan_account(
        self,
        account: dict[str, Any],
        max_videos: int | None = None,
        force_full_scan: bool = False,
        progress: ProgressFn | None = None,
    ) -> list[dict[str, Any]]:
        """Quét 1 tài khoản:
        - Lần đầu quét hoặc force_full_scan=True: Quét toàn bộ video của kênh (max_videos=None, stop_after_id=None).
        - Lần 2 quét trở đi: Quét từ thời điểm trước đó đến video mới nhất (dừng khi gặp last_video_id).
        - Chỉ tải thumbnail và lưu metadata, KHÔNG tự động tải file video mp4 vật lý.
        """
        platform = account["platform"].lower()
        account_id = account["account_id"]
        account_url = account["account_url"]
        last_video_id = account.get("last_video_id")
        last_checked_at = account.get("last_checked_at")

        # Xác định lần đầu quét hay quét tăng dần
        is_first_scan = force_full_scan or (not bool(last_video_id and last_checked_at))
        stop_after_id = None if is_first_scan else str(last_video_id)
        fetch_limit = max_videos if max_videos is not None else None

        def report(msg: str, pct: float) -> None:
            if progress:
                progress(msg, max(0.0, min(1.0, pct)))

        scan_type_str = "toàn bộ kênh (quét từ đầu)" if is_first_scan else f"mới nhất (từ mốc {stop_after_id})"
        report(f"Đang quét {scan_type_str} [{platform.upper()}] {account_id}…", 0.05)
        videos_meta: list[dict[str, Any]] = []

        # 1. Trích xuất danh sách video từ kênh
        try:
            if platform == "douyin":
                dy = DouyinDownloader()
                videos_meta = dy.get_user_videos(account_url, max_count=fetch_limit, stop_after_id=stop_after_id)

            elif platform == "bilibili":
                bili = BilibiliDownloader()
                videos_meta = bili.get_user_videos(account_url, max_count=fetch_limit, stop_after_id=stop_after_id)
                if not videos_meta:
                    ytdlp = YtDlpEngine("bilibili")
                    if ytdlp.is_available():
                        videos_meta = ytdlp.fetch_account_videos(account_url, max_count=fetch_limit, stop_after_id=stop_after_id)
            else:  # tiktok, facebook, instagram, youtube...
                ytdlp = YtDlpEngine(platform)
                if ytdlp.is_available():
                    videos_meta = ytdlp.fetch_account_videos(account_url, max_count=fetch_limit, stop_after_id=stop_after_id)
        except Exception as e:
            report(f"Lỗi khi cào tài khoản {account_id}: {e}", 0.1)
            return []

        # Cập nhật checkpoint mốc quét cho tài khoản: ưu tiên mốc video mới nhất không phải video ghim
        if videos_meta:
            non_pinned = [v for v in videos_meta if not v.get("is_pinned")]
            latest_item = non_pinned[0] if non_pinned else videos_meta[0]
            latest_id = str(latest_item["id"])
            update_account_last_checked(account_id, last_video_id=latest_id)
        else:
            update_account_last_checked(account_id)

        if not videos_meta:
            report(f"Tài khoản {account_id}: Không phát hiện thêm video mới nào.", 1.0)
            return []

        report(f"Tìm thấy {len(videos_meta)} video. Đang tải thumbnail và đồng bộ dữ liệu…", 0.3)
        from concurrent.futures import ThreadPoolExecutor

        def _fetch_thumb(item: dict[str, Any]) -> tuple[str, str]:
            v_id = str(item["id"])
            t_url = item.get("thumbnail") or item.get("cover") or ""
            return v_id, cache_thumbnail(t_url, platform, v_id)

        thumb_map: dict[str, str] = {}
        try:
            with ThreadPoolExecutor(max_workers=8) as executor:
                for v_id, c_thumb in executor.map(_fetch_thumb, videos_meta):
                    thumb_map[v_id] = c_thumb
        except Exception:
            pass

        # Gán thứ tự ghim (pinned rank): video ghim đầu tiên nhận 3, thứ hai nhận 2, thứ ba nhận 1
        pinned_count = sum(1 for v in videos_meta if v.get("is_pinned"))
        curr_pin_rank = pinned_count
        for item in videos_meta:
            if item.get("is_pinned"):
                item["is_pinned"] = curr_pin_rank
                curr_pin_rank = max(1, curr_pin_rank - 1)
            else:
                item["is_pinned"] = 0

        # Lưu vào DB theo thứ tự từ cũ nhất đến mới nhất (reversed) để video mới nhất nhận ID lớn hơn
        discovered_map: dict[str, dict[str, Any]] = {}
        total_items = len(videos_meta)

        for rev_idx, item in enumerate(reversed(videos_meta)):
            vid_id = str(item["id"])
            title = item.get("title", f"video_{vid_id}")
            video_url = item.get("url") or item.get("webpage_url") or ""
            duration = float(item.get("duration") or 0.0)
            published_at = item.get("published_at")
            play_url = item.get("play_url") or ""
            is_pin = int(item.get("is_pinned") or 0)
            cached_thumb = thumb_map.get(vid_id) or cache_thumbnail(
                item.get("thumbnail") or item.get("cover") or "", platform, vid_id
            )

            # Lưu metadata video vào DB với trạng thái 'discovered'
            db_id = record_discovered_video(
                account_id=account_id,
                platform=platform,
                platform_video_id=vid_id,
                title=title,
                thumbnail_url=cached_thumb,
                video_url=video_url,
                duration=duration,
                published_at=published_at,
                play_url=play_url,
                is_pinned=is_pin,
            )

            is_already_dl = is_video_downloaded(platform, vid_id)
            discovered_map[vid_id] = {
                "id": db_id,
                "account_id": account_id,
                "platform": platform,
                "platform_video_id": vid_id,
                "title": title,
                "thumbnail_url": cached_thumb,
                "video_url": video_url,
                "duration": duration,
                "download_status": "downloaded" if is_already_dl else "discovered",
                "play_url": play_url,
                "published_at": published_at,
                "is_pinned": is_pin,
            }

            pct = 0.4 + (0.6 * ((rev_idx + 1) / total_items))
            report(f"Đã lưu ({rev_idx+1}/{total_items}): {title[:35]}…", pct)

        # Trả về danh sách đúng theo thứ tự hiển thị của Douyin (mới nhất/ghim lên đầu)
        discovered_records = [discovered_map[str(item["id"])] for item in videos_meta if str(item["id"]) in discovered_map]
        report(f"Hoàn thành quét kênh {account_id}: Đã tìm thấy {len(discovered_records)} video (Chờ bạn chọn tải video).", 1.0)
        return discovered_records

    def scan_all_accounts(
        self,
        max_videos_per_account: int | None = None,
        force_full_scan: bool = False,
        progress: ProgressFn | None = None,
    ) -> list[dict[str, Any]]:
        """Quét tất cả tài khoản đang bật (is_active = 1), chỉ tải thumbnail."""
        accounts = get_accounts(active_only=True)
        all_discovered: list[dict[str, Any]] = []
        total = len(accounts)
        if total == 0:
            if progress:
                progress("Không có tài khoản nào trong danh sách theo dõi.", 1.0)
            return []

        for i, acc in enumerate(accounts):
            if progress:
                progress(f"Đang xử lý kênh {i+1}/{total}: [{acc['platform']}] {acc['account_id']}", (i / total))
            discovered = self.scan_account(
                acc,
                max_videos=max_videos_per_account,
                force_full_scan=force_full_scan,
                progress=progress,
            )
            all_discovered.extend(discovered)

        if progress:
            progress(f"Đã hoàn thành quét {total} tài khoản. Tổng số video: {len(all_discovered)}", 1.0)
        return all_discovered

    def download_discovered_video(
        self,
        video_row: dict[str, Any],
        progress: ProgressFn | None = None,
    ) -> Path:
        """Tải file video vật lý (.mp4) về máy tính khi người dùng bấm quyết định tải."""
        platform = video_row["platform"].lower()
        account_id = video_row.get("account_id") or "general_inbox"
        vid_id = str(video_row["platform_video_id"])
        title = video_row.get("title") or f"video_{vid_id}"
        video_url = video_row.get("video_url") or ""

        target_dir = get_download_root() / f"{platform}_{sanitize_filename(account_id)}"
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = sanitize_filename(title)
        dest_file = target_dir / f"{safe_name}_{vid_id}.mp4"

        def report(msg: str, pct: float) -> None:
            if progress:
                progress(msg, max(0.0, min(1.0, pct)))

        # 1. Kiểm tra chống tải trùng: Nếu file đã có sẵn trên ổ cứng hoặc đã tải trước đó
        raw_p = video_row.get("raw_video_path")
        if raw_p:
            p = Path(raw_p)
            if p.exists() and p.is_file() and p.stat().st_size > 1024 * 50:
                report(f"Video {vid_id} đã tải về máy trước đó.", 1.0)
                mark_video_downloaded(platform, vid_id, str(p))
                return p

        if dest_file.exists() and dest_file.stat().st_size > 1024 * 50:
            report(f"Video {vid_id} đã có sẵn trên đĩa.", 1.0)
            mark_video_downloaded(platform, vid_id, str(dest_file))
            return dest_file

        report(f"Đang tải video thực tế: {title[:35]}…", 0.1)
        download_ok = False
        try:
            if platform == "bilibili":
                BilibiliDownloader().download_video(vid_id, dest_file)
                download_ok = True
            elif platform == "douyin":
                douyin_dl = DouyinDownloader()
                play_url = video_row.get("play_url")
                target_url = video_url if video_url else f"https://www.douyin.com/video/{vid_id}"
                dest_file = douyin_dl.download_single_video(target_url, dest_file, play_url=play_url)
                download_ok = True
            else:
                ytdlp = YtDlpEngine(platform)
                target_url = video_url if video_url else vid_id
                dest_file = ytdlp.download_video(target_url, dest_file)
                download_ok = True
        except Exception as e:
            print(f"[DownloadManager] Lỗi tải video {vid_id}: {e}")
            # Fallback
            try:
                ytdlp = YtDlpEngine(platform)
                target_url = video_url if video_url else vid_id
                dest_file = ytdlp.download_video(target_url, dest_file)
                download_ok = True
            except Exception as ex:
                print(f"[DownloadManager] Fallback lỗi: {ex}")
                raise RuntimeError(f"Không thể tải video {vid_id}: {e} (Fallback: {ex})")

        if download_ok and dest_file.exists() and dest_file.stat().st_size > 1024 * 10:
            mark_video_downloaded(platform, vid_id, str(dest_file))
            report(f"Tải video thành công!", 1.0)
            return dest_file
        else:
            raise RuntimeError(f"Tải video {vid_id} không thành công hoặc file rỗng.")


    def process_inbox_video(
        self,
        video_row: dict[str, Any],
        mode: str = "remix",
        settings: dict[str, Any] | None = None,
        progress: ProgressFn | None = None,
    ) -> Path:
        """Xử lý video từ Inbox: Remix hoặc Dịch/Lồng tiếng, xuất thẳng ra thư mục Ready to Upload."""
        from .settings import load_settings
        from .. import media

        cfg = load_settings()
        if settings:
            cfg.update(settings)

        platform = video_row["platform"]
        vid_id = str(video_row["platform_video_id"])
        raw_path = Path(video_row["raw_video_path"])
        if not raw_path.exists():
            raise FileNotFoundError(f"Không tìm thấy file video gốc: {raw_path}")

        update_video_processing(platform, vid_id, "processing")
        READY_DIR = OUTPUT_DIR / "ready_to_upload"
        READY_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = sanitize_filename(video_row.get("title") or vid_id)

        def report(msg: str, pct: float) -> None:
            if progress:
                progress(msg, max(0.0, min(1.0, pct)))

        # Chuẩn bị file logo (nếu có file ảnh hoặc sinh từ chữ)
        actual_wm = cfg.get("watermark_path")
        if cfg.get("watermark_enabled", True):
            if actual_wm and not Path(actual_wm).exists():
                actual_wm = None
            if not actual_wm and cfg.get("watermark_text"):
                try:
                    from ..config import TEMP_DIR
                    from ..watermark import generate_text_logo
                    logo_dir = TEMP_DIR / "branding"
                    logo_dir.mkdir(parents=True, exist_ok=True)
                    tmp_logo = logo_dir / "text_watermark.png"
                    generate_text_logo(cfg["watermark_text"].strip(), tmp_logo)
                    actual_wm = str(tmp_logo)
                except Exception:
                    pass

        try:
            if mode == "remix":
                report("Đang chạy bộ lọc lách bản quyền & chèn logo (3-6s)…", 0.3)
                out_file = READY_DIR / f"{safe_name}_{vid_id}_remix.mp4"
                processed_path = media.remix_video(
                    video_path=raw_path,
                    output_path=out_file,
                    anti_video=cfg.get("anti_video", True),
                    anti_audio=cfg.get("anti_audio", True),
                    watermark_enabled=cfg.get("watermark_enabled", True),
                    watermark_path=actual_wm,
                    watermark_opacity=cfg.get("watermark_opacity", 0.18),
                    watermark_motion=cfg.get("watermark_motion", "drift"),
                    watermark_width=int(cfg.get("watermark_width", 180)),
                    video_quality=cfg.get("video_quality", "high"),
                )
                report("Hoàn tất Remix video!", 1.0)
                update_video_processing(platform, vid_id, "completed", str(processed_path))
                return Path(processed_path)

            elif mode in ("dub", "hard", "soft"):
                if not self.pipeline:
                    from ..pipeline import VideoTranslatePipeline
                    self.pipeline = VideoTranslatePipeline(
                        model_size=cfg.get("model_size", "medium"),
                        device=cfg.get("device", "cuda"),
                    )
                report("Đang bóc băng Whisper, dịch Gemini và lồng tiếng AI…", 0.2)
                res = self.pipeline.run(
                    video_path=raw_path,
                    target_lang=cfg.get("target_lang", "vi"),
                    source_lang=cfg.get("source_lang", "zh"),
                    mode=mode,
                    bilingual=cfg.get("bilingual", False),
                    voice=cfg.get("voice"),
                    fit_timing=cfg.get("fit_timing", True),
                    resolve_overlap=cfg.get("resolve_overlap", True),
                    max_overlap_tempo=cfg.get("max_overlap_tempo", 1.85),
                    burn_sub=cfg.get("burn_sub", True),
                    progress=report,
                    output_dir=READY_DIR,
                    save_direct_to_output_dir=True,
                    font_size=cfg.get("font_size", 16),
                    sub_style=cfg.get("sub_style", "solid_black"),
                    sub_position=cfg.get("sub_position", "bottom"),
                    sub_margin_v=cfg.get("sub_margin_v", 30),
                    box_padding=cfg.get("box_padding", 5),
                    box_opacity=cfg.get("box_opacity", 100),
                    watermark_enabled=cfg.get("watermark_enabled", True),
                    watermark_path=actual_wm,
                    watermark_text=cfg.get("watermark_text"),
                    watermark_opacity=cfg.get("watermark_opacity", 0.18),
                    watermark_motion=cfg.get("watermark_motion", "drift"),
                    watermark_width=int(cfg.get("watermark_width", 180)),
                    video_quality=cfg.get("video_quality", "high"),
                    anti_video=cfg.get("anti_video", True),
                    anti_audio=cfg.get("anti_audio", True),
                )
                report("Hoàn tất dịch & lồng tiếng!", 1.0)
                update_video_processing(platform, vid_id, "completed", str(res.output_video))
                return Path(res.output_video) if res.output_video else raw_path
            else:
                update_video_processing(platform, vid_id, "completed", str(raw_path))
                return raw_path
        except Exception as e:
            update_video_processing(platform, vid_id, "failed", error=str(e))
            raise

