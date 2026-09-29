#!/usr/bin/env python3
"""CLI Quản lý Tự Động Tải & Xử Lý Video Đa Nền Tảng (Facebook, Instagram, Douyin, TikTok, Bilibili).

Cách dùng:
  # 1. Thêm tài khoản mới
  python download_cli.py add --platform douyin --url "https://www.douyin.com/user/MS4wLjAB..." --name "Kênh Douyin A" --mode remix
  python download_cli.py add --platform bilibili --url "https://space.bilibili.com/123456" --name "Bilibili Creator" --mode dub
  python download_cli.py add --platform tiktok --url "https://www.tiktok.com/@creator" --name "TikTok Creator" --mode remix

  # 2. Xem danh sách tài khoản theo dõi
  python download_cli.py list

  # 3. Quét và tải video mới ngay bây giờ
  python download_cli.py scan --max 5

  # 4. Xem lịch sử video đã tải
  python download_cli.py history
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent))


from src.downloader.db import (
    add_account,
    delete_account,
    get_accounts,
    get_recent_videos,
    init_db,
    update_account_status,
)
from src.downloader.manager import DownloadManager



def main() -> None:
    init_db()
    parser = argparse.ArgumentParser(
        prog="download_cli",
        description="Tự động tải & xử lý video từ Facebook, Instagram, Douyin, TikTok, Bilibili.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Lệnh thực thi")

    # Subcommand: add
    p_add = subparsers.add_parser("add", help="Thêm tài khoản theo dõi mới")
    p_add.add_argument("--platform", required=True, choices=["douyin", "tiktok", "bilibili", "facebook", "instagram"], help="Nền tảng")
    p_add.add_argument("--url", required=True, help="Link trang cá nhân hoặc kênh")
    p_add.add_argument("--name", default=None, help="Tên hiển thị gợi nhớ")
    p_add.add_argument("--id", default=None, dest="account_id", help="ID tài khoản (tự suy ra từ URL nếu bỏ trống)")
    p_add.add_argument("--mode", default="remix", choices=["remix", "dub", "none"], help="Chế độ xử lý sau khi tải")
    p_add.add_argument("--no-auto", action="store_true", help="Không tự động xử lý (chỉ tải về)")

    # Subcommand: list
    subparsers.add_parser("list", help="Xem danh sách tài khoản đang theo dõi")

    # Subcommand: delete
    p_del = subparsers.add_parser("delete", help="Xóa tài khoản theo dõi")
    p_del.add_argument("account_id", help="ID tài khoản cần xóa")

    # Subcommand: toggle
    p_tog = subparsers.add_parser("toggle", help="Bật hoặc tắt trạng thái theo dõi")
    p_tog.add_argument("account_id", help="ID tài khoản")
    p_tog.add_argument("--active", type=int, choices=[0, 1], required=True, help="1 = Bật, 0 = Tắt")

    # Subcommand: scan
    p_scan = subparsers.add_parser("scan", help="Quét và tải video mới")
    p_scan.add_argument("--account", default=None, help="Chỉ quét 1 tài khoản cụ thể theo ID")
    p_scan.add_argument("--max", type=int, default=5, help="Số video tối đa mỗi tài khoản (mặc định 5)")
    p_scan.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"], help="Phần cứng cho Whisper nếu lồng tiếng")

    # Subcommand: history
    p_hist = subparsers.add_parser("history", help="Xem lịch sử video đã tải")
    p_hist.add_argument("--limit", type=int, default=30, help="Số lượng bản ghi")

    args = parser.parse_args()

    if args.subcommand == "add":
        acc_id = args.account_id or args.url.strip("/").split("/")[-1]
        add_account(
            platform=args.platform,
            account_id=acc_id,
            account_url=args.url,
            account_name=args.name or acc_id,
            auto_process=not args.no_auto,
            process_mode=args.mode,
        )
        print(f"✅ Đã thêm tài khoản [{args.platform.upper()}] {acc_id} thành công!")

    elif args.subcommand == "list":
        accounts = get_accounts()
        if not accounts:
            print("Chưa có tài khoản nào được theo dõi. Dùng 'add' để thêm mới.")
            return
        print(f"\n📋 DANH SÁCH TÀI KHOẢN ĐANG THEO DÕI ({len(accounts)}):")
        print("-" * 80)
        for a in accounts:
            status = "🟢 Đang bật" if a["is_active"] else "🔴 Đang tắt"
            auto_str = f"Auto ({a['process_mode']})" if a["auto_process"] else "Chỉ tải"
            print(f"[{a['platform'].upper():<9}] {a['account_name']:<25} ID: {a['account_id']:<20} {auto_str:<12} {status}")
        print("-" * 80)

    elif args.subcommand == "delete":
        delete_account(args.account_id)
        print(f"🗑️ Đã xóa tài khoản {args.account_id}.")

    elif args.subcommand == "toggle":
        update_account_status(args.account_id, bool(args.active))
        state = "BẬT" if args.active else "TẮT"
        print(f"🔄 Đã {state} theo dõi cho tài khoản {args.account_id}.")

    elif args.subcommand == "scan":
        print("🚀 Khởi động tiến trình quét video mới…")
        pipeline = None
        try:
            from src.pipeline import VideoTranslatePipeline
            pipeline = VideoTranslatePipeline(device=args.device)
        except Exception as e:
            print(f"ℹ️ Chú ý: Không nạp được module dịch AI ({e}). Chế độ Remix (Lách bản quyền) vẫn hoạt động bình thường.")
        manager = DownloadManager(pipeline=pipeline)

        def print_progress(msg: str, pct: float) -> None:
            pct_int = int(pct * 100)
            print(f"[{pct_int:3d}%] {msg}")

        if args.account:
            accounts = [a for a in get_accounts() if a["account_id"] == args.account]
            if not accounts:
                print(f"❌ Không tìm thấy tài khoản với ID: {args.account}")
                return
            res = manager.scan_account(accounts[0], max_videos=args.max, progress=print_progress)
        else:
            res = manager.scan_all_accounts(max_videos_per_account=args.max, progress=print_progress)

        print(f"\n🎉 Hoàn thành quét. Tổng số video mới đã tải: {len(res)}")

    elif args.subcommand == "history":
        videos = get_recent_videos(limit=args.limit)
        if not videos:
            print("Chưa có lịch sử video nào được tải.")
            return
        print(f"\n📹 LỊCH SỬ VIDEO ĐÃ TẢI ({len(videos)} video gần nhất):")
        print("-" * 90)
        for v in videos:
            status_emoji = "✅" if v["processed_status"] == "completed" else ("⏳" if v["processed_status"] == "pending" else "⚠️")
            print(f"{status_emoji} [{v['platform'].upper():<9}] {v['title'][:40]:<42} | Trạng thái: {v['processed_status']:<10} | {v['downloaded_at'][:19]}")
        print("-" * 90)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
