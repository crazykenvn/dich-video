"""Pydantic Models định nghĩa cấu trúc dữ liệu Request / Response cho API Studio."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class DriveInfo(BaseModel):
    letter: str
    path: str
    name: str
    total_gb: float
    free_gb: float


class FolderItem(BaseModel):
    name: str
    path: str
    video_count: int
    has_subfolders: bool


class BrowseFolderResponse(BaseModel):
    path: str
    parent: str | None = None
    folders: list[FolderItem]
    total_folders: int


class PathConfigRequest(BaseModel):
    download_root_dir: str | None = None
    output_root_dir: str | None = None


class PathConfigResponse(BaseModel):
    download_root_dir: str
    output_root_dir: str


class OpenFolderRequest(BaseModel):
    path: str


class QuickDownloadRequest(BaseModel):
    url: str
    subfolder: str = "general_inbox"


class ScanLocalFolderRequest(BaseModel):
    path: str
    source_name: str | None = None


class TogglePublishStatusRequest(BaseModel):
    video_id: int
    platform: str
    is_published: bool | None = None


class SubtitleSegmentModel(BaseModel):
    id: int
    start: float
    end: float
    text: str


class VideoTextBlockModel(BaseModel):
    id: str
    zone: str = "body_overlay"  # "bottom_sub" | "top_title" | "body_overlay"
    start: float
    end: float
    box: dict[str, int]
    text_zh: str
    text_vi: str = ""
    confidence: float = 0.9
    style: str = "blur_box"  # "blur_box" | "solid_black" | "stroke_only"
    is_enabled: bool = True


class RenderConfigRequest(BaseModel):
    video_path: str
    mode: str = "translate"  # "translate" | "remix"
    subfolder: str = "general_inbox"
    anti_combo: str = "stealth"  # "stealth" | "cinema" | "crt" | "fortress"
    segments: list[SubtitleSegmentModel] = Field(default_factory=list)
    mask_style: str = "solid_black"
    box_opacity: int = 100
    font_size: int = 16
    box_padding: int = 6
    box_width: int = 88
    font_family: str = "Arial"
    margin_v: int = 38
    voice: str = "vi-VN-HoaiMyNeural"
    pitch_shift: bool = True
    watermark_enabled: bool = True
    watermark_text: str = "KEN STUDIO"
    is_orig_muted: bool = False
    audio_ducking: int = 12
    ocr_blocks: list[VideoTextBlockModel] | None = None


class SaveSubtitlesRequest(BaseModel):
    video_path: str
    segments: list[SubtitleSegmentModel] = Field(default_factory=list)
    margin_v: int = 38
    mask_style: str = "solid_black"
    font_size: int = 16
    box_padding: int = 6
    box_width: int = 88
    voice: str = "vi-VN-HoaiMyNeural"
    is_orig_muted: bool = False


class GenerateDubAudioRequest(BaseModel):
    video_path: str
    voice: str = "vi-VN-HoaiMyNeural"
    segments: list[SubtitleSegmentModel] = Field(default_factory=list)


class VideoItemResponse(BaseModel):
    id: int | None = None
    filename: str
    path: str
    subfolder: str
    size_mb: float
    duration_str: str | None = "00:15"
    has_sub: bool = False
    suggest_remix: bool = False
    status: str = "inbox"
    source_type: str = "downloaded"  # "downloaded" | "local"


class AutoTranslateRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    video_path: str
    source_lang: str = "zh-CN"
    target_lang: str = "vi"
    model_size: str | None = None
    device: str | None = None
    voice: str = "vi-VN-HoaiMyNeural"



class ScanOCRRequest(BaseModel):
    video_path: str
    sample_fps: float = 2.0
    min_confidence: float = 0.60


class SaveOCRBlocksRequest(BaseModel):
    video_path: str
    blocks: list[VideoTextBlockModel]
