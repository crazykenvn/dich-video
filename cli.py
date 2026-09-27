#!/usr/bin/env python3
"""CLI: python cli.py video.mp4 --to vi --mode soft"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import LANGUAGES, WHISPER_MODELS
from src.pipeline import VideoTranslatePipeline


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dich-video",
        description="Dịch video: nhận dạng giọng nói → dịch → phụ đề hoặc lồng tiếng.",
    )
    p.add_argument("video", help="Đường dẫn file video hoặc thư mục chứa nhiều video")
    p.add_argument("--output", default=None, help="Thư mục lưu kết quả")
    p.add_argument("--to", dest="target", default="vi", choices=sorted(k for k in LANGUAGES if k != "auto"))
    p.add_argument("--from", dest="source", default="auto", choices=sorted(LANGUAGES.keys()))
    p.add_argument(
        "--mode",
        default="dub",
        choices=["dub", "remix", "hard", "soft", "srt"],
        help="dub=lồng tiếng + sub cứng | remix=xử lý bản quyền & logo (không dịch) | hard=chỉ ghi chữ lên hình | soft=nhúng phụ đề mềm | srt=chỉ xuất chữ",
    )
    p.add_argument("--model", default="medium", choices=sorted(WHISPER_MODELS.keys()))
    p.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    p.add_argument(
        "--voice",
        default=None,
        help="Giọng VieNeu-TTS hoặc Edge TTS (vd. vi-VN-HoaiMyNeural, vi-VN-NamMinhNeural)",
    )
    p.add_argument("--no-bilingual", action="store_true", help="Phụ đề chỉ ngôn ngữ đích")
    p.add_argument("--no-burn-sub", action="store_true", help="Không in sub cứng lên video khi lồng tiếng")
    p.add_argument("--no-fit-timing", action="store_true", help="Không kéo/nén tốc độ TTS theo khung gốc")
    p.add_argument(
        "--no-resolve-overlap",
        action="store_true",
        help="Tắt phương án A: không tăng tốc câu trước khi chồng câu sau",
    )
    p.add_argument(
        "--max-overlap-tempo",
        type=float,
        default=1.85,
        help="Trần tăng tốc khi phát hiện chồng câu (mặc định 1.85)",
    )
    p.add_argument("--font-size", type=int, default=11, help="Cỡ chữ phụ đề (mặc định: 11)")
    p.add_argument(
        "--sub-style",
        default="white_box",
        choices=["white_box", "black_box", "classic"],
        help="Kiểu nền phụ đề: white_box (chữ đen nền trắng mờ), black_box, classic",
    )
    p.add_argument("--watermark-text", default=None, help="Chèn watermark chữ (vd: @kenvn)")
    p.add_argument("--watermark-image", default=None, help="Đường dẫn file ảnh logo watermark")
    p.add_argument(
        "--watermark-opacity",
        type=float,
        default=0.18,
        help="Độ mờ watermark (0.05 - 0.50, mặc định: 0.18)",
    )
    p.add_argument(
        "--watermark-motion",
        default="drift",
        choices=["drift", "scroll", "bounce", "top_right", "bottom_right"],
        help="Chuyển động watermark: drift (lượn sóng), scroll, bounce, top_right, bottom_right",
    )
    p.add_argument(
        "--video-quality",
        default="high",
        choices=["high", "medium", "gpu"],
        help="Chất lượng encode video: high (CRF 18 siêu nét - 100% chi tiết gốc), medium (CRF 22), gpu (h264_mf 25M)",
    )
    p.add_argument(
        "--anti-video",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Bật/tắt bộ lọc hình ảnh chống quét bản quyền (mặc định: bật)",
    )
    p.add_argument(
        "--anti-audio",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Bật/tắt biến điệu âm thanh gốc chống quét bản quyền (mặc định: bật)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target_path = Path(args.video).expanduser().resolve()
    if not target_path.exists():
        print(f"Không tìm thấy file hoặc thư mục: {target_path}", file=sys.stderr)
        return 1

    SUPPORTED_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v", ".flv", ".ts", ".wmv"}
    if target_path.is_dir():
        video_files = [f for f in sorted(target_path.iterdir()) if f.is_file() and f.suffix.lower() in SUPPORTED_EXTS]
        if not video_files:
            print(f"Không tìm thấy video nào trong thư mục: {target_path}")
            return 0
    else:
        video_files = [target_path]

    pipe = VideoTranslatePipeline(model_size=args.model, device=args.device)

    total = len(video_files)
    print(f"Đã tìm thấy {total} video cần xử lý.")
    print(f"Dịch  : {args.source} → {args.target} | mode={args.mode} | model={args.model} | device={args.device}")

    has_wm = bool(args.watermark_text or args.watermark_image)

    for idx, vf in enumerate(video_files, 1):
        print(f"\n[{idx}/{total}] Đang xử lý: {vf.name}")

        def progress(msg: str, pct: float) -> None:
            bar = int(pct * 24)
            print(f"\r  [{'█' * bar}{'░' * (24 - bar)}] {pct:5.0%}  {msg:<45}", end="", flush=True)

        try:
            result = pipe.run(
                video_path=vf,
                target_lang=args.target,
                source_lang=args.source,
                mode=args.mode,
                bilingual=not args.no_bilingual,
                voice=args.voice,
                fit_timing=not args.no_fit_timing,
                resolve_overlap=not args.no_resolve_overlap,
                max_overlap_tempo=args.max_overlap_tempo,
                burn_sub=not args.no_burn_sub,
                progress=progress,
                output_dir=Path(args.output) if args.output else None,
                save_direct_to_output_dir=True if args.output else False,
                font_size=args.font_size,
                sub_style=args.sub_style,
                watermark_enabled=has_wm,
                watermark_path=args.watermark_image,
                watermark_text=args.watermark_text,
                watermark_opacity=args.watermark_opacity,
                watermark_motion=args.watermark_motion,
                video_quality=args.video_quality,
                anti_video=args.anti_video,
                anti_audio=args.anti_audio,
            )
            if result.mode == "remix":
                print(f"\n  ✓ Xong (Chế độ Remix/Bản quyền) -> {result.output_video}")
            else:
                print(f"\n  ✓ Xong: {result.segment_count} câu ({result.detected_language}) -> {result.output_video}")
        except Exception as exc:
            print(f"\n  ✗ Lỗi: {exc}", file=sys.stderr)

    print("\n--- Hoàn tất xử lý hàng loạt ---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
