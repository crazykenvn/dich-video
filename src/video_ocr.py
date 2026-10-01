"""Module Video OCR: Phát hiện, bóc tách và dịch sub cứng / text rải rác trên video sang tiếng Việt.

Sử dụng RapidOCR (PP-OCRv4 ONNX) tăng tốc GPU để đọc chữ Hán trên từng khung hình,
kết hợp thuật toán Temporal IoU để gom cụm các mốc thời gian xuất hiện,
và Gemini Rotator để dịch chính xác theo ngữ cảnh sang tiếng Việt.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

from .config import OUTPUT_DIR
from .gemini_rotator import GeminiRotator, get_shared_rotator
from .media import duration_seconds, get_ffmpeg_bin, get_video_resolution

logger = logging.getLogger(__name__)

# Singleton RapidOCR engine
_GLOBAL_OCR_ENGINE: Any = None


def get_ocr_engine() -> Any:
    """Khởi tạo và trả về instance singleton RapidOCR."""
    global _GLOBAL_OCR_ENGINE
    if _GLOBAL_OCR_ENGINE is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            # Khởi tạo mặc định dùng ONNXRuntime
            _GLOBAL_OCR_ENGINE = RapidOCR()
            logger.info("[video_ocr] Đã khởi tạo thành công RapidOCR Engine.")
        except Exception as e:
            logger.error(f"[video_ocr] Lỗi khởi tạo RapidOCR: {e}")
            raise
    return _GLOBAL_OCR_ENGINE


@dataclass
class VideoTextBlock:
    id: str
    zone: str                          # "bottom_sub" | "top_title" | "body_overlay"
    start: float                       # Giây bắt đầu xuất hiện
    end: float                         # Giây kết thúc
    box: dict[str, int]                # {"x": int, "y": int, "w": int, "h": int}
    text_zh: str                       # Chữ tiếng Trung gốc
    text_vi: str = ""                  # Bản dịch tiếng Việt
    confidence: float = 0.90           # Độ tin cậy OCR
    style: str = "blur_box"            # "blur_box" | "solid_black" | "stroke_only"
    is_enabled: bool = True            # Bật / tắt che và dịch khối chữ này

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VideoTextBlock:
        return cls(
            id=data.get("id", ""),
            zone=data.get("zone", "body_overlay"),
            start=float(data.get("start", 0.0)),
            end=float(data.get("end", 0.0)),
            box=data.get("box", {"x": 0, "y": 0, "w": 100, "h": 50}),
            text_zh=data.get("text_zh", ""),
            text_vi=data.get("text_vi", ""),
            confidence=float(data.get("confidence", 0.9)),
            style=data.get("style", "blur_box"),
            is_enabled=bool(data.get("is_enabled", True)),
        )


def compute_iou(box1: dict[str, int], box2: dict[str, int]) -> float:
    """Tính Intersection over Union (IoU) giữa 2 bounding box."""
    x1 = max(box1["x"], box2["x"])
    y1 = max(box1["y"], box2["y"])
    x2 = min(box1["x"] + box1["w"], box2["x"] + box2["w"])
    y2 = min(box1["y"] + box1["h"], box2["y"] + box2["h"])

    inter_w = max(0, x2 - x1)
    inter_h = max(0, y2 - y1)
    inter_area = inter_w * inter_h

    area1 = box1["w"] * box1["h"]
    area2 = box2["w"] * box2["h"]
    union_area = area1 + area2 - inter_area

    if union_area <= 0:
        return 0.0
    return inter_area / float(union_area)


def text_similarity(t1: str, t2: str) -> float:
    """Đo độ tương đồng chuỗi giữa 2 đoạn text."""
    s1 = t1.strip()
    s2 = t2.strip()
    if not s1 or not s2:
        return 0.0
    if s1 == s2 or s1 in s2 or s2 in s1:
        return 1.0
    return SequenceMatcher(None, s1, s2).ratio()


def polygon_to_bbox(polygon: list[list[float]], scale_x: float = 1.0, scale_y: float = 1.0) -> dict[str, int]:
    """Chuyển đổi 4 tọa độ polygon [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] thành bounding box {x, y, w, h}."""
    xs = [pt[0] * scale_x for pt in polygon]
    ys = [pt[1] * scale_y for pt in polygon]
    min_x = max(0, int(round(min(xs))))
    max_x = int(round(max(xs)))
    min_y = max(0, int(round(min(ys))))
    max_y = int(round(max(ys)))
    return {
        "x": min_x,
        "y": min_y,
        "w": max(10, max_x - min_x),
        "h": max(10, max_y - min_y),
    }


def classify_zone(box: dict[str, int], video_height: int) -> str:
    """Phân loại vùng hiển thị của chữ: đáy (sub thoại), trên cùng (tiêu đề), hoặc giữa (chữ rải rác)."""
    mid_y = box["y"] + (box["h"] / 2.0)
    if mid_y > 0.72 * video_height:
        return "bottom_sub"
    elif mid_y < 0.28 * video_height:
        return "top_title"
    return "body_overlay"


class VideoOCRScanner:
    """Bộ quét Video OCR trích xuất và gom cụm chữ cứng theo thời gian."""

    def __init__(
        self,
        sample_fps: float = 2.0,
        min_confidence: float = 0.60,
        min_box_w: int = 24,
        min_box_h: int = 14,
        iou_threshold: float = 0.50,
        rotator: GeminiRotator | None = None,
    ):
        self.sample_fps = sample_fps
        self.min_confidence = min_confidence
        self.min_box_w = min_box_w
        self.min_box_h = min_box_h
        self.iou_threshold = iou_threshold
        self.rotator = rotator if rotator is not None else get_shared_rotator()

    def scan_video(
        self,
        video_path: Path,
        max_duration: float | None = None,
        progress_callback: Callable[[str, float], None] | None = None,
    ) -> list[VideoTextBlock]:
        """Quét video, bóc tách toàn bộ khối chữ và dịch sang tiếng Việt."""
        video_path = Path(video_path).resolve()
        if not video_path.exists():
            raise FileNotFoundError(f"Video không tồn tại: {video_path}")

        vw, vh = get_video_resolution(video_path)
        total_dur = duration_seconds(video_path)
        if total_dur <= 0:
            total_dur = 15.0

        if progress_callback:
            progress_callback("Đang trích xuất khung hình video...", 10)

        # 1. Trích xuất khung hình định kỳ theo sample_fps (tối ưu hóa độ phân giải 960p)
        import hashlib
        v_hash = hashlib.md5(str(video_path).encode("utf-8", errors="replace")).hexdigest()[:12]
        frames_dir = OUTPUT_DIR / "temp" / "ocr_frames" / f"ocr_{v_hash}"
        if frames_dir.exists():
            shutil.rmtree(frames_dir, ignore_errors=True)
        frames_dir.mkdir(parents=True, exist_ok=True)

        target_scale = "scale=-2:960" if vh > 960 else "scale=-2:trunc(ih/2)*2"
        cmd = [get_ffmpeg_bin(), "-y"]
        if max_duration and max_duration > 0:
            cmd.extend(["-t", str(max_duration)])
        cmd.extend([
            "-i", str(video_path),
            "-vf", f"fps={self.sample_fps},{target_scale}",
            "-q:v", "2",
            str(frames_dir / "frame_%04d.jpg"),
        ])
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        frame_files = sorted(list(frames_dir.glob("frame_*.jpg")))
        total_frames = len(frame_files)
        if total_frames == 0:
            logger.warning("[video_ocr] Không trích xuất được khung hình nào từ video.")
            return []

        # Đo tỉ lệ scale giữa frame ảnh OCR và kích thước video gốc
        import cv2
        first_img = cv2.imread(str(frame_files[0]))
        if first_img is None:
            # Fallback nếu cv2.imread gặp lỗi đường dẫn
            import numpy as np
            first_img = cv2.imdecode(np.fromfile(str(frame_files[0]), dtype=np.uint8), cv2.IMREAD_COLOR)

        f_h, f_w = first_img.shape[:2] if first_img is not None else (vh, vw)
        scale_x = float(vw) / float(f_w) if f_w > 0 else 1.0
        scale_y = float(vh) / float(f_h) if f_h > 0 else 1.0

        if progress_callback:
            progress_callback(f"RapidOCR đang quét {total_frames} khung hình...", 30)

        engine = get_ocr_engine()
        step_sec = 1.0 / self.sample_fps

        # 2. Quét OCR từng frame và gom cụm theo thời gian (Temporal IoU)
        active_tracks: list[dict[str, Any]] = []
        completed_tracks: list[dict[str, Any]] = []

        for idx, f_path in enumerate(frame_files):
            t_curr = idx * step_sec
            try:
                ocr_results, _ = engine(str(f_path))
            except Exception as e:
                logger.error(f"[video_ocr] Lỗi OCR tại frame {idx}: {e}")
                ocr_results = []

            # Lọc các detection hợp lệ
            current_detections: list[dict[str, Any]] = []
            for res in ocr_results or []:
                polygon, text, score_raw = res
                try:
                    score = float(score_raw)
                except Exception:
                    score = 0.8
                if score < self.min_confidence:
                    continue

                clean_text = text.strip()
                if not clean_text or len(clean_text) < 1:
                    continue

                bbox = polygon_to_bbox(polygon, scale_x=scale_x, scale_y=scale_y)
                if bbox["w"] < self.min_box_w or bbox["h"] < self.min_box_h:
                    continue

                current_detections.append({
                    "box": bbox,
                    "text": clean_text,
                    "score": score,
                    "matched": False,
                })

            # So khớp detection với active_tracks
            matched_track_indices = set()
            for det in current_detections:
                best_match_idx = -1
                best_iou = 0.0

                for t_idx, track in enumerate(active_tracks):
                    if t_idx in matched_track_indices:
                        continue
                    iou = compute_iou(det["box"], track["box"])
                    sim = text_similarity(det["text"], track["text"])

                    # Điều kiện ghép: IoU tương đương và chữ giống hoặc lồng vào nhau
                    if iou >= self.iou_threshold and (sim >= 0.50 or det["text"] in track["text"] or track["text"] in det["text"]):
                        if iou > best_iou:
                            best_iou = iou
                            best_match_idx = t_idx

                if best_match_idx >= 0:
                    matched_track_indices.add(best_match_idx)
                    det["matched"] = True
                    trk = active_tracks[best_match_idx]
                    trk["end"] = round(t_curr + step_sec, 2)
                    trk["last_seen"] = t_curr
                    trk["hit_count"] += 1

                    # Cập nhật bounding box mở rộng vừa vặn
                    x1 = min(trk["box"]["x"], det["box"]["x"])
                    y1 = min(trk["box"]["y"], det["box"]["y"])
                    x2 = max(trk["box"]["x"] + trk["box"]["w"], det["box"]["x"] + det["box"]["w"])
                    y2 = max(trk["box"]["y"] + trk["box"]["h"], det["box"]["y"] + det["box"]["h"])
                    trk["box"] = {"x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1}

                    # Ưu tiên chuỗi text dài hơn hoặc có độ tin cậy cao hơn
                    if len(det["text"]) > len(trk["text"]) or det["score"] > trk["score"]:
                        trk["text"] = det["text"]
                        trk["score"] = max(trk["score"], det["score"])
                else:
                    # Tạo track mới
                    active_tracks.append({
                        "start": round(t_curr, 2),
                        "end": round(t_curr + step_sec, 2),
                        "last_seen": t_curr,
                        "box": det["box"],
                        "text": det["text"],
                        "score": det["score"],
                        "hit_count": 1,
                    })

            # Chốt các track đã biến mất quá 0.8 giây
            still_active = []
            for trk in active_tracks:
                if t_curr - trk["last_seen"] > (step_sec * 1.8):
                    completed_tracks.append(trk)
                else:
                    still_active.append(trk)
            active_tracks = still_active

            # Cập nhật tiến trình
            if progress_callback and (idx % 4 == 0 or idx == total_frames - 1):
                pct = 30 + int((idx / float(total_frames)) * 40)
                progress_callback(f"RapidOCR đang quét frame {idx + 1}/{total_frames}...", pct)

        # Chuyển toàn bộ active_tracks còn lại vào completed_tracks
        completed_tracks.extend(active_tracks)

        # 3. Lọc bỏ các khối chữ rác xuất hiện chớp nhoáng (< 0.4s)
        valid_tracks = [t for t in completed_tracks if (t["end"] - t["start"] >= 0.35 or t["hit_count"] >= 2)]
        valid_tracks.sort(key=lambda x: (x["start"], x["box"]["y"]))

        # Chuyển đổi thành VideoTextBlock
        text_blocks: list[VideoTextBlock] = []
        for i, trk in enumerate(valid_tracks, start=1):
            zone = classify_zone(trk["box"], vh)
            block = VideoTextBlock(
                id=f"ocr_{i:02d}",
                zone=zone,
                start=trk["start"],
                end=min(total_dur, trk["end"]),
                box=trk["box"],
                text_zh=trk["text"],
                text_vi="",
                confidence=round(trk["score"], 2),
                style="blur_box",
                is_enabled=True,
            )
            text_blocks.append(block)

        if not text_blocks:
            if progress_callback:
                progress_callback("Hoàn thành: Không phát hiện chữ tiếng Trung nào.", 100)
            return []

        # 4. Dịch thuật sang tiếng Việt bằng Gemini Rotator (Batch Translation)
        if progress_callback:
            progress_callback(f"Gemini đang dịch {len(text_blocks)} cụm chữ sang tiếng Việt...", 75)

        self._translate_blocks(text_blocks)

        # 5. Lưu kết quả vào output/subtitles/{video_stem}_ocr.json
        save_ocr_blocks(video_path, text_blocks)

        if progress_callback:
            progress_callback(f"Đã phát hiện và dịch thành công {len(text_blocks)} khối chữ!", 100)

        # Dọn dẹp thư mục frame tạm
        shutil.rmtree(frames_dir, ignore_errors=True)
        return text_blocks

    def _translate_blocks(self, blocks: list[VideoTextBlock]) -> None:
        """Dịch batch các khối chữ tiếng Trung sang tiếng Việt bằng Gemini."""
        if not blocks:
            return

        unique_texts = list(dict.fromkeys([b.text_zh for b in blocks]))
        translations_map: dict[str, str] = {}

        if self.rotator and self.rotator.total_keys > 0:
            prompt = (
                "Bạn là chuyên gia dịch thuật video tiếng Trung sang tiếng Việt chuyên nghiệp.\n"
                "Dưới đây là danh sách các cụm từ, câu thoại hoặc tiêu đề đồ họa xuất hiện trên video TikTok/Douyin.\n"
                "Hãy dịch chính xác, tự nhiên, ngắn gọn và khớp ngữ cảnh video sang tiếng Việt.\n"
                "QUAN TRỌNG: Trả về DUY NHẤT một chuỗi JSON hợp lệ dạng danh sách các chuỗi theo đúng thứ tự câu vào, ví dụ: [\"câu 1\", \"câu 2\"]\n"
                "Không thêm bất kỳ lời giải thích nào khác.\n\n"
                f"Danh sách tiếng Trung:\n{json.dumps(unique_texts, ensure_ascii=False)}"
            )
            try:
                resp = self.rotator.generate(prompt)
                raw_json = resp.strip()
                # Tách khối markdown nếu có
                if "```" in raw_json:
                    m = re.search(r"```(?:json)?\s*(.*?)\s*```", raw_json, re.DOTALL)
                    if m:
                        raw_json = m.group(1).strip()
                parsed = json.loads(raw_json)
                if isinstance(parsed, list) and len(parsed) == len(unique_texts):
                    for src, dst in zip(unique_texts, parsed):
                        translations_map[src] = str(dst).strip()
            except Exception as e:
                logger.error(f"[video_ocr] Lỗi Gemini batch translation: {e}")

        # Fallback dịch qua Google Translate GTX nếu Gemini chưa có key hoặc chưa đủ
        missing_texts = [s for s in unique_texts if s not in translations_map]
        if missing_texts:
            try:
                import requests
                combined = "\n".join(missing_texts)
                url = "https://translate.googleapis.com/translate_a/single"
                params = {"client": "gtx", "sl": "zh-CN", "tl": "vi", "dt": "t", "q": combined}
                resp = requests.get(url, params=params, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_lines = "".join([part[0] for part in data[0] if part and part[0]]).split("\n")
                    if len(raw_lines) == len(missing_texts):
                        for src, dst in zip(missing_texts, raw_lines):
                            translations_map[src] = dst.strip()
                    else:
                        for idx, src in enumerate(missing_texts):
                            if idx < len(raw_lines):
                                translations_map[src] = raw_lines[idx].strip()
            except Exception as e:
                logger.error(f"[video_ocr] Lỗi Google fallback translation: {e}")

        # Gán lại bản dịch tiếng Việt cho các blocks
        for src in unique_texts:
            if src not in translations_map:
                translations_map[src] = src

        # Gán lại bản dịch tiếng Việt cho các blocks
        for b in blocks:
            b.text_vi = translations_map.get(b.text_zh, b.text_zh)


def get_ocr_json_path(video_path: Path) -> Path:
    """Lấy đường dẫn file lưu trữ metadata OCR JSON của video."""
    sub_dir = OUTPUT_DIR / "subtitles"
    sub_dir.mkdir(parents=True, exist_ok=True)
    return sub_dir / f"{video_path.stem}_ocr.json"


def save_ocr_blocks(video_path: Path, blocks: list[VideoTextBlock]) -> Path:
    """Lưu danh sách khối chữ OCR vào file JSON."""
    json_path = get_ocr_json_path(video_path)
    data = {
        "video_path": str(video_path.resolve()),
        "total_blocks": len(blocks),
        "blocks": [b.to_dict() for b in blocks],
    }
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return json_path


def load_ocr_blocks(video_path: Path) -> list[VideoTextBlock]:
    """Nạp danh sách khối chữ OCR đã lưu của video (nếu có)."""
    json_path = get_ocr_json_path(video_path)
    if not json_path.exists():
        return []
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        return [VideoTextBlock.from_dict(b) for b in data.get("blocks", [])]
    except Exception as e:
        logger.error(f"[video_ocr] Lỗi đọc OCR json {json_path}: {e}")
        return []
