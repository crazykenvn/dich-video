"""Trình điều phối trung tâm (Download Manager): Cào, tải không trùng lặp và kích hoạt xử lý hậu kỳ video."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from ..config import OUTPUT_DIR
from .bilibili_engine import BilibiliDownloader
from .db import (
    get_accounts,
    init_db,
    is_video_downloaded,
    record_download,
    update_account_last_checked,
    update_video_processing,
)
from .douyin_engine import DouyinDownloader
from .ytdlp_engine import YtDlpEngine

DOWNLOADS_DIR = OUTPUT_DIR / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

ProgressFn = Callable[[str, float], None]


def sanitize_filename(name: str) -> str:
    """Loại bỏ ký tự không hợp lệ trong tên file trên Windows."""
    clean = re.sub(r'[\\/*?:"<>|]', "_", name).strip()
    return clean[:80] if clean else "video"


class DownloadManager:
    """Quản lý quét tài khoản, tải video và chuyển tiếp sang pipeline xử lý."""

    def __init__(self, pipeline: Any | None = None) -> None:
        init_db()
        self.pipeline = pipeline

    def scan_account(
        self,
        account: dict[str, Any],
        max_videos: int = 5,
        progress: ProgressFn | None = None,
    ) -> list[Path]:
        """Quét 1 tài khoản, phát hiện video mới và tải về."""
        platform = account["platform"].lower()
        account_id = account["account_id"]
        account_url = account["account_url"]
        auto_process = bool(account.get("auto_process", 1))
        process_mode = account.get("process_mode", "remix")

        def report(msg: str, pct: float) -> None:
            if progress:
                progress(msg, max(0.0, min(1.0, pct)))

        report(f"Đang kiểm tra tài khoản [{platform.upper()}] {account_id}…", 0.05)
        videos_meta: list[dict[str, Any]] = []

        # 1. Trích xuất danh sách video mới từ tài khoản
        try:
            if platform == "douyin":
                dy = DouyinDownloader()
                videos_meta = dy.get_user_videos(account_url, max_count=max_videos)

            elif platform == "bilibili":
                bili = BilibiliDownloader()
                videos_meta = bili.get_user_videos(account_url, page_size=max_videos)
                if not videos_meta:
                    ytdlp = YtDlpEngine("bilibili")
                    if ytdlp.is_available():
                        videos_meta = ytdlp.fetch_account_videos(account_url, max_count=max_videos)
            else:  # tiktok, facebook, instagram
                ytdlp = YtDlpEngine(platform)
                if ytdlp.is_available():
                    videos_meta = ytdlp.fetch_account_videos(account_url, max_count=max_videos)
        except Exception as e:
            report(f"Lỗi khi cào tài khoản {account_id}: {e}", 0.1)
            return []

        update_account_last_checked(account_id)

        if not videos_meta:
            report(f"Không tìm thấy video nào mới cho {account_id}.", 1.0)
            return []

        # 2. Lọc bỏ các video đã tải (chống trùng lặp)
        new_videos = [v for v in videos_meta if not is_video_downloaded(platform, v["id"])]
        if not new_videos:
            report(f"Tài khoản {account_id}: Toàn bộ video đều đã được tải trước đó.", 1.0)
            return []

        report(f"Phát hiện {len(new_videos)} video mới. Bắt đầu tải…", 0.2)
        downloaded_paths: list[Path] = []
        target_dir = DOWNLOADS_DIR / f"{platform}_{sanitize_filename(account_id)}"
        target_dir.mkdir(parents=True, exist_ok=True)

        for idx, item in enumerate(new_videos):
            vid_id = item["id"]
            title = item.get("title", f"video_{vid_id}")
            safe_name = sanitize_filename(title)
            dest_file = target_dir / f"{safe_name}_{vid_id}.mp4"

            pct = 0.2 + (0.4 * (idx / len(new_videos)))
            report(f"Đang tải ({idx+1}/{len(new_videos)}): {title[:35]}…", pct)

            download_ok = False
            try:
                if platform == "douyin" and item.get("play_url"):
                    DouyinDownloader().download_clean_video(item["play_url"], dest_file)
                    download_ok = True
                elif platform == "bilibili":
                    BilibiliDownloader().download_video(vid_id, dest_file)
                    download_ok = True
                else:
                    ytdlp = YtDlpEngine(platform)
                    dest_file = ytdlp.download_video(item["url"], dest_file)
                    download_ok = True
            except Exception as e:
                print(f"[DownloadManager] Lỗi tải video {vid_id}: {e}")
                # Fallback qua yt-dlp nếu engine chuyên biệt lỗi
                try:
                    ytdlp = YtDlpEngine(platform)
                    dest_file = ytdlp.download_video(item["url"], dest_file)
                    download_ok = True
                except Exception as ex:
                    print(f"[DownloadManager] Fallback yt-dlp cũng lỗi: {ex}")

            if download_ok and dest_file.exists():
                downloaded_paths.append(dest_file)
                record_download(
                    account_id=account_id,
                    platform=platform,
                    platform_video_id=vid_id,
                    title=title,
                    raw_video_path=str(dest_file),
                    processed_status="inbox",
                )

        report(f"Hoàn thành quét tài khoản {account_id}. Đã tải {len(downloaded_paths)} video mới vào Hộp thư chờ duyệt.", 1.0)
        return downloaded_paths


    def scan_all_accounts(
        self,
        max_videos_per_account: int = 5,
        progress: ProgressFn | None = None,
    ) -> list[Path]:
        """Quét và tải tất cả tài khoản đang bật (is_active = 1)."""
        accounts = get_accounts(active_only=True)
        all_downloaded: list[Path] = []
        total = len(accounts)
        if total == 0:
            if progress:
                progress("Không có tài khoản nào trong danh sách theo dõi.", 1.0)
            return []

        for i, acc in enumerate(accounts):
            if progress:
                progress(f"Đang xử lý kênh {i+1}/{total}: [{acc['platform']}] {acc['account_id']}", (i / total))
            downloaded = self.scan_account(acc, max_videos=max_videos_per_account, progress=progress)
            all_downloaded.extend(downloaded)

        if progress:
            progress(f"Đã hoàn thành quét {total} tài khoản. Tổng số video mới: {len(all_downloaded)}", 1.0)
        return all_downloaded

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
                    watermark_path=cfg.get("watermark_path"),
                    watermark_opacity=cfg.get("watermark_opacity", 0.18),
                    watermark_motion=cfg.get("watermark_motion", "drift"),
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
                    font_size=cfg.get("font_size", 11),
                    sub_style=cfg.get("sub_style", "solid_black"),
                    sub_position=cfg.get("sub_position", "bottom"),
                    sub_margin_v=cfg.get("sub_margin_v", 30),
                    watermark_enabled=cfg.get("watermark_enabled", True),
                    watermark_path=cfg.get("watermark_path"),
                    watermark_opacity=cfg.get("watermark_opacity", 0.18),
                    watermark_motion=cfg.get("watermark_motion", "drift"),
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

