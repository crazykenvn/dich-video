"""Cơ sở dữ liệu SQLite quản lý tài khoản theo dõi và lịch sử video đã tải (chống trùng lặp)."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import OUTPUT_DIR

DB_DIR = OUTPUT_DIR / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "monitor.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Khởi tạo bảng nếu chưa có."""
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS monitored_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                account_id TEXT NOT NULL UNIQUE,
                account_name TEXT,
                account_url TEXT NOT NULL,
                auto_process INTEGER DEFAULT 1,
                process_mode TEXT DEFAULT 'remix',
                last_checked_at TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS downloaded_videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                platform_video_id TEXT NOT NULL,
                title TEXT,
                raw_video_path TEXT NOT NULL,
                downloaded_at TEXT,
                processed_status TEXT DEFAULT 'inbox',
                processed_video_path TEXT,
                error_message TEXT,
                is_uploaded INTEGER DEFAULT 0,
                uploaded_at TEXT,
                UNIQUE(platform, platform_video_id)
            )
            """
        )
        # Tự động nâng cấp cột nếu database cũ chưa có
        try:
            conn.execute("ALTER TABLE downloaded_videos ADD COLUMN is_uploaded INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE downloaded_videos ADD COLUMN uploaded_at TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE downloaded_videos ADD COLUMN platform_publish_status TEXT DEFAULT '{}'")
        except Exception:
            pass
        conn.commit()



def add_account(
    platform: str,
    account_id: str,
    account_url: str,
    account_name: str | None = None,
    auto_process: bool = True,
    process_mode: str = "remix",
) -> None:
    now = datetime.now().isoformat()
    name = account_name or account_id
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO monitored_accounts (
                platform, account_id, account_name, account_url, auto_process, process_mode, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET
                account_name=excluded.account_name,
                account_url=excluded.account_url,
                auto_process=excluded.auto_process,
                process_mode=excluded.process_mode,
                is_active=1
            """,
            (platform.lower(), account_id, name, account_url, int(auto_process), process_mode, now),
        )
        conn.commit()


def get_accounts(active_only: bool = False) -> list[dict[str, Any]]:
    init_db()
    query = "SELECT * FROM monitored_accounts"
    params: list[Any] = []
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY id DESC"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def update_account_status(account_id: str, is_active: bool) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE monitored_accounts SET is_active = ? WHERE account_id = ?",
            (int(is_active), account_id),
        )
        conn.commit()


def update_account_last_checked(account_id: str) -> None:
    now = datetime.now().isoformat()
    with get_connection() as conn:
        conn.execute(
            "UPDATE monitored_accounts SET last_checked_at = ? WHERE account_id = ?",
            (now, account_id),
        )
        conn.commit()


def delete_account(account_id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM monitored_accounts WHERE account_id = ?", (account_id,))
        conn.commit()


def is_video_downloaded(platform: str, platform_video_id: str) -> bool:
    init_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM downloaded_videos WHERE platform = ? AND platform_video_id = ?",
            (platform.lower(), str(platform_video_id)),
        ).fetchone()
        return row is not None


def record_download(
    account_id: str,
    platform: str,
    platform_video_id: str,
    title: str,
    raw_video_path: str,
    processed_status: str = "pending",
) -> int:
    init_db()
    now = datetime.now().isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT OR REPLACE INTO downloaded_videos (
                account_id, platform, platform_video_id, title, raw_video_path, downloaded_at, processed_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account_id,
                platform.lower(),
                str(platform_video_id),
                title,
                str(raw_video_path),
                now,
                processed_status,
            ),
        )
        conn.commit()
        return cursor.lastrowid or 0


def update_video_processing(
    platform: str,
    platform_video_id: str,
    status: str,
    processed_path: str | None = None,
    error: str | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE downloaded_videos
            SET processed_status = ?, processed_video_path = ?, error_message = ?
            WHERE platform = ? AND platform_video_id = ?
            """,
            (status, processed_path, error, platform.lower(), str(platform_video_id)),
        )
        conn.commit()


def get_recent_videos(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM downloaded_videos
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_pending_videos() -> list[dict[str, Any]]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT v.*, a.process_mode as acc_process_mode, a.auto_process as acc_auto_process
            FROM downloaded_videos v
            LEFT JOIN monitored_accounts a ON v.account_id = a.account_id
            WHERE v.processed_status IN ('pending', 'inbox')
            ORDER BY v.id ASC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def get_inbox_videos() -> list[dict[str, Any]]:
    """Lấy danh sách video đang ở Hộp thư Chờ duyệt (chưa xử lý hoặc bị lỗi)."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM downloaded_videos
            WHERE processed_status IN ('inbox', 'pending', 'downloaded', 'failed')
            ORDER BY id DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def get_failed_videos() -> list[dict[str, Any]]:
    """Lấy danh sách các video bị lỗi trong quá trình xử lý."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM downloaded_videos WHERE processed_status = 'failed' ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def reset_video_status(video_id: int, new_status: str = "inbox") -> None:
    """Khôi phục trạng thái video về inbox để có thể xử lý lại."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE downloaded_videos SET processed_status = ?, error_message = NULL WHERE id = ?",
            (new_status, video_id),
        )
        conn.commit()


def get_ready_videos(include_uploaded: bool = True, limit: int = 100) -> list[dict[str, Any]]:
    """Lấy danh sách video thành phẩm đã hoàn tất và sẵn sàng upload."""
    init_db()
    with get_connection() as conn:
        if include_uploaded:
            query = "SELECT * FROM downloaded_videos WHERE processed_status = 'completed' ORDER BY id DESC LIMIT ?"
            rows = conn.execute(query, (limit,)).fetchall()
        else:
            query = "SELECT * FROM downloaded_videos WHERE processed_status = 'completed' AND (is_uploaded IS NULL OR is_uploaded = 0) ORDER BY id DESC LIMIT ?"
            rows = conn.execute(query, (limit,)).fetchall()
        return [dict(r) for r in rows]


def mark_as_uploaded(video_id: int, is_uploaded: bool = True) -> None:
    """Đánh dấu video đã đăng lên mạng xã hội hay chưa."""
    now = datetime.now().isoformat() if is_uploaded else None
    with get_connection() as conn:
        conn.execute(
            "UPDATE downloaded_videos SET is_uploaded = ?, uploaded_at = ? WHERE id = ?",
            (int(is_uploaded), now, video_id),
        )
        conn.commit()


def mark_as_skipped(video_id: int) -> None:
    """Đánh dấu bỏ qua video này trong Inbox."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE downloaded_videos SET processed_status = 'skipped' WHERE id = ?",
            (video_id,),
        )
        conn.commit()


def delete_downloaded_video(video_id: int) -> None:
    """Xóa bản ghi video khỏi cơ sở dữ liệu."""
    with get_connection() as conn:
        conn.execute("DELETE FROM downloaded_videos WHERE id = ?", (video_id,))
        conn.commit()


def get_platform_publish_status(video_id: int) -> dict[str, Any]:
    """Lấy trạng thái phân phối đa nền tảng (TikTok, Reels, Shorts) của video."""
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT platform_publish_status FROM downloaded_videos WHERE id = ?", (video_id,)).fetchone()
        if not row:
            return {}
        raw = row["platform_publish_status"]
        if not raw:
            return {}
        try:
            import json
            return json.loads(raw)
        except Exception:
            return {}


def toggle_platform_publish_status(video_id: int, platform: str, is_published: bool | None = None) -> dict[str, Any]:
    """Bật / tắt trạng thái đã đăng tải lên một nền tảng cụ thể (tiktok, reels, shorts)."""
    import json
    init_db()
    current = get_platform_publish_status(video_id)
    platform_key = platform.lower()
    
    if is_published is None:
        curr_state = current.get(platform_key, {}).get("is_published", False)
        new_state = not curr_state
    else:
        new_state = is_published

    now = datetime.now().isoformat()
    current[platform_key] = {
        "is_published": new_state,
        "updated_at": now if new_state else None,
    }
    
    # Đồng bộ với is_uploaded cũ nếu có bất kỳ nền tảng nào đã đăng
    any_published = any(v.get("is_published", False) for v in current.values())

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE downloaded_videos 
            SET platform_publish_status = ?, is_uploaded = ?, uploaded_at = ?
            WHERE id = ?
            """,
            (json.dumps(current, ensure_ascii=False), int(any_published), now if any_published else None, video_id),
        )
        conn.commit()
    return current


