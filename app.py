#!/usr/bin/env python3
"""Giao diện Quản Lý & Sản Xuất Video Tự Động (Creator Studio UI).

Quy trình 4 bước khép kín:
  [📥 1. Thu Thập Nguồn] ──► [🔍 2. Duyệt & Phân Loại] ──► [🚀 3. Sẵn Sàng Upload] ──► [🏷️ 4. Cài Đặt]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

from src.config import OUTPUT_DIR, PROJECT_ROOT
from src.gemini_rotator import get_shared_rotator
from src.downloader.db import get_inbox_videos, get_ready_videos, init_db
from src.downloader.manager import DownloadManager
from src.downloader.settings import load_settings
from src.downloader.ui import (
    READY_DIR,
    render_tab_ingestion,
    render_tab_publishing,
    render_tab_settings,
    render_tab_triage,
)

# Cấu hình trang Streamlit
st.set_page_config(
    page_title="Creator Video Studio",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: "Be Vietnam Pro", sans-serif; }
.hero-banner {
    background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 55%, #0ea5e9 160%);
    color: #f8fafc;
    padding: 1.2rem 1.6rem;
    border-radius: 14px;
    margin-bottom: 1.2rem;
    box-shadow: 0 4px 20px rgba(0,0,0,0.08);
}
.hero-banner h1 { font-size: 1.75rem; margin: 0 0 .2rem 0; font-weight: 700; }
.hero-banner p { margin: 0; opacity: .88; font-size: 0.95rem; }
.stProgress > div > div > div { background: linear-gradient(90deg, #38bdf8, #22c55e); }
div[data-testid="stMetric"] {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 12px;
    padding: .6rem .9rem;
}
div[data-testid="stMetric"] label, div[data-testid="stMetric"] p {
    color: #94a3b8 !important;
    font-size: 0.85rem !important;
}
div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
    color: #38bdf8 !important;
    font-weight: 700 !important;
    font-size: 1.35rem !important;
}
.badge-status {
    padding: 3px 8px;
    border-radius: 6px;
    font-size: 0.8rem;
    font-weight: 600;
}

</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def check_gpu_cuda() -> str:
    """Kiểm tra card đồ họa CUDA trên máy."""
    try:
        import torch
        if torch.cuda.is_available():
            return f"🟢 CUDA ({torch.cuda.get_device_name(0)})"
    except Exception:
        pass
    return "⚡ Tăng tốc phần cứng (MediaFoundation / CPU)"


def main() -> None:
    init_db()
    manager = DownloadManager()

    # Thống kê nhanh cho Sidebar
    inbox_vids = get_inbox_videos()
    ready_vids = get_ready_videos()
    rotator = get_shared_rotator()

    # =========================================================================
    # SIDEBAR: BẢNG THEO DÕI HỆ THỐNG (COMPACT SYSTEM MONITOR)
    # =========================================================================
    with st.sidebar:
        st.markdown("### 🎛️ SYSTEM MONITOR")
        st.caption("Trạng thái động cơ & Hàng đợi")

        # Widget Phần cứng
        st.markdown(f"**Phần cứng:**\n`{check_gpu_cuda()}`")

        # Widget Gemini Keys
        if rotator.total_keys > 0:
            st.markdown(f"**Gemini API:** 🟢 `{rotator.total_keys} Keys (Round-Robin)`")
        else:
            st.markdown("**Gemini API:** ⚠️ `0 Key (Dùng Google Translate)`")

        st.markdown("---")

        # Đồng hồ số lượng
        st.metric("📥 Inbox chờ duyệt", f"{len(inbox_vids)} video")
        st.metric("🚀 Sẵn sàng Upload", f"{len(ready_vids)} video")

        st.markdown("---")

        # Nút thao tác nhanh
        st.markdown("**Thao tác nhanh:**")
        if st.button("📂 Mở Kho Thành Phẩm", use_container_width=True):
            READY_DIR.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(str(READY_DIR))
            else:
                st.info(f"`{READY_DIR}`")

        if st.button("🔄 Làm Mới Dữ Liệu", use_container_width=True):
            st.rerun()

    # =========================================================================
    # HEADER BANNER
    # =========================================================================
    st.markdown(
        """
<div class="hero-banner">
  <h1>🎬 Video Content Studio</h1>
  <p>Quy trình sản xuất khép kín: <b>Thu Thập Nguồn Vào</b> ➔ <b>Kiểm Tra & Phân Loại</b> ➔ <b>Xử Lý Lách Bản Quyền / Dịch AI</b> ➔ <b>Kho Sẵn Sàng Upload</b></p>
</div>
""",
        unsafe_allow_html=True,
    )

    # =========================================================================
    # GIAO DIỆN CHÍNH: 4 TABS TUẦN TỰ
    # =========================================================================
    tab1, tab2, tab3, tab4 = st.tabs([
        "📥 1. Thu Thập Nguồn Vào",
        "🔍 2. Kiểm Tra & Duyệt Xử Lý",
        "🚀 3. Kho Sẵn Sàng Upload",
        "🏷️ 4. Cấu Hình & Thương Hiệu",
    ])

    with tab1:
        render_tab_ingestion(manager=manager)

    with tab2:
        render_tab_triage(manager=manager)

    with tab3:
        render_tab_publishing()

    with tab4:
        render_tab_settings()


if __name__ == "__main__":
    main()
