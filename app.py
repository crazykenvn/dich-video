#!/usr/bin/env python3
"""Giao diện Quản Lý & Sản Xuất Video Tự Động (Creator Studio UI).

Quy trình 4 bước khép kín:
  [📥 1. Thu Thập Nguồn] ──► [🔍 2. Duyệt & Phân Loại] ──► [🚀 3. Sẵn Sàng Upload] ──► [🏷️ 4. Cài Đặt]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st

from src.downloader.db import init_db
from src.downloader.manager import DownloadManager
from src.downloader.ui import (
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
    initial_sidebar_state="collapsed",
)

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: "Be Vietnam Pro", sans-serif; }

/* Ẩn hoàn toàn left sidebar */
[data-testid="stSidebar"], section[data-testid="stSidebar"] {
    display: none !important;
}

/* Tối ưu khoảng cách đỉnh trang khi không có banner */
.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 2rem !important;
    max-width: 100% !important;
}

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


def main() -> None:
    init_db()
    manager = DownloadManager()

    # =========================================================================
    # GIAO DIỆN CHÍNH: 4 TABS TUẦN TỰ (FULL WIDTH)
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
