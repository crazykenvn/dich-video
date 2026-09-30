"""Khởi tạo và cấu hình ứng dụng FastAPI cho Creator Studio Pipeline Pro."""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import OUTPUT_DIR, PROJECT_ROOT
from ..downloader.db import init_db
from .routes import fs, publishing, studio, videos


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Khởi động và dọn dẹp tài nguyên máy chủ."""
    print("[Studio Server] Starting Studio Server...")
    init_db()

    # Đảm bảo các thư mục cốt lõi tồn tại
    (OUTPUT_DIR / "downloads").mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "ready_to_upload").mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "thumbnails").mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "branding").mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "tmp").mkdir(parents=True, exist_ok=True)

    print("[Studio Server] Server ready at http://localhost:8000")

    # Tự động mở trình duyệt nếu chưa mở
    def _open_browser():
        import time
        import webbrowser
        time.sleep(1.0)
        try:
            webbrowser.open("http://localhost:8000")
        except Exception:
            pass

    import threading
    threading.Thread(target=_open_browser, daemon=True).start()

    yield
    print("[Studio Server] Shutting down...")


app = FastAPI(
    title="Creator Video Studio API",
    description="Backend API tốc độ cao phục vụ biên tập video, render NVENC và quản lý phân phối đa nền tảng.",
    version="2.0.0",
    lifespan=lifespan,
)

# Kích hoạt CORS cho phép frontend tương tác mượt mà
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đăng ký các router API
app.include_router(fs.router, prefix="/api")
app.include_router(videos.router, prefix="/api")
app.include_router(studio.router, prefix="/api")
app.include_router(publishing.router, prefix="/api")

# Phục vụ thư mục thumbnails static
thumbnails_dir = OUTPUT_DIR / "thumbnails"
thumbnails_dir.mkdir(parents=True, exist_ok=True)
app.mount("/thumbnails", StaticFiles(directory=str(thumbnails_dir)), name="thumbnails")

# Phục vụ thư mục branding static (chứa logo thương hiệu watermark lưu trữ vĩnh viễn)
branding_dir = OUTPUT_DIR / "branding"
branding_dir.mkdir(parents=True, exist_ok=True)
app.mount("/branding", StaticFiles(directory=str(branding_dir)), name="branding")

# Phục vụ compiled assets của React SPA frontend
dist_assets_dir = PROJECT_ROOT / "frontend" / "dist" / "assets"
if dist_assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(dist_assets_dir)), name="assets")



@app.get("/api/health")
def health_check() -> dict[str, str | bool]:
    """Kiểm tra tình trạng hoạt động của máy chủ backend."""
    has_cuda = False
    try:
        import torch
        has_cuda = torch.cuda.is_available()
    except Exception:
        has_cuda = os.system("where nvidia-smi >nul 2>&1") == 0

    from ..media import is_nvenc_available
    has_nvenc = is_nvenc_available()

    return {
        "status": "healthy",
        "version": "2.0.0",
        "cuda_ready": has_cuda,
        "nvenc_ready": has_nvenc,
        "gpu_target": "RTX 3060 12GB NVENC" if has_nvenc else "CPU",
    }


@app.get("/preview_sample.jpg", response_model=None)
def get_sample_preview():
    """Cung cấp ảnh mẫu preview của video."""
    sample_file = PROJECT_ROOT / "preview_sample.jpg"
    if sample_file.exists():
        return FileResponse(str(sample_file), media_type="image/jpeg")
    return JSONResponse(status_code=404, content={"message": "Ảnh mẫu chưa tồn tại"})


@app.get("/", response_model=None)
def serve_index():
    """Phục vụ giao diện người dùng chính."""
    # Nếu có thư mục build frontend/dist thì serve file index.html của SPA
    dist_index = PROJECT_ROOT / "frontend" / "dist" / "index.html"
    if dist_index.exists():
        return FileResponse(str(dist_index))

    # Nếu chưa build thì serve giao diện mockup_studio.html
    mockup_file = PROJECT_ROOT / "mockup_studio.html"
    if mockup_file.exists():
        return FileResponse(str(mockup_file))

    return JSONResponse(content={"message": "Studio Pipeline Pro API Ready!"})
