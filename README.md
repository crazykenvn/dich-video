# 🎬 Hệ Thống Dịch Video & Lách Bản Quyền Tự Động (Video Translator & Anti-Detect)

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-Ready-007808?logo=ffmpeg&logoColor=white)](https://ffmpeg.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-UI-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Whisper](https://img.shields.io/badge/Whisper-OpenAI%20GPU-blue)](https://github.com/openai/whisper)
[![Gemini](https://img.shields.io/badge/Google-Gemini%20API-4E75A0?logo=google&logoColor=white)](https://ai.google.dev/)
[![VieNeu-TTS](https://img.shields.io/badge/TTS-VieNeu--TTS-orange)](https://github.com/pnnbao97/VieNeu-TTS)

Hệ thống tự động hóa xử lý video toàn diện chạy hoàn toàn trên máy tính của bạn:
**Tách âm thanh → Nhận dạng giọng nói (Whisper GPU) → Dịch thuật thông minh (Gemini Round-Robin) → Lồng tiếng Việt & Khớp khẩu hình (VieNeu-TTS) → Đóng phụ đề cứng (Hardsub) → Xử lý bộ lọc lách bản quyền đa tầng (pHash & Audio Spectrogram)**.

---

## 🌟 Tính Năng Nổi Bật

### 1. 🤖 Nhận Dạng & Dịch Thuật Đa Tầng
* **Whisper AI Tăng Tốc CUDA:** Hỗ trợ GPU NVIDIA (RTX 3060...) nhận dạng tiếng Trung, Anh, Nhật, Hàn... chuẩn xác đến từng mili-giây.
* **Cơ Chế Gemini API Round-Robin:** Hỗ trợ nạp không giới hạn số lượng API Key trong file `gemini_keys.txt`. Hệ thống tự động luân phiên xoay vòng từng key, không lo dính hạn mức Rate Limit (RPM/TPM).
* **Tự Động Fallback:** Nếu không có key hoặc tất cả key bận, hệ thống tự động chuyển sang Google Translate miễn phí mà không làm gián đoạn tiến trình.

### 2. 🎙️ Lồng Tiếng Việt & Khớp Khẩu Hình Thông Minh
* **VieNeu-TTS:** Giọng đọc tiếng Việt tự nhiên chuẩn studio (Đức Trí, Mai Anh, Minh Quân...).
* **Hỗ Trợ Edge-TTS:** Lồng tiếng cho hơn 15+ ngôn ngữ quốc tế (Anh, Trung, Nhật, Hàn, Pháp, Đức...).
* **Giải Quyết Chồng Âm (Plan A):** Tự động phát hiện khi câu lồng tiếng dài hơn khoảng cách câu gốc và tự động kéo/nén tốc độ (tempo 1.2x – 1.85x) để khớp khẩu hình từng khung hình, không bị cắt cụt từ.

### 3. 🛡️ Bộ Công Cụ Lách Bản Quyền Đa Tầng (Anti-Fingerprint Suite)
* **Kỹ thuật 1 - Lọc Cấu Trúc Hình Ảnh (pHash / DCT Disruptor):** Micro-Crop 1.5% viền ngoài, tái nội suy Lanczos về kích thước gốc, chuẩn hóa `setsar=1`, vi chỉnh tương phản/màu sắc (Micro-EQ) và cấy lớp hạt điện ảnh động mịn (`noise=c0s=2.5:allf=t`) làm mã băm hình ảnh biến thiên liên tục.
* **Kỹ thuật 4 - Biến Điệu Âm Thanh Gốc (Acoustic Fingerprint Disruptor):** Đẩy cao độ `+2.5%` kết hợp bù tốc độ `atempo=1/1.025` và bộ cân bằng âm sắc đa tần (Parametric EQ). Giữ 100% lời thoại và âm thanh môi trường gốc, khớp khẩu hình 100% nhưng làm lệch hoàn toàn phổ âm thanh Spectrogram.
* **Logo Thương Hiệu Chuyển Động Mờ:** Chèn watermark chữ hoặc ảnh PNG với độ mờ lý tưởng (18%), di chuyển lượn sóng (drift) hoặc nảy góc (bounce) vô hiệu hóa bot quét bản quyền của TikTok, Douyin, Reels.

### 4. 💎 Chất Lượng Xuất Video Chuẩn Phát Sóng (CRF 18)
* Xuất video bằng bộ mã hóa `libx264 -crf 18 -preset veryfast -pix_fmt yuv420p` (chuẩn Visually Lossless phát sóng truyền hình).
* Bảo toàn 100% độ sắc nét ban đầu của video (khuôn mặt, chi tiết mắt/tóc, nếp áo, hậu cảnh) không bị nhòe nát hay vỡ khối macroblock.
* Hỗ trợ tùy chọn mã hóa phần cứng GPU MediaFoundation bitrate cao.

### 5. 📁 Dịch Hàng Loạt (Batch Processing) & Bảng Theo Dõi Trực Tiếp
* Chọn 1 thư mục đầu vào -> Xuất thẳng ra 1 thư mục đầu ra.
* Bảng tiến độ theo dõi trực tiếp từng video (kích thước, trạng thái, thời gian xử lý, số câu thoại).
* Tự động bỏ qua các video đã hoàn thành (`skip_existing`).

### 6. ⚡ Chế Độ "Remix" — Xử Lý Nhanh Không Cần Dịch
* Dành riêng cho các video không cần dịch thuật: Bỏ qua Whisper/Gemini/TTS, chỉ chạy qua bộ lọc hình ảnh + biến điệu âm thanh gốc + đóng logo.
* Tốc độ cực nhanh: Chỉ **3 – 6 giây / video**!

---

## 📋 Yêu Cầu Hệ Thống

1. **Hệ điều hành:** Windows 10/11, Linux, macOS.
2. **Python:** 3.10 trở lên.
3. **FFmpeg:** Cần cài đặt [FFmpeg](https://ffmpeg.org/download.html) và thêm vào biến môi trường PATH.
4. **Card đồ họa (Khuyến nghị):** NVIDIA GPU hỗ trợ CUDA (RTX 2060/3060/4060...) để nhận dạng Whisper và encode siêu tốc.

---

## 📦 Cài Đặt

```bash
# 1. Clone repository về máy
git clone https://github.com/crazykenvn/dich-video.git
cd dich-video

# 2. Tạo môi trường ảo Python
python -m venv .venv

# 3. Kích hoạt môi trường ảo
# Trên Windows:
.venv\Scripts\activate
# Trên Linux/macOS:
source .venv/bin/activate

# 4. Cài đặt các thư viện phụ thuộc
pip install -r requirements.txt
```

---

## 🔑 Cấu Hình Gemini API Key (Tùy chọn - Khuyên dùng)

Tạo file `gemini_keys.txt` tại thư mục gốc của dự án và dán danh sách key (mỗi dòng một key):

```text
AIzaSyD-xxxxxxxxxxxxxxxxxxxxxxxxxxxx
AIzaSyB-yyyyyyyyyyyyyyyyyyyyyyyyyyyy
AIzaSyC-zzzzzzzzzzzzzzzzzzzzzzzzzzzz
```

*Hệ thống sẽ tự động đọc file này và luân phiên xoay vòng các key khi dịch. File này đã được đưa vào `.gitignore` để đảm bảo an toàn tuyệt đối.*

---

## 🚀 Hướng Dẫn Sử Dụng

### Cách 1: Sử dụng Giao Diện Web (Streamlit)

Chỉ cần click đúp vào file:
```cmd
Chay-Giao-Dien.bat
```
hoặc chạy lệnh:
```bash
streamlit run app.py
```

Giao diện trực quan gồm 2 Tab chính:
* **📁 Dịch hàng loạt (Thư mục):** Chọn thư mục chứa nhiều video và thư mục xuất, bấm bắt đầu để máy tự động chạy qua từng video.
* **🎬 Dịch 1 video (Tải file):** Kéo thả video đơn lẻ để xem trước, dịch và tải về ngay.

---

### Cách 2: Sử Dụng Dòng Lệnh (CLI)

#### 1. Dịch & Lồng tiếng video (Chế độ Dub)
```bash
python cli.py "D:\input.mp4" --to vi --mode dub --voice "Đức Trí" --font-size 11 --sub-style white_box
```

#### 2. Dịch hàng loạt toàn bộ thư mục video
```bash
python cli.py "D:\video_goc" --output "D:\video_dich" --mode dub --video-quality high
```

#### 3. Chế độ Remix (Chỉ xử lý lách bản quyền & đóng logo, không dịch)
```bash
python cli.py "D:\video_goc" --output "D:\video_remix" --mode remix --watermark-text "@KENVN" --watermark-opacity 0.18
```

#### 4. Chỉ xuất phụ đề cứng (Hardsub)
```bash
python cli.py "D:\input.mp4" --mode hard --sub-style white_box
```

---

## 📊 Bảng Chế Độ Xuất (Modes)

| Mode | Ý nghĩa | Quy trình xử lý | Thời gian |
|:---:|:---|:---|:---:|
| `dub` | **Lồng tiếng & Phụ đề** *(Khuyên dùng)* | Whisper → Gemini → VieNeu-TTS → Hòa âm → Đóng sub cứng & Logo | ~30 - 60s / clip |
| `remix` | **⚡ Lách bản quyền & Logo** *(Mới)* | Lọc hình pHash + Biến điệu audio gốc + Chèn logo chuyển động | **3 - 6s / clip** |
| `hard` | **Chỉ in phụ đề cứng** | Whisper → Gemini → Đóng sub cứng lên khung hình | ~15 - 25s / clip |
| `soft` | **Nhúng phụ đề mềm** | Whisper → Gemini → Mux phụ đề có thể bật/tắt | ~10 - 20s / clip |
| `srt` | **Chỉ xuất file chữ SRT** | Whisper → Gemini → Xuất file .srt gốc, dịch & song ngữ | ~5 - 10s / clip |

---

## 🔄 Quy Trình Đồng Bộ Cập Nhật Từ Tác Giả Gốc (Upstream)

Repo này được cấu hình theo mô hình **Upstream – Origin** giúp bạn giữ nguyên các tính năng tùy biến cá nhân mà vẫn kéo được các bản vá mới từ tác giả gốc:

```bash
# 1. Kéo các commit mới nhất từ tác giả về
git fetch upstream

# 2. Gộp cập nhật vào mã nguồn của bạn
git merge upstream/main

# 3. Đẩy lên GitHub cá nhân của bạn
git push origin main
```

---

## 📄 Bản Quyền & Giấy Phép

Dự án được phân phối dưới giấy phép mã nguồn mở MIT License. Tự do sử dụng, chỉnh sửa và triển khai cho các mục đích cá nhân và thương mại.
