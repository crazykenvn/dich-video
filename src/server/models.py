"""Pydantic Models định nghĩa cấu trúc dữ liệu Request / Response cho API Studio."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


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
    margin_v: int = 38
    voice: str = "vi-VN-HoaiMyNeural"
    pitch_shift: bool = True
    watermark_enabled: bool = True
    watermark_text: str = "KEN STUDIO"


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
