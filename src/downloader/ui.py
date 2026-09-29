"""Giao diện UI Studio: Quản lý toàn bộ Quy trình 4 bước (Thu thập -> Duyệt xử lý -> Xuất bản -> Cài đặt)."""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any
import pandas as pd
import streamlit as st

from ..config import (
    EDGE_VOICE_ALTERNATES,
    EDGE_VOICE_MAP,
    LANGUAGES,
    OUTPUT_DIR,
    PROJECT_ROOT,
    VIENEU_VOICES,
    WHISPER_MODELS,
)
from ..gemini_rotator import get_shared_rotator
from .db import (
    add_account,
    delete_account,
    delete_downloaded_video,
    get_accounts,
    get_failed_videos,
    get_inbox_videos,
    get_ready_videos,
    get_recent_videos,
    init_db,
    mark_as_skipped,
    mark_as_uploaded,
    record_download,
    reset_video_status,
    update_account_status,
)
from .manager import DOWNLOADS_DIR, DownloadManager
from .settings import load_settings, save_settings

READY_DIR = OUTPUT_DIR / "ready_to_upload"
READY_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# TAB 1: THU THẬP NGUỒN VÀO (INGESTION)
# =============================================================================
def render_tab_ingestion(manager: DownloadManager) -> None:
    init_db()
    st.subheader("📥 1. Thu Thập Nguồn Vào (Chỉ Tải & Gom Nguồn)")
    st.caption("Tự động cào video gốc sạch từ các kênh mạng xã hội hoặc nạp file video từ máy tính vào Hộp Thư Chờ Duyệt (Inbox).")

    accounts = get_accounts()

    col_add, col_local = st.columns([1.2, 1])

    # 1.1. Thêm kênh theo dõi
    with col_add:
        with st.expander("➕ Thêm kênh / tài khoản cần theo dõi", expanded=len(accounts) == 0):
            with st.form("form_add_channel", clear_on_submit=True):
                platform_choice = st.selectbox(
                    "Nền tảng mạng xã hội",
                    options=["douyin", "tiktok", "bilibili", "facebook", "instagram"],
                    format_func=lambda x: {
                        "douyin": "🎵 Douyin (TikTok Trung Quốc)",
                        "tiktok": "📱 TikTok (Quốc tế)",
                        "bilibili": "📺 Bilibili (B站)",
                        "facebook": "📘 Facebook (Reels/Page)",
                        "instagram": "📸 Instagram (Reels)",
                    }.get(x, x),
                )
                account_url = st.text_input(
                    "Link trang cá nhân / Kênh / ID",
                    placeholder="VD: https://www.douyin.com/user/... hoặc https://space.bilibili.com/123456",
                )
                account_name = st.text_input("Tên gợi nhớ (Tùy chọn)", placeholder="VD: Kênh Review Phim A")

                submitted = st.form_submit_button("➕ Thêm vào danh sách theo dõi", use_container_width=True)
                if submitted:
                    if not account_url.strip():
                        st.error("Vui lòng nhập link tài khoản!")
                    else:
                        raw_id = account_url.strip("/").split("/")[-1].split("?")[0]
                        name = account_name.strip() or raw_id
                        add_account(
                            platform=platform_choice,
                            account_id=raw_id,
                            account_url=account_url.strip(),
                            account_name=name,
                            auto_process=False,  # Chỉ download thuần túy vào Inbox!
                            process_mode="none",
                        )
                        st.success(f"Đã thêm kênh [{platform_choice.upper()}] {name} thành công!")
                        st.rerun()

    # 1.2. Nhập video có sẵn từ máy tính vào Inbox
    with col_local:
        with st.expander("📁 Nhập video có sẵn từ máy tính vào Inbox", expanded=True):
            uploaded_files = st.file_uploader(
                "Kéo thả video vào đây để nạp vào Inbox",
                type=["mp4", "mkv", "mov", "webm"],
                accept_multiple_files=True,
                key="manual_inbox_uploader",
            )
            if uploaded_files:
                imported_count = 0
                for uf in uploaded_files:
                    dest_file = DOWNLOADS_DIR / "local" / uf.name
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    if not dest_file.exists():
                        dest_file.write_bytes(uf.getbuffer())
                        record_download(
                            account_id="local_upload",
                            platform="local",
                            platform_video_id=f"local_{int(time.time())}_{uf.name}",
                            title=Path(uf.name).stem,
                            raw_video_path=str(dest_file),
                            processed_status="inbox",
                        )
                        imported_count += 1
                if imported_count > 0:
                    st.success(f"Đã nạp {imported_count} video vào Inbox Chờ Duyệt!")
                    st.rerun()

    st.markdown("---")

    # 1.3. Danh sách kênh & Nút Quét Tải
    c_h1, c_h2 = st.columns([2, 1])
    with c_h1:
        st.markdown(f"#### 📋 Danh Sách Kênh Đang Theo Dõi ({len(accounts)} kênh)")
    with c_h2:
        max_vids = st.slider("Số video mới tối đa mỗi kênh:", min_value=1, max_value=20, value=5)

    if not accounts:
        st.info("💡 Chưa có kênh nào được theo dõi. Hãy thêm kênh ở trên để bắt đầu cào video tự động.")
    else:
        for acc in accounts:
            with st.container():
                c1, c2, c3, c4 = st.columns([1.5, 4, 1.5, 1])
                with c1:
                    st.markdown(f"**[{acc['platform'].upper()}]**")
                with c2:
                    st.markdown(f"**{acc['account_name']}**")
                    st.caption(f"ID: `{acc['account_id'][:30]}` | Lần quét cuối: {acc['last_checked_at'] or 'Chưa quét'}")
                with c3:
                    is_act = bool(acc["is_active"])
                    toggle = st.toggle("Bật quét", value=is_act, key=f"ingest_tog_{acc['account_id']}")
                    if toggle != is_act:
                        update_account_status(acc["account_id"], toggle)
                        st.rerun()
                with c4:
                    if st.button("🗑️", key=f"ingest_del_{acc['account_id']}", help="Xóa kênh này"):
                        delete_account(acc["account_id"])
                        st.rerun()
            st.divider()

        # Nút Quét Toàn Bộ Kênh
        btn_scan = st.button(
            "🚀 QUÉT & TẢI VIDEO MỚI TẤT CẢ KÊNH ĐANG BẬT (CHỈ TẢI VÀO INBOX)",
            type="primary",
            use_container_width=True,
        )
        if btn_scan:
            scan_progress = st.progress(0.0)
            status_box = st.empty()

            def update_progress(msg: str, pct: float) -> None:
                scan_progress.progress(pct)
                status_box.info(f"⏳ {msg}")

            downloaded = manager.scan_all_accounts(
                max_videos_per_account=max_vids,
                progress=update_progress,
            )
            scan_progress.progress(1.0)
            status_box.success(f"🎉 Đã hoàn tất tải {len(downloaded)} video mới vào Hộp thư chờ duyệt!")
            time.sleep(1)
            st.rerun()


# =============================================================================
# TAB 2: KIỂM TRA & DUYỆT XỬ LÝ (TRIAGE & STUDIO - TỐI ƯU CHO SỐ LƯỢNG LỚN)
# =============================================================================
def render_tab_triage(manager: DownloadManager, pipeline: Any | None = None) -> None:
    init_db()
    st.subheader("🔍 2. Kiểm Tra & Phân Loại Xử Lý Video (Triage Studio)")
    st.caption("Xem trước video trong Inbox, chọn một hoặc nhiều video cùng lúc để chạy Remix lách bản quyền hoặc Dịch & Lồng tiếng AI.")

    inbox_videos = get_inbox_videos()
    failed_videos = get_failed_videos()

    if failed_videos:
        st.warning(f"⚠️ Phát hiện {len(failed_videos)} video bị lỗi xử lý trước đó. Bạn có thể bấm '🔄 Thử lại' trực tiếp tại từng video bên dưới.")

    if not inbox_videos:
        st.info("🎉 Hộp thư Inbox hiện đang trống! Hãy sang Tab **📥 1. Thu Thập Nguồn Vào** để quét video mới hoặc tải file lên.")
        return

    # Khởi tạo session state lưu danh sách ID được chọn
    if "selected_inbox_ids" not in st.session_state:
        st.session_state["selected_inbox_ids"] = set()

    # Đồng bộ các ID hợp lệ còn nằm trong inbox
    valid_ids = {v["id"] for v in inbox_videos}
    st.session_state["selected_inbox_ids"] = st.session_state["selected_inbox_ids"].intersection(valid_ids)

    # 2.1. Thanh điều khiển hiển thị & bộ lọc
    col_f1, col_f2, col_f3 = st.columns([2, 1.5, 1.5])
    with col_f1:
        search_query = st.text_input("🔍 Tìm kiếm theo tiêu đề:", placeholder="Nhập từ khóa...")
    with col_f2:
        platforms = ["Tất cả"] + sorted(list({v["platform"] for v in inbox_videos}))
        filter_plat = st.selectbox("Lọc theo nền tảng:", platforms)
    with col_f3:
        view_mode = st.radio(
            "Chế độ hiển thị:",
            ["📋 Bảng Gọn (Nhiều video)", "🎬 Lưới Thẻ (3 Cột)"],
            horizontal=True,
        )

    # Lọc danh sách theo search và platform
    filtered_videos = inbox_videos
    if filter_plat != "Tất cả":
        filtered_videos = [v for v in filtered_videos if v["platform"] == filter_plat]
    if search_query.strip():
        q = search_query.strip().lower()
        filtered_videos = [v for v in filtered_videos if q in (v["title"] or "").lower()]

    filtered_ids = {v["id"] for v in filtered_videos}
    selected_ids = st.session_state["selected_inbox_ids"]
    selected_count = len(selected_ids.intersection(filtered_ids))

    # 2.2. THANH CÔNG CỤ THAO TÁC HÀNG LOẠT (BULK ACTION BAR)
    st.markdown("---")
    c_sel1, c_sel2, c_act1, c_act2, c_act3 = st.columns([1.5, 1.5, 2.5, 2.5, 1.5])

    with c_sel1:
        if st.button("☑️ Chọn tất cả", use_container_width=True):
            st.session_state["selected_inbox_ids"].update(filtered_ids)
            st.rerun()
    with c_sel2:
        if st.button("◻️ Bỏ chọn", use_container_width=True):
            st.session_state["selected_inbox_ids"].difference_update(filtered_ids)
            st.rerun()
    with c_act1:
        btn_bulk_remix = st.button(
            f"⚡ Remix ({selected_count} video đã chọn)",
            type="primary",
            disabled=selected_count == 0,
            use_container_width=True,
            help="Chạy bộ lọc lách bản quyền pHash Lanczos + Micro-EQ + Hạt Noise + Biến điệu audio + Logo (3-6s/clip).",
        )
    with c_act2:
        btn_bulk_dub = st.button(
            f"🎙️ Dịch & Lồng tiếng ({selected_count} video đã chọn)",
            disabled=selected_count == 0,
            use_container_width=True,
            help="Whisper GPU -> Dịch Gemini -> Lồng tiếng VieNeu-TTS -> Hardsub + Lách bản quyền.",
        )
    with c_act3:
        btn_bulk_del = st.button(
            f"🗑️ Bỏ qua ({selected_count})",
            disabled=selected_count == 0,
            use_container_width=True,
        )

    # Xử lý các thao tác hàng loạt
    if btn_bulk_del:
        for vid_id in list(selected_ids):
            mark_as_skipped(vid_id)
        st.session_state["selected_inbox_ids"].clear()
        st.success("Đã bỏ qua các video đã chọn.")
        st.rerun()

    if btn_bulk_remix or btn_bulk_dub:
        target_mode = "remix" if btn_bulk_remix else "dub"
        target_vids = [v for v in inbox_videos if v["id"] in selected_ids]

        progress_bar = st.progress(0.0)
        status_text = st.empty()

        for idx, v in enumerate(target_vids):
            status_text.info(f"Đang xử lý ({idx+1}/{len(target_vids)}): {v['title'][:35]}…")
            try:
                reset_video_status(v["id"])
                manager.process_inbox_video(v, mode=target_mode)
            except Exception as e:
                st.error(f"Lỗi video {v['platform_video_id']}: {e}")
            progress_bar.progress((idx + 1) / len(target_vids))

        st.session_state["selected_inbox_ids"].clear()
        status_text.success(f"🎉 Đã hoàn tất xử lý {len(target_vids)} video! Video đã chuyển sang Tab **🚀 3. Kho Sẵn Sàng Upload**.")
        time.sleep(2)
        st.rerun()

    st.markdown(f"**Danh sách: Hiển thị {len(filtered_videos)} / {len(inbox_videos)} video trong Inbox | Đã chọn: {selected_count} video**")

    # 2.3. HIỂN THỊ DANH SÁCH VIDEO
    if view_mode == "📋 Bảng Gọn (Nhiều video)":
        # CHẾ ĐỘ 1: BẢNG DANH SÁCH GỌN (Tối ưu hiển thị 50-100 video không giật lag)
        for v in filtered_videos:
            raw_path = Path(v["raw_video_path"])
            vid_id = v["id"]
            is_checked = vid_id in selected_ids
            is_failed = v.get("processed_status") == "failed"

            with st.container():
                col_chk, col_plat, col_title, col_size, col_preview, col_btn_r, col_btn_d, col_btn_x = st.columns(
                    [0.5, 1.2, 4, 1.5, 1.2, 1.2, 1.2, 0.6]
                )

                with col_chk:
                    checked = st.checkbox(f"Chọn {vid_id}", value=is_checked, key=f"tbl_chk_{vid_id}", label_visibility="collapsed")
                    if checked != is_checked:
                        if checked:
                            st.session_state["selected_inbox_ids"].add(vid_id)
                        else:
                            st.session_state["selected_inbox_ids"].discard(vid_id)
                        st.rerun()

                with col_plat:
                    st.markdown(f"`{v['platform'].upper()}`")

                with col_title:
                    if is_failed:
                        st.markdown(f"**{v['title'][:55]}** :red[[🚨 LỖI]]" if v['title'] else f"*Video_{v['platform_video_id']}* :red[[🚨 LỖI]]")
                        st.caption(f"🚨 Lý do: `{v.get('error_message') or 'Thất bại'}`")
                    else:
                        st.markdown(f"**{v['title'][:60]}**" if v['title'] else f"*Video_{v['platform_video_id']}*")

                with col_size:
                    if raw_path.exists():
                        sz = round(raw_path.stat().st_size / (1024 * 1024), 1)
                        st.caption(f"{sz} MB | {v['downloaded_at'][11:16]}")
                    else:
                        st.caption("Mất file")

                with col_preview:
                    with st.popover("▶️ Xem thử"):
                        if raw_path.exists():
                            st.video(str(raw_path))
                        else:
                            st.error("File không tồn tại")

                with col_btn_r:
                    btn_r_lbl = "🔄 Thử lại" if is_failed else "⚡ Remix"
                    btn_r_type = "primary" if is_failed else "secondary"
                    if st.button(btn_r_lbl, key=f"tbl_r_{vid_id}", help="Lách bản quyền 3-6s", type=btn_r_type):
                        with st.spinner("Đang xử lý…"):
                            try:
                                reset_video_status(vid_id)
                                manager.process_inbox_video(v, mode="remix")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Lỗi: {e}")

                with col_btn_d:
                    if st.button("🎙️ Dịch", key=f"tbl_d_{vid_id}", help="Dịch & Lồng tiếng AI"):
                        with st.spinner("Đang dịch…"):
                            try:
                                reset_video_status(vid_id)
                                manager.process_inbox_video(v, mode="dub")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Lỗi: {e}")

                with col_btn_x:
                    if st.button("🗑️", key=f"tbl_x_{vid_id}", help="Bỏ qua video này"):
                        mark_as_skipped(vid_id)
                        st.rerun()

            st.divider()

    else:
        # CHẾ ĐỘ 2: LƯỚI THẺ 3 CỘT (GRID VIEW)
        cols = st.columns(3)
        for idx, v in enumerate(filtered_videos):
            raw_path = Path(v["raw_video_path"])
            vid_id = v["id"]
            is_checked = vid_id in selected_ids
            is_failed = v.get("processed_status") == "failed"

            with cols[idx % 3]:
                with st.container(border=True):
                    # Checkbox chọn card
                    c_card_chk, c_card_tag = st.columns([1, 3])
                    with c_card_chk:
                        chk_val = st.checkbox("Chọn", value=is_checked, key=f"grid_chk_{vid_id}")
                        if chk_val != is_checked:
                            if chk_val:
                                st.session_state["selected_inbox_ids"].add(vid_id)
                            else:
                                st.session_state["selected_inbox_ids"].discard(vid_id)
                            st.rerun()
                    with c_card_tag:
                        st.caption(f"[{v['platform'].upper()}] • {v['downloaded_at'][:16]}")

                    if raw_path.exists():
                        st.video(str(raw_path))
                    else:
                        st.warning("File không tồn tại")

                    if is_failed:
                        st.error(f"🚨 Lỗi: {v.get('error_message') or 'Thất bại'}")

                    st.markdown(f"**{v['title'][:45]}**" if v['title'] else f"Video_{v['platform_video_id']}")

                    col_b1, col_b2, col_b3 = st.columns([1.5, 1.5, 1])
                    with col_b1:
                        grid_r_lbl = "🔄 Thử lại" if is_failed else "⚡ Remix"
                        grid_r_type = "primary" if is_failed else "secondary"
                        if st.button(grid_r_lbl, key=f"grid_r_{vid_id}", type=grid_r_type, use_container_width=True):
                            try:
                                reset_video_status(vid_id)
                                manager.process_inbox_video(v, mode="remix")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Lỗi: {e}")
                    with col_b2:
                        if st.button("🎙️ Dịch", key=f"grid_d_{vid_id}", type="primary", use_container_width=True):
                            try:
                                reset_video_status(vid_id)
                                manager.process_inbox_video(v, mode="dub")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Lỗi: {e}")
                    with col_b3:
                        if st.button("🗑️", key=f"grid_x_{vid_id}", use_container_width=True):
                            mark_as_skipped(vid_id)
                            st.rerun()


# =============================================================================
# TAB 3: SẴN SÀNG UPLOAD (PUBLISHING HUB)
# =============================================================================
def render_tab_publishing() -> None:
    init_db()
    st.subheader("🚀 3. Kho Video Xuất Bản (Ready to Upload)")
    st.caption("Toàn bộ video thành phẩm đạt chuẩn phát sóng CRF 18 (đã lồng tiếng Việt hoặc lách bản quyền + logo thương hiệu).")

    col_btn1, col_btn2 = st.columns([2, 1], vertical_alignment="bottom")
    with col_btn1:
        if st.button("📂 Mở Thư Mục Chứa Video Thành Phẩm (Explorer)", use_container_width=True):
            READY_DIR.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(str(READY_DIR))
            else:
                st.info(f"Đường dẫn: `{READY_DIR}`")
    with col_btn2:
        filter_status = st.selectbox("Bộ lọc trạng thái:", ["Tất cả thành phẩm", "Chưa đăng", "Đã đăng"])

    include_up = filter_status != "Chưa đăng"
    ready_vids = get_ready_videos(include_uploaded=include_up)

    if filter_status == "Đã đăng":
        ready_vids = [v for v in ready_vids if v.get("is_uploaded") == 1]

    failed_vids = get_failed_videos()

    if not ready_vids:
        if failed_vids:
            st.warning(f"⚠️ Đang có {len(failed_vids)} video bị lỗi khi xử lý! Vui lòng sang Tab **🔍 2. Kiểm Tra & Duyệt Xử Lý** để xem chi tiết lỗi và bấm '🔄 Thử lại'.")
        st.info("Chưa có video thành phẩm nào trong kho. Hãy xử lý video từ Tab **🔍 2. Kiểm Tra & Duyệt Xử Lý** trước!")
        return

    st.markdown(f"**Danh sách: {len(ready_vids)} video thành phẩm đã sẵn sàng**")

    for v in ready_vids:
        out_path = Path(v["processed_video_path"]) if v.get("processed_video_path") else None
        is_up = bool(v.get("is_uploaded"))

        with st.container():
            c_vid, c_desc, c_tool = st.columns([3, 4, 3])

            with c_vid:
                if out_path and out_path.exists():
                    st.video(str(out_path))
                else:
                    st.error("Không tìm thấy file thành phẩm trên ổ cứng.")

            with c_desc:
                st.markdown(f"**{v['title']}**")
                st.caption(f"Nguồn: `[{v['platform'].upper()}]` | ID: `{v['platform_video_id']}`")
                if out_path and out_path.exists():
                    sz = round(out_path.stat().st_size / (1024 * 1024), 1)
                    st.caption(f"📁 Tên file: `{out_path.name}` ({sz} MB)")
                if is_up:
                    st.success(f"✅ Đã đăng lúc: {v.get('uploaded_at', '')[:19]}")
                else:
                    st.warning("⏳ Chưa đăng")

            with c_tool:
                st.markdown("**Thao tác xuất bản:**")
                if not is_up:
                    if st.button("✅ Đánh dấu ĐÃ ĐĂNG", key=f"mark_up_{v['id']}", use_container_width=True):
                        mark_as_uploaded(v["id"], True)
                        st.rerun()
                else:
                    if st.button("🔄 Đánh dấu CHƯA ĐĂNG", key=f"unmark_up_{v['id']}", use_container_width=True):
                        mark_as_uploaded(v["id"], False)
                        st.rerun()

                if out_path and out_path.exists() and sys.platform == "win32":
                    if st.button("▶️ Mở xem trên máy (Player)", key=f"open_ext_{v['id']}", use_container_width=True):
                        os.startfile(str(out_path))

                if out_path and out_path.exists():
                    try:
                        with open(out_path, "rb") as f:
                            file_bytes = f.read()
                        st.download_button(
                            "⬇️ Tải file về máy",
                            data=file_bytes,
                            file_name=out_path.name,
                            mime="video/mp4",
                            key=f"dl_btn_{v['id']}",
                            use_container_width=True,
                        )
                    except Exception as e:
                        st.caption(f"Không thể đọc file: {e}")

                if st.button("🔄 Đưa về Inbox (Xử lý lại)", key=f"re_inbox_{v['id']}", use_container_width=True):
                    reset_video_status(v["id"])
                    st.rerun()

                if st.button("🗑️ Xóa bản ghi", key=f"del_pub_{v['id']}", use_container_width=True):
                    delete_downloaded_video(v["id"])
                    st.rerun()

        st.divider()


# =============================================================================
# TAB 4: CẤU HÌNH BỘ LỌC & THƯƠNG HIỆU (SETTINGS & BRANDING - AN TOÀN TUYỆT ĐỐI)
# =============================================================================
def render_tab_settings() -> None:
    st.subheader("🏷️ 4. Cấu Hình Bộ Lọc & Thương Hiệu (Settings & Branding)")
    st.caption("Cấu hình trước một lần: Mẫu logo mờ chuyển động, bộ lọc lách bản quyền, giọng đọc AI và API Keys.")

    cfg = load_settings()

    with st.form("settings_form"):
        # 4.1. Lớp giáp lách bản quyền & Logo
        st.markdown("#### 🛡️ 1. Lớp Giáp Lách Bản Quyền & Logo Thương Hiệu")
        col_ad1, col_ad2 = st.columns(2)
        with col_ad1:
            cfg["anti_video"] = st.checkbox(
                "Lọc cấu trúc hình ảnh (pHash / DCT Disruptor)",
                value=cfg.get("anti_video", True),
                help="Cắt vi mô 1.5%, tái nội suy Lanczos, chuẩn hóa setsar=1, Micro-EQ và cấy hạt film grain 2.5% động.",
            )
        with col_ad2:
            cfg["anti_audio"] = st.checkbox(
                "Biến điệu âm thanh gốc (Acoustic Spectrogram Disruptor)",
                value=cfg.get("anti_audio", True),
                help="Đẩy cao độ pitch +2.5% kết hợp bù tốc độ atempo=1/1.025 và Parametric EQ làm lệch phổ âm thanh gốc.",
            )

        # Cấu hình Logo
        st.markdown("**🏷️ Logo nhận diện thương hiệu chuyển động**")
        cfg["watermark_enabled"] = st.checkbox("Bật chèn Logo chuyển động", value=cfg.get("watermark_enabled", True))
        c_wm1, c_wm2, c_wm3 = st.columns(3)
        with c_wm1:
            cfg["watermark_text"] = st.text_input("Nội dung chữ Logo", value=cfg.get("watermark_text", "KEN VIDEO"))
        with c_wm2:
            cfg["watermark_opacity"] = st.slider(
                "Độ mờ (Opacity)",
                min_value=0.05,
                max_value=0.50,
                value=float(cfg.get("watermark_opacity", 0.18)),
                step=0.01,
                help="18% là độ mờ chuẩn vàng: người xem nhìn rõ nội dung nhưng bot AI không so khớp được.",
            )
        with c_wm3:
            motion_choices = {
                "drift": "Lượn sóng (Drift)",
                "bounce": "Bật nảy (DVD)",
                "scroll": "Chạy ngang",
                "top_right": "Cố định trên-phải",
                "bottom_right": "Cố định dưới-phải",
            }
            m_keys = list(motion_choices.keys())
            cur_m = cfg.get("watermark_motion", "drift")
            m_idx = m_keys.index(cur_m) if cur_m in m_keys else 0
            cfg["watermark_motion"] = st.selectbox(
                "Kiểu di chuyển",
                options=m_keys,
                format_func=lambda x: motion_choices[x],
                index=m_idx,
            )

        st.markdown("---")

        # 4.2. Dịch thuật & Giọng đọc AI (Tra cứu index an toàn)
        st.markdown("#### 🎙️ 2. Dịch Thuật & Giọng Đọc AI Mặc Định")
        c_l1, c_l2 = st.columns(2)
        with c_l1:
            src_keys = list(LANGUAGES.keys())
            cur_src = cfg.get("source_lang", "zh-CN")
            if cur_src == "zh" or cur_src not in src_keys:
                cur_src = "zh-CN" if "zh-CN" in src_keys else src_keys[0]
            src_idx = src_keys.index(cur_src) if cur_src in src_keys else 0

            cfg["source_lang"] = st.selectbox(
                "Ngôn ngữ gốc video:",
                options=src_keys,
                format_func=lambda x: LANGUAGES.get(x, x),
                index=src_idx,
            )
        with c_l2:
            tgt_list = [k for k in LANGUAGES.keys() if k != "auto"]
            cur_tgt = cfg.get("target_lang", "vi")
            if cur_tgt not in tgt_list:
                cur_tgt = "vi" if "vi" in tgt_list else tgt_list[0]
            tgt_idx = tgt_list.index(cur_tgt) if cur_tgt in tgt_list else 0

            cfg["target_lang"] = st.selectbox(
                "Ngôn ngữ đích (Dịch sang):",
                options=tgt_list,
                format_func=lambda x: LANGUAGES.get(x, x),
                index=tgt_idx,
            )

        c_v1, c_v2 = st.columns(2)
        with c_v1:
            all_voices = list(EDGE_VOICE_ALTERNATES.get("vi", [])) + list(VIENEU_VOICES)
            cur_voice = cfg.get("voice", "vi-VN-HoaiMyNeural")
            v_idx = all_voices.index(cur_voice) if cur_voice in all_voices else 0
            cfg["voice"] = st.selectbox("Giọng đọc mặc định:", options=all_voices, index=v_idx)
        with c_v2:
            cfg["bilingual"] = st.checkbox("Mặc định phụ đề song ngữ", value=cfg.get("bilingual", False))

        st.markdown("---")

        # 4.3. Chất lượng xuất & Phần cứng
        st.markdown("#### ⚙️ 3. Chất Lượng Xuất Video & Phần Cứng")
        c_q1, c_q2 = st.columns(2)
        with c_q1:
            quality_opts = {
                "high": "💎 Siêu nét (CRF 18 - 100% gốc, Khuyên dùng)",
                "medium": "⚖️ Cân bằng dung lượng (CRF 22)",
                "gpu": "⚡ Tăng tốc GPU (h264_mf Bitrate 25M)",
            }
            q_keys = list(quality_opts.keys())
            cur_q = cfg.get("video_quality", "high")
            q_idx = q_keys.index(cur_q) if cur_q in q_keys else 0
            cfg["video_quality"] = st.selectbox(
                "Chất lượng nén video:",
                options=q_keys,
                format_func=lambda x: quality_opts[x],
                index=q_idx,
            )
        with c_q2:
            wh_opts = list(WHISPER_MODELS.keys())
            cur_wh = cfg.get("model_size", "medium")
            wh_idx = wh_opts.index(cur_wh) if cur_wh in wh_opts else 0
            cfg["model_size"] = st.selectbox(
                "Whisper Model:",
                options=wh_opts,
                index=wh_idx,
            )

        submit_save = st.form_submit_button("💾 LƯU CẤU HÌNH THƯƠNG HIỆU & HỆ THỐNG", use_container_width=True)
        if submit_save:
            save_settings(cfg)
            st.success("✅ Đã lưu cấu hình thành công! Mọi tác vụ sẽ tự động sử dụng thiết lập này.")
            st.rerun()

    # Quản lý Gemini Keys & Cookies ngoài form
    with st.expander("🔑 Quản lý Gemini API Keys & Cookies nền tảng"):
        rotator = get_shared_rotator()
        st.write(f"• **Gemini API:** Đang có **{rotator.total_keys} keys** hoạt động luân phiên (file `gemini_keys.txt`).")
        st.write("• **Cookies:** Các file cookie được tự động nhận diện trong thư mục `cookies/`:")
        st.code("cookies/\n  ├── douyin_cookies.txt\n  ├── bilibili_cookies.txt\n  ├── facebook_cookies.txt\n  └── instagram_cookies.txt")
