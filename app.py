#!/usr/bin/env python3
"""Giao diện Streamlit — Hỗ trợ Dịch hàng loạt (Thư mục) và Dịch từng video đơn lẻ."""

from __future__ import annotations

import gc
import importlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import streamlit as st

from src.config import (
    EDGE_VOICE_ALTERNATES,
    EDGE_VOICE_MAP,
    LANGUAGES,
    OUTPUT_DIR,
    VIENEU_VOICES,
    WHISPER_MODELS,
)
from src.gemini_rotator import get_shared_rotator
import src.pipeline
importlib.reload(src.pipeline)
from src.pipeline import VideoTranslatePipeline

st.set_page_config(
    page_title="Dịch Video Tự Động",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: "Be Vietnam Pro", sans-serif; }
.hero {
    background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 55%, #0ea5e9 160%);
    color: #f8fafc;
    padding: 1.4rem 1.6rem;
    border-radius: 16px;
    margin-bottom: 1.2rem;
}
.hero h1 { font-size: 1.85rem; margin: 0 0 .3rem 0; letter-spacing: -.02em; }
.hero p { margin: 0; opacity: .88; font-size: 0.95rem; }
.stProgress > div > div > div { background: linear-gradient(90deg, #38bdf8, #22c55e); }
div[data-testid="stMetric"] {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: .4rem .8rem;
}
.badge-key {
    background: #e0f2fe;
    color: #0369a1;
    padding: 4px 10px;
    border-radius: 8px;
    font-size: 0.85rem;
    font-weight: 600;
    display: inline-block;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

st.markdown(
    """
<div class="hero">
  <h1>🎬 Hệ Thống Dịch Video Tự Động</h1>
  <p>Nhận dạng giọng nói (Whisper GPU) → Dịch thuật thông minh (Gemini Round-Robin) → Lồng tiếng & Khớp miệng → Ghép phụ đề cứng (Hardsub).</p>
</div>
""",
    unsafe_allow_html=True,
)

# ==========================================
# SIDEBAR: BẢNG ĐIỀU KHIỂN HỆ THỐNG
# ==========================================
with st.sidebar:
    st.markdown("### 🎛️ BẢNG ĐIỀU KHIỂN")

    # ----------------------------------------------------
    # PHẦN 1: CHẾ ĐỘ HOẠT ĐỘNG
    # ----------------------------------------------------
    mode_labels = {
        "dub": "🎙️ Lồng tiếng & Phụ đề (Tự động hoàn toàn)",
        "remix": "⚡ Lách Bản Quyền & Logo (Không dịch)",
        "hard": "📝 Chỉ in phụ đề cứng (Giữ tiếng gốc)",
        "soft": "💬 Nhúng phụ đề mềm (Bật/tắt trong player)",
        "srt": "📄 Chỉ xuất file phụ đề SRT",
    }
    mode = st.selectbox(
        "1️⃣ Chế độ hoạt động",
        options=list(mode_labels.keys()),
        format_func=lambda k: mode_labels[k],
        index=0,
        help="Chọn tác vụ bạn muốn thực hiện cho video.",
    )

    # Giá trị mặc định an toàn cho các biến
    lang_items = [(k, v) for k, v in LANGUAGES.items()]
    src_keys = [k for k, _ in lang_items]
    tgt_keys = [k for k in src_keys if k != "auto"]

    source_lang = "zh"
    target_lang = "vi"
    bilingual = False
    voice = None
    fit_timing = True
    resolve_overlap = True
    max_overlap_tempo = 1.85
    burn_sub = False
    font_size = 11
    sub_style = "white_box"

    # ----------------------------------------------------
    # PHẦN 2: DỊCH THUẬT & NGÔN NGỮ (Ẩn nếu chọn Remix)
    # ----------------------------------------------------
    if mode != "remix":
        st.markdown("---")
        st.markdown("**2️⃣ Ngôn ngữ & Dịch thuật**")
        col_l1, col_l2 = st.columns(2)
        with col_l1:
            source_lang = st.selectbox(
                "Ngôn ngữ gốc",
                options=src_keys,
                format_func=lambda k: LANGUAGES[k],
                index=src_keys.index("zh") if "zh" in src_keys else 0,
            )
        with col_l2:
            target_lang = st.selectbox(
                "Ngôn ngữ đích",
                options=tgt_keys,
                format_func=lambda k: LANGUAGES[k],
                index=tgt_keys.index("vi") if "vi" in tgt_keys else 0,
            )

        bilingual = st.checkbox(
            "Phụ đề song ngữ (Gốc + Đích)",
            value=False,
            disabled=mode == "srt",
            help="Hiển thị cả dòng thoại gốc và dòng dịch tiếng Việt.",
        )

        rotator = get_shared_rotator()
        if rotator.total_keys > 0:
            st.caption(f"🔑 **{rotator.total_keys} Gemini API Key** sẵn sàng (Round-Robin luân phiên).")
        else:
            st.caption("⚠️ Chưa nạp key trong `gemini_keys.txt` (Đang dùng Google Translate).")

    # ----------------------------------------------------
    # PHẦN 3: GIỌNG ĐỌC AI & KHỚP KHẨU HÌNH (Chỉ khi Dub)
    # ----------------------------------------------------
    if mode == "dub":
        st.markdown("---")
        st.markdown("**3️⃣ Giọng đọc AI & Khớp nhịp**")
        if target_lang == "vi":
            voices = list(EDGE_VOICE_ALTERNATES.get("vi", [])) + list(VIENEU_VOICES)
        else:
            voices = EDGE_VOICE_ALTERNATES.get(target_lang) or [
                EDGE_VOICE_MAP.get(target_lang, "en-US-JennyNeural")
            ]
        voice = st.selectbox("Giọng đọc AI", options=voices, index=0)

        with st.expander("⏱️ Căn chỉnh nhịp & Tránh chồng câu", expanded=False):
            fit_timing = st.checkbox("Khớp nhịp thoại gốc (kéo/nén tốc độ)", value=True)
            resolve_overlap = st.checkbox(
                "Tự động tăng tốc câu trước nếu chồng lấn",
                value=True,
            )
            max_overlap_tempo = st.slider(
                "Trần tăng tốc khi chồng câu",
                min_value=1.20,
                max_value=2.00,
                value=1.85,
                step=0.05,
                disabled=not resolve_overlap,
            )

    # ----------------------------------------------------
    # PHẦN 4: PHỤ ĐỀ (SUBTITLES)
    # ----------------------------------------------------
    if mode in ("dub", "hard", "soft"):
        st.markdown("---")
        st.markdown("**4️⃣ Tùy biến Phụ đề**")
        if mode == "dub":
            burn_sub = st.checkbox(
                "In phụ đề cứng lên video (Hardsub)",
                value=True,
                help="In chữ phụ đề trực tiếp lên hình ảnh để đăng TikTok/Reels.",
            )
        elif mode == "hard":
            burn_sub = True
        else:
            burn_sub = False

        if burn_sub:
            col_sb1, col_sb2 = st.columns([1, 2])
            with col_sb1:
                font_size = st.number_input(
                    "Cỡ chữ",
                    min_value=7,
                    max_value=24,
                    value=11,
                    help="Cỡ 11 nhỏ gọn chuẩn mắt người xem.",
                )
            with col_sb2:
                sub_style_options = {
                    "white_box": "Chữ đen - Nền trắng mờ",
                    "black_box": "Chữ trắng - Nền đen mờ",
                    "classic": "Chữ trắng viền đen",
                }
                sub_style = st.selectbox(
                    "Kiểu nền",
                    options=list(sub_style_options.keys()),
                    format_func=lambda k: sub_style_options[k],
                    index=0,
                )

    # ----------------------------------------------------
    # PHẦN 5: LÁCH BẢN QUYỀN & LOGO
    # ----------------------------------------------------
    st.markdown("---")
    st.markdown("**🛡️ Lách Bản Quyền & Watermark**")

    col_anti1, col_anti2 = st.columns(2)
    with col_anti1:
        anti_video = st.checkbox(
            "Lọc hình (pHash)",
            value=True,
            help="Kỹ thuật 1: Crop 1.5% + Grain điện ảnh + Micro EQ phá vỡ mã băm hình ảnh.",
        )
    with col_anti2:
        anti_audio = st.checkbox(
            "Lệch âm thanh",
            value=True,
            help="Kỹ thuật 4: Đẩy pitch +2.5% & EQ lệch phổ Spectrogram nhưng vẫn giữ 100% tiếng gốc.",
        )

    with st.expander("🏷️ Cấu hình Logo / Watermark chuyển động", expanded=True):
        watermark_enabled = st.checkbox("Chèn Logo mờ chuyển động", value=True)
        watermark_text = None
        watermark_path = None
        watermark_opacity = 0.18
        watermark_motion = "drift"

        if watermark_enabled:
            wm_type = st.radio("Nguồn Logo", ["Chữ / Tên thương hiệu", "File ảnh Logo (PNG)"], horizontal=True)
            if wm_type == "Chữ / Tên thương hiệu":
                watermark_text = st.text_input("Nội dung chữ", value="KEN VIDEO")
            else:
                uploaded_logo = st.file_uploader(
                    "Tải ảnh Logo (PNG)",
                    type=["png", "jpg", "jpeg", "webp"],
                    key="logo_uploader",
                )
                if uploaded_logo:
                    logo_dest = OUTPUT_DIR / "_uploads" / f"logo_{uploaded_logo.name}"
                    logo_dest.parent.mkdir(parents=True, exist_ok=True)
                    logo_dest.write_bytes(uploaded_logo.getbuffer())
                    watermark_path = str(logo_dest)

            c_wm1, c_wm2 = st.columns(2)
            with c_wm1:
                watermark_opacity = st.slider(
                    "Độ mờ",
                    min_value=0.05,
                    max_value=0.50,
                    value=0.18,
                    step=0.01,
                    format="%.2f",
                    help="18% là độ mờ chuẩn: người xem nhìn rõ nội dung nhưng bot quét không so khớp được.",
                )
            with c_wm2:
                motion_options = {
                    "drift": "Lượn sóng (Drift)",
                    "scroll": "Chạy ngang",
                    "bounce": "Bật nảy (DVD)",
                    "top_right": "Cố định trên-phải",
                    "bottom_right": "Cố định dưới-phải",
                }
                watermark_motion = st.selectbox(
                    "Kiểu chạy",
                    options=list(motion_options.keys()),
                    format_func=lambda k: motion_options[k],
                    index=0,
                )

    # ----------------------------------------------------
    # PHẦN 6: CHẤT LƯỢNG XUẤT VIDEO & PHẦN CỨNG
    # ----------------------------------------------------
    st.markdown("---")
    with st.expander("⚙️ Chất lượng Video & Phần cứng", expanded=False):
        quality_options = {
            "high": "💎 Siêu nét (CRF 18 - 100% gốc, Khuyên dùng)",
            "medium": "⚖️ Cân bằng dung lượng (CRF 22)",
            "gpu": "⚡ Tăng tốc GPU (h264_mf Bitrate 25M)",
        }
        video_quality = st.selectbox(
            "Chất lượng nén video",
            options=list(quality_options.keys()),
            format_func=lambda k: quality_options[k],
            index=0,
            help="CRF 18 giữ 100% chi tiết gốc không vỡ hạt.",
        )

        if mode != "remix":
            c_hw1, c_hw2 = st.columns(2)
            with c_hw1:
                model_size = st.selectbox(
                    "Model Whisper",
                    options=list(WHISPER_MODELS.keys()),
                    index=list(WHISPER_MODELS.keys()).index("medium") if "medium" in WHISPER_MODELS else 0,
                    help="Medium khuyến nghị cho độ chính xác cao.",
                )
            with c_hw2:
                device = st.selectbox(
                    "Thiết bị AI",
                    options=["cuda", "auto", "cpu"],
                    index=0,
                    help="NVIDIA CUDA siêu tốc trên RTX.",
                )
        else:
            model_size = "medium"
            device = "cuda"



# ==========================================
# GIAO DIỆN CHÍNH: 2 TABS
# ==========================================
tab_batch, tab_single = st.tabs(["📁 Dịch hàng loạt (Thư mục)", "🎬 Dịch 1 video (Tải file)"])

SUPPORTED_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v", ".flv", ".ts", ".wmv"}


def _get_target_filename(stem: str, ext: str, mode: str, save_direct: bool) -> str:
    """Trả về tên file video đầu ra dự kiến."""
    if save_direct:
        if mode == "dub":
            return f"{stem}_vi{ext}"
        elif mode == "remix":
            return f"{stem}_remix{ext}"
        elif mode == "hard":
            return f"{stem}_sub{ext}"
        elif mode == "soft":
            return f"{stem}_soft{ext}"
        else:
            return f"{stem}_vi.srt"
    else:
        if mode == "dub":
            return f"{stem}.dub{ext}"
        elif mode == "remix":
            return f"{stem}.remix{ext}"
        elif mode == "hard":
            return f"{stem}.sub{ext}"
        elif mode == "soft":
            return f"{stem}.soft{ext}"
        else:
            return "translated.srt"


# ----------------------------------------------------
# TAB 1: DỊCH HÀNG LOẠT (THƯ MỤC)
# ----------------------------------------------------
with tab_batch:
    st.subheader("Dịch tự động toàn bộ video trong thư mục")

    default_in = str((Path.cwd() / "input_videos").resolve())
    default_out = str((Path.cwd() / "output_batch").resolve())

    col_in, col_out = st.columns(2)
    with col_in:
        input_dir_str = st.text_input(
            "📁 Thư mục video nguồn (Input Folder):",
            value=default_in,
            help="Đường dẫn đến thư mục chứa các video cần dịch trên máy của bạn",
        )
    with col_out:
        output_dir_str = st.text_input(
            "💾 Thư mục lưu kết quả (Output Folder):",
            value=default_out,
            help="Đường dẫn đến thư mục lưu các video và phụ đề sau khi dịch",
        )

    col_opt1, col_opt2 = st.columns(2)
    with col_opt1:
        skip_existing = st.checkbox(
            "Bỏ qua video đã có kết quả (tiết kiệm thời gian & API)",
            value=True,
            help="Nếu video đã có file xuất hoàn chỉnh trong thư mục đích, hệ thống tự động bỏ qua để chuyển sang video tiếp theo.",
        )
    with col_opt2:
        save_direct = st.checkbox(
            "Lưu file kết quả trực tiếp ra thư mục đích (không tạo folder con)",
            value=True,
            help="Lưu thẳng dạng video_vi.mp4, video_vi.srt ra thư mục đích thay vì mỗi video nằm trong một folder riêng.",
        )

    in_dir = Path(input_dir_str.strip().strip('"').strip("'"))
    out_dir = Path(output_dir_str.strip().strip('"').strip("'"))

    video_files: list[Path] = []
    if not in_dir.exists() or not in_dir.is_dir():
        st.warning(f"⚠️ Thư mục nguồn `{in_dir}` hiện chưa tồn tại.")
        if st.button("Tạo thư mục nguồn này ngay", key="btn_create_input_dir"):
            in_dir.mkdir(parents=True, exist_ok=True)
            st.rerun()
    else:
        video_files = [
            f for f in sorted(in_dir.iterdir())
            if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS
        ]

    # Kiểm tra trạng thái từng video
    table_preview_data = []
    ready_count = 0
    done_count = 0

    for idx, vf in enumerate(video_files, start=1):
        target_name = _get_target_filename(vf.stem, vf.suffix or ".mp4", mode, save_direct)
        target_path = (out_dir / target_name) if save_direct else (out_dir / vf.stem / target_name)
        is_done = target_path.exists() and target_path.stat().st_size > 1000
        sz_mb = round(vf.stat().st_size / (1024 * 1024), 1)

        if is_done:
            done_count += 1
            st_text = "⏭️ Đã có kết quả (sẽ bỏ qua)" if skip_existing else "🔄 Đã có kết quả (sẽ dịch lại)"
        else:
            ready_count += 1
            st_text = "⏳ Sẵn sàng dịch"

        table_preview_data.append({
            "STT": idx,
            "Tên Video": vf.name,
            "Kích thước": f"{sz_mb} MB",
            "Trạng thái": st_text,
            "File đầu ra dự kiến": target_name,
        })

    st.markdown(
        f"**📊 Thống kê:** Tìm thấy **{len(video_files)}** video trong thư mục nguồn "
        f"(Sẵn sàng dịch: **{ready_count}** | Đã hoàn thành: **{done_count}**)"
    )

    if video_files:
        with st.expander("👀 Xem danh sách video phát hiện được", expanded=len(video_files) <= 15):
            st.dataframe(pd.DataFrame(table_preview_data), use_container_width=True, hide_index=True)

    col_btn1, col_btn2, col_btn3 = st.columns([2, 1, 1])
    with col_btn1:
        start_batch = st.button(
            "🚀 BẮT ĐẦU DỊCH HÀNG LOẠT",
            type="primary",
            use_container_width=True,
            disabled=len(video_files) == 0,
        )
    with col_btn2:
        if st.button("🔄 Quét lại thư mục", use_container_width=True):
            st.rerun()
    with col_btn3:
        if st.button("📂 Mở thư mục Output", use_container_width=True):
            out_dir.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(str(out_dir))
            else:
                st.info(f"Đường dẫn: `{out_dir}`")

    # XỬ LÝ CHẠY BATCH
    if start_batch and video_files:
        out_dir.mkdir(parents=True, exist_ok=True)
        st.divider()

        batch_header = st.empty()
        overall_bar = st.progress(0)

        cur_video_box = st.container()
        with cur_video_box:
            cur_video_title = st.empty()
            cur_video_bar = st.progress(0)
            cur_video_msg = st.empty()

        st.subheader("📋 Bảng tiến độ theo dõi trực tiếp")
        live_table_ph = st.empty()

        # Dữ liệu bảng theo dõi trực tiếp
        live_rows = []
        for idx, vf in enumerate(video_files, start=1):
            target_name = _get_target_filename(vf.stem, vf.suffix or ".mp4", mode, save_direct)
            target_path = (out_dir / target_name) if save_direct else (out_dir / vf.stem / target_name)
            is_done = target_path.exists() and target_path.stat().st_size > 1000
            sz_mb = round(vf.stat().st_size / (1024 * 1024), 1)

            init_status = "⏭️ Bỏ qua" if (is_done and skip_existing) else "⏳ Chờ xử lý"
            init_time = "Đã có sẵn" if (is_done and skip_existing) else "-"

            live_rows.append({
                "STT": idx,
                "Tên Video": vf.name,
                "Kích thước": f"{sz_mb} MB",
                "Trạng thái": init_status,
                "Thời gian": init_time,
                "Chi tiết": "",
            })

        live_table_ph.dataframe(pd.DataFrame(live_rows), use_container_width=True, hide_index=True)

        # Khởi tạo Pipeline dùng chung (Whisper model được cache trên GPU)
        pipe = VideoTranslatePipeline(model_size=model_size, device=device)

        total_vids = len(video_files)
        success_vids = 0
        skipped_vids = 0
        error_vids = 0
        t_batch_start = time.time()

        for i, vf in enumerate(video_files):
            target_name = _get_target_filename(vf.stem, vf.suffix or ".mp4", mode, save_direct)
            target_path = (out_dir / target_name) if save_direct else (out_dir / vf.stem / target_name)
            is_done = target_path.exists() and target_path.stat().st_size > 1000

            if is_done and skip_existing:
                skipped_vids += 1
                overall_bar.progress((i + 1) / total_vids)
                continue

            # Cập nhật trạng thái đang xử lý
            live_rows[i]["Trạng thái"] = "⚡ Đang xử lý..."
            live_table_ph.dataframe(pd.DataFrame(live_rows), use_container_width=True, hide_index=True)

            batch_header.markdown(f"#### ⏳ Tiến độ hàng loạt: Video **[{i+1}/{total_vids}]** — `{vf.name}`")
            cur_video_title.markdown(f"**🎬 Đang dịch:** `{vf.name}`")
            cur_video_bar.progress(0)
            cur_video_msg.info("Khởi động pipeline...")

            def make_progress_cb(name_str):
                def _cb(msg: str, pct: float):
                    cur_video_bar.progress(min(100, max(0, int(pct * 100))))
                    cur_video_msg.info(f"**[{name_str}]** {msg}")
                return _cb

            t_vid_start = time.time()
            try:
                result = pipe.run(
                    video_path=vf,
                    target_lang=target_lang,
                    source_lang=source_lang,
                    mode=mode,
                    bilingual=bilingual,
                    voice=voice,
                    fit_timing=fit_timing,
                    resolve_overlap=resolve_overlap,
                    max_overlap_tempo=max_overlap_tempo,
                    burn_sub=burn_sub,
                    progress=make_progress_cb(vf.name),
                    output_dir=out_dir,
                    save_direct_to_output_dir=save_direct,
                    font_size=font_size,
                    sub_style=sub_style,
                    watermark_enabled=watermark_enabled,
                    watermark_path=watermark_path,
                    watermark_text=watermark_text,
                    watermark_opacity=watermark_opacity,
                    watermark_motion=watermark_motion,
                    video_quality=video_quality,
                    anti_video=anti_video,
                    anti_audio=anti_audio,
                )
                elapsed = round(time.time() - t_vid_start, 1)
                live_rows[i]["Trạng thái"] = "✅ Hoàn tất"
                live_rows[i]["Thời gian"] = f"{elapsed}s"
                if result.mode == "remix":
                    live_rows[i]["Chi tiết"] = "Xử lý bản quyền & logo (Gốc)"
                else:
                    live_rows[i]["Chi tiết"] = f"{result.segment_count} câu ({result.detected_language})"
                success_vids += 1
            except Exception as exc:
                elapsed = round(time.time() - t_vid_start, 1)
                live_rows[i]["Trạng thái"] = "❌ Thất bại"
                live_rows[i]["Thời gian"] = f"{elapsed}s"
                live_rows[i]["Chi tiết"] = str(exc)[:80]
                error_vids += 1

            live_table_ph.dataframe(pd.DataFrame(live_rows), use_container_width=True, hide_index=True)
            overall_bar.progress((i + 1) / total_vids)
            gc.collect()

        total_elapsed = round(time.time() - t_batch_start, 1)
        cur_video_title.empty()
        cur_video_bar.empty()
        cur_video_msg.empty()
        batch_header.empty()
        overall_bar.progress(100)

        mins = int(total_elapsed // 60)
        secs = int(total_elapsed % 60)
        time_str = f"{mins} phút {secs} giây" if mins > 0 else f"{secs} giây"

        st.balloons()
        st.success(
            f"🎉 **ĐÃ HOÀN TẤT DỊCH TOÀN BỘ VIDEO!**\n\n"
            f"- ✅ Thành công: **{success_vids}** video\n"
            f"- ⏭️ Bỏ qua (đã có sẵn): **{skipped_vids}** video\n"
            f"- ❌ Lỗi: **{error_vids}** video\n"
            f"- ⏱️ Tổng thời gian: **{time_str}**\n\n"
            f"📂 Thư mục kết quả: `{out_dir}`"
        )
        if sys.platform == "win32":
            if st.button("📂 Mở thư mục kết quả ngay", key="btn_open_after_batch"):
                os.startfile(str(out_dir))


# ----------------------------------------------------
# TAB 2: DỊCH 1 VIDEO (TẢI FILE)
# ----------------------------------------------------
with tab_single:
    st.subheader("Dịch và xem trước từng video đơn lẻ")

    uploaded = st.file_uploader(
        "Tải video hoặc audio",
        type=["mp4", "mkv", "mov", "webm", "avi", "m4v", "mp3", "wav", "m4a", "aac"],
        key="single_file_uploader",
    )

    col_a, col_b = st.columns([2, 1])
    with col_a:
        st.caption("Hỗ trợ mp4 / mkv / mov / webm / avi và file âm thanh mp3, wav.")
    with col_b:
        run_single = st.button("Bắt đầu dịch video này", type="primary", use_container_width=True, disabled=uploaded is None)

    single_status = st.empty()
    single_bar = st.progress(0)
    single_result_box = st.container()

    def _save_upload(file) -> Path:
        dest_dir = OUTPUT_DIR / "_uploads"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / file.name
        dest.write_bytes(file.getbuffer())
        return dest

    if run_single and uploaded is not None:
        video_path = _save_upload(uploaded)
        single_status.info(f"Đã nhận file `{video_path.name}` — khởi động pipeline…")

        def single_progress(msg: str, pct: float) -> None:
            single_bar.progress(min(100, int(pct * 100)))
            single_status.info(msg)

        try:
            pipe = VideoTranslatePipeline(model_size=model_size, device=device)
            result = pipe.run(
                video_path=video_path,
                target_lang=target_lang,
                source_lang=source_lang,
                mode=mode,
                bilingual=bilingual,
                voice=voice,
                fit_timing=fit_timing,
                resolve_overlap=resolve_overlap,
                max_overlap_tempo=max_overlap_tempo,
                burn_sub=burn_sub,
                progress=single_progress,
                font_size=font_size,
                sub_style=sub_style,
                watermark_enabled=watermark_enabled,
                watermark_path=watermark_path,
                watermark_text=watermark_text,
                watermark_opacity=watermark_opacity,
                watermark_motion=watermark_motion,
                video_quality=video_quality,
                anti_video=anti_video,
                anti_audio=anti_audio,
            )
        except Exception as exc:
            single_status.error(f"Lỗi: {exc}")
            st.stop()

        single_bar.progress(100)
        single_status.success("Hoàn tất xử lý video.")

        with single_result_box:
            m1, m2, m3 = st.columns(3)
            m1.metric("Ngôn ngữ gốc", result.detected_language)
            m2.metric("Số đoạn thoại", result.segment_count if result.mode != "remix" else "Gốc")
            m3.metric("Chế độ", result.mode)

            if result.srt_translated and Path(result.srt_translated).exists():
                st.subheader("Tải phụ đề")
                c1, c2, c3 = st.columns(3)
                c1.download_button(
                    "SRT đã dịch",
                    data=Path(result.srt_translated).read_bytes(),
                    file_name=Path(result.srt_translated).name,
                    mime="text/plain",
                )
                if result.srt_original and Path(result.srt_original).exists():
                    c2.download_button(
                        "SRT gốc",
                        data=Path(result.srt_original).read_bytes(),
                        file_name=Path(result.srt_original).name,
                        mime="text/plain",
                    )
                if result.srt_bilingual and Path(result.srt_bilingual).exists():
                    c3.download_button(
                        "SRT song ngữ",
                        data=Path(result.srt_bilingual).read_bytes(),
                        file_name=Path(result.srt_bilingual).name,
                        mime="text/plain",
                    )

            if result.output_video and Path(result.output_video).exists():
                st.subheader("Xem & Tải video đã xử lý")
                st.video(result.output_video)
                st.download_button(
                    "Tải video đã xử lý",
                    data=Path(result.output_video).read_bytes(),
                    file_name=Path(result.output_video).name,
                    mime="video/mp4",
                )

            with st.expander("Xem transcript JSON"):
                st.code(Path(result.transcript_json).read_text(encoding="utf-8")[:8000], language="json")
    else:
        if uploaded is None:
            single_status.caption("Chọn video và nhấn **Bắt đầu dịch video này**.")
            single_bar.progress(0)
