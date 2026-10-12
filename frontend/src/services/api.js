/**
 * API Service tương tác với Backend FastAPI của Creator Video Studio
 */

export function formatWinPath(p) {
  if (!p) return '';
  return p.split('/').join('\\');
}

export async function apiFetch(endpoint, options = {}) {
  try {
    const res = await fetch(endpoint, {
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {})
      },
      ...options
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `Lỗi HTTP ${res.status}`);
    }
    return await res.json();
  } catch (error) {
    console.warn(`API Error [${endpoint}]:`, error.message);
    return null;
  }
}

// 1. Hệ thống & File
export const getHealth = () => apiFetch('/api/health');
export const getConfig = () => apiFetch('/api/fs/config');
export const updateConfig = (data) => apiFetch('/api/fs/config', {
  method: 'POST',
  body: JSON.stringify(data)
});
export const openFolder = (path) => apiFetch('/api/fs/open-folder', {
  method: 'POST',
  body: JSON.stringify({ path })
});

// 2. Video Nguồn & Quét Máy
export const getSources = () => apiFetch('/api/videos/sources');
export const getVideos = (sourceType = 'all', sourceId = 'all') =>
  apiFetch(`/api/videos/list?source_type=${sourceType}&source_id=${encodeURIComponent(sourceId)}`);
export const quickDownload = (url, subfolder) => apiFetch('/api/videos/quick-download', {
  method: 'POST',
  body: JSON.stringify({ url, subfolder })
});
export const scanLocal = (path, sourceName = '') => apiFetch('/api/videos/scan-local', {
  method: 'POST',
  body: JSON.stringify({ path, source_name: sourceName })
});
export const pickFolder = () => apiFetch('/api/videos/pick-folder', {
  method: 'POST'
});
export const pickFiles = () => apiFetch('/api/videos/pick-files', {
  method: 'POST'
});
export const removeFolder = (path, folderType = 'local') => apiFetch('/api/videos/remove-folder', {
  method: 'POST',
  body: JSON.stringify({ path, folder_type: folderType })
});

// Crawler Accounts API
export const getCrawlerAccounts = () => apiFetch('/api/videos/crawler/accounts');
export const addCrawlerAccount = (data) => apiFetch('/api/videos/crawler/accounts', {
  method: 'POST',
  body: JSON.stringify(data)
});
export const toggleCrawlerAccount = (accountId, isActive) => apiFetch('/api/videos/crawler/toggle', {
  method: 'POST',
  body: JSON.stringify({ account_id: accountId, is_active: isActive })
});
export const deleteCrawlerAccount = (accountId) => apiFetch(`/api/videos/crawler/accounts/${encodeURIComponent(accountId)}`, {
  method: 'DELETE'
});
export const scanCrawlerAccounts = (accountId = null, maxVideos = null, forceFullScan = false) => apiFetch('/api/videos/crawler/scan', {
  method: 'POST',
  body: JSON.stringify({ account_id: accountId, max_videos: maxVideos, force_full_scan: forceFullScan })
});
export const resetCrawlerScan = (accountId = null, deleteDiscovered = false) => apiFetch('/api/videos/crawler/reset-scan', {
  method: 'POST',
  body: JSON.stringify({ account_id: accountId, delete_discovered: deleteDiscovered })
});
export const clearThumbnails = (accountId = null) => apiFetch('/api/videos/clear-thumbnails', {
  method: 'POST',
  body: JSON.stringify({ account_id: accountId })
});
export const deleteVideoItem = (videoId = null, path = null, deleteFile = false) => apiFetch('/api/videos/delete-item', {
  method: 'POST',
  body: JSON.stringify({ video_id: videoId, path: path, delete_file: deleteFile })
});
export const downloadDiscoveredVideo = (videoId) => apiFetch('/api/videos/download-discovered', {
  method: 'POST',
  body: JSON.stringify({ video_id: videoId })
});
export const openDouyinLogin = () => apiFetch('/api/videos/crawler/douyin-login', {
  method: 'POST',
});
export const getDouyinStatus = () => apiFetch('/api/videos/crawler/douyin-status');
export const confirmDouyinLogin = () => apiFetch('/api/videos/crawler/douyin-confirm', {
  method: 'POST',
});
export const saveDouyinCookie = (cookie) => apiFetch('/api/videos/crawler/douyin-cookie', {
  method: 'POST',
  body: JSON.stringify({ cookie }),
});
export const uploadDouyinCookieFile = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch('/api/videos/crawler/douyin-cookie-file', {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Lỗi nạp file cookie' }));
    throw new Error(err.detail || 'Lỗi nạp file cookie');
  }
  return await res.json();
};
export const uploadVideo = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  try {
    const res = await fetch('/api/videos/upload', {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Lỗi tải video lên' }));
      throw new Error(err.detail || 'Lỗi tải video lên');
    }
    return await res.json();
  } catch (err) {
    console.warn('Upload video error:', err);
    return null;
  }
};

// 3. Studio & Preview
export const getVideoStreamUrl = (videoPath) =>
  `/api/videos/stream?video_path=${encodeURIComponent(videoPath)}`;
export const getVideoInfo = (videoPath) =>
  apiFetch(`/api/studio/video-info?video_path=${encodeURIComponent(videoPath)}`);
export const getPreviewFrame = (videoPath, timestampSec = 1.0) =>
  apiFetch(`/api/studio/preview-frame?video_path=${encodeURIComponent(videoPath)}&timestamp_sec=${timestampSec}`, {
    method: 'POST'
  });
export const getTimelineFrames = (videoPath, count = 16) =>
  apiFetch(`/api/studio/timeline-frames?video_path=${encodeURIComponent(videoPath)}&count=${count}`);
export const getSubtitles = (videoPath) =>
  apiFetch(`/api/studio/subtitles?video_path=${encodeURIComponent(videoPath)}`);
export const getDubAudioUrl = (videoPath) =>
  `/api/studio/dub-audio?video_path=${encodeURIComponent(videoPath)}`;
export const generateDubAudio = (data) => apiFetch('/api/studio/generate-dub-audio', {
  method: 'POST',
  body: JSON.stringify(data)
});
export const saveSubtitles = (data) => apiFetch('/api/studio/save-subtitles', {
  method: 'POST',
  body: JSON.stringify(data)
});
export const getLabPresets = () => apiFetch('/api/studio/presets');
export const exportVideo = (data) => apiFetch('/api/studio/export', {
  method: 'POST',
  body: JSON.stringify(data)
});
export const getLogoInfo = () => apiFetch('/api/studio/logo-info');
export const uploadLogo = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  try {
    const res = await fetch('/api/studio/upload-logo', {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Lỗi tải ảnh logo' }));
      throw new Error(err.detail || 'Lỗi tải ảnh logo');
    }
    return await res.json();
  } catch (err) {
    console.warn('Upload Logo error:', err);
    return null;
  }
};
export const deleteLogo = () => apiFetch('/api/studio/logo', {
  method: 'DELETE'
});
export const autoTranslate = (data) => apiFetch('/api/studio/auto-translate', {
  method: 'POST',
  body: JSON.stringify(data)
});
export const getTranslateProgress = (videoPath) =>
  apiFetch(`/api/studio/translate-progress?video_path=${encodeURIComponent(videoPath)}`);
export const importSrt = async (file, videoPath) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('video_path', videoPath);
  try {
    const res = await fetch('/api/studio/import-srt', {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Lỗi tải file phụ đề' }));
      throw new Error(err.detail || 'Lỗi tải file phụ đề');
    }
    return await res.json();
  } catch (err) {
    console.warn('Import SRT error:', err);
    return null;
  }
};

// 3.1. Video OCR: Phát hiện & Dịch chữ rải rác
export const scanOCR = (videoPath, sampleFps = 2.0, minConfidence = 0.60) => apiFetch('/api/studio/scan-ocr', {
  method: 'POST',
  body: JSON.stringify({ video_path: videoPath, sample_fps: sampleFps, min_confidence: minConfidence })
});
export const getOCRStatus = (videoPath) =>
  apiFetch(`/api/studio/ocr-status?video_path=${encodeURIComponent(videoPath)}`);
export const getOCRBlocks = (videoPath) =>
  apiFetch(`/api/studio/ocr-blocks?video_path=${encodeURIComponent(videoPath)}`);
export const saveOCRBlocks = (videoPath, blocks) => apiFetch('/api/studio/save-ocr-blocks', {
  method: 'POST',
  body: JSON.stringify({ video_path: videoPath, blocks })
});

// 4. Phân phối Đa nền tảng
export const getPublishSubfolders = () =>
  apiFetch('/api/publishing/subfolders');
export const getPublishVideos = (subfolder = 'all') =>
  apiFetch(`/api/publishing/videos?subfolder=${encodeURIComponent(subfolder)}`);
export const togglePublish = (videoId, platform, isPublished) => apiFetch('/api/publishing/toggle-status', {
  method: 'POST',
  body: JSON.stringify({ video_id: videoId, platform, is_published: isPublished })
});
export const getPublishStats = () => apiFetch('/api/publishing/stats');
