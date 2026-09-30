import React, { useState, useEffect, useRef } from 'react';
import { 
  Folder, FolderPlus, Download, HardDrive, Laptop, Globe, Zap, 
  Search, ExternalLink, RefreshCw, Sparkles, Filter, FileVideo, PlusCircle, Upload
} from 'lucide-react';
import * as api from '../services/api';

export default function IngestionScreen({ onSelectVideo, showToast }) {
  const [downloadRootDir, setDownloadRootDir] = useState('D:\\Mine\\dich-video\\output\\downloads\\');
  const [sources, setSources] = useState({ download_subfolders: [], local_folders: [] });
  const [activeSourceType, setActiveSourceType] = useState('subfolder');
  const [activeSourceId, setActiveSourceId] = useState('all');
  const [videosList, setVideosList] = useState([]);
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [loading, setLoading] = useState(false);
  const [quickUrl, setQuickUrl] = useState('');
  const [targetAccount, setTargetAccount] = useState('general_inbox');

  const fileInputRef = useRef(null);

  // Load config & sources lúc mount
  useEffect(() => {
    loadConfig();
    loadSourcesData();
  }, []);

  const loadConfig = async () => {
    const cfg = await api.getConfig();
    if (cfg && cfg.download_root_dir) {
      setDownloadRootDir(api.formatWinPath(cfg.download_root_dir));
    }
  };

  const loadSourcesData = async () => {
    const data = await api.getSources();
    if (data) {
      setSources(data);
      if (data.download_subfolders?.length > 0) {
        const first = data.download_subfolders[0];
        setActiveSourceType('subfolder');
        setActiveSourceId(first.id);
        setTargetAccount(first.folder_name);
        loadVideos(first.type === 'local_disk' ? 'local' : 'subfolder', first.id);
      } else {
        loadVideos('all', 'all');
      }
    }
  };

  const loadVideos = async (sourceType, sourceId) => {
    setLoading(true);
    const list = await api.getVideos(sourceType, sourceId);
    if (list && Array.isArray(list)) {
      setVideosList(list);
    }
    setLoading(false);
  };

  const handleFilterFolder = (type, id) => {
    setActiveSourceType(type);
    setActiveSourceId(id);
    loadVideos(type, id);
  };

  // 1. Mở hộp thoại Windows Explorer chọn thư mục máy tính
  const handlePickLocalFolder = async () => {
    showToast('Đang mở hộp thoại Windows Explorer để chọn thư mục...', 'info');
    const res = await api.pickFolder();
    if (res && res.success) {
      showToast(`✓ Đã nạp thành công <b>${res.video_count} video</b> từ thư mục <b>${res.folder_name}</b>!`, 'success');
      await loadSourcesData();
      setActiveSourceType('local');
      setActiveSourceId(res.path);
      if (res.videos && res.videos.length > 0) {
        setVideosList(res.videos);
      } else {
        loadVideos('local', res.path);
      }
    } else if (res && res.message && !res.message.includes('hủy')) {
      showToast(`⚠️ ${res.message}`, 'warning');
    }
  };

  // 2. Mở hộp thoại Windows Explorer chọn trực tiếp file video
  const handlePickLocalFiles = async () => {
    showToast('Đang mở hộp thoại Windows Explorer để chọn file video...', 'info');
    const res = await api.pickFiles();
    if (res && res.success && res.videos?.length > 0) {
      showToast(`✓ Đã chọn <b>${res.videos.length} video</b> từ máy tính!`, 'success');
      setVideosList(prev => [...res.videos, ...prev]);
      // Nếu người dùng chọn đúng 1 file, mở ngay vào Studio
      if (res.videos.length === 1) {
        onSelectVideo(res.videos[0], 'translate');
      }
    } else if (res && res.message && !res.message.includes('hủy')) {
      showToast(`⚠️ ${res.message}`, 'warning');
    }
  };

  // 3. Đổi thư mục tải về gốc (download_root) qua Windows Explorer
  const handlePickDownloadRoot = async () => {
    const res = await api.pickFolder();
    if (res && res.success && res.path) {
      setDownloadRootDir(api.formatWinPath(res.path));
      await api.updateConfig({ download_root_dir: res.path });
      showToast(`✓ Đã đổi thư mục tải về gốc thành:<br/><span class="font-mono text-white text-[11px]">${api.formatWinPath(res.path)}</span>`, 'success');
      loadSourcesData();
    }
  };

  // 4. Nhập/Dán thủ công đường dẫn thư mục hoặc file trên máy
  const handleManualPathPrompt = async () => {
    const p = prompt('Nhập đường dẫn thư mục hoặc file video trên máy (ví dụ: D:\\Videos\\MyTiktok):');
    if (!p || !p.trim()) return;
    const trimmed = p.trim();
    showToast(`Đang quét đường dẫn: ${trimmed}...`, 'info');
    const res = await api.scanLocal(trimmed);
    if (res && res.success) {
      showToast(`✓ Đã quét thành công ${res.video_count} video từ thư mục ${res.folder_name}!`, 'success');
      await loadSourcesData();
      setActiveSourceType('local');
      setActiveSourceId(res.path);
      loadVideos('local', res.path);
    } else {
      showToast(`❌ Không tìm thấy video hợp lệ tại đường dẫn này!`, 'error');
    }
  };

  // 5. Tải file video trực tiếp từ trình duyệt (Upload)
  const handleDirectVideoUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    showToast(`Đang nạp file video <b>${file.name}</b> vào Studio...`, 'info');
    const res = await api.uploadVideo(file);
    if (res && res.success && res.video) {
      showToast(`✓ Đã nạp video <b>${res.video.filename}</b> thành công!`, 'success');
      onSelectVideo(res.video, 'translate');
    } else {
      showToast('❌ Không thể nạp video này lên máy chủ', 'error');
    }
  };

  const handleQuickDownload = async () => {
    if (!quickUrl.trim()) {
      alert('Vui lòng dán link video Douyin / TikTok vào ô nhập!');
      return;
    }

    let acc = targetAccount;
    if (acc === '_new_subfolder_') {
      const name = prompt('Nhập tên subfolder tài khoản mới (ví dụ: ken_channel):', 'ken_channel');
      if (!name) return;
      acc = name.trim();
    }

    showToast(`Đang gửi yêu cầu tải video vào subfolder: <code class="text-sky-300">downloads/${acc}/</code>`, 'info');
    const res = await api.quickDownload(quickUrl.trim(), acc);
    if (res && res.success) {
      showToast(`✓ Đã thêm video vào hàng đợi tải về: downloads/${acc}/`, 'success');
      setQuickUrl('');
      setTimeout(() => loadSourcesData(), 1200);
    }
  };

  const filteredVideos = videosList.filter(v => {
    if (categoryFilter === 'translate') return v.has_sub;
    if (categoryFilter === 'remix') return v.suggest_remix;
    return true;
  });

  return (
    <div className="flex-1 flex flex-col p-4 overflow-y-auto bg-slate-950 space-y-4">
      {/* Hidden browser file input fallback */}
      <input
        type="file"
        ref={fileInputRef}
        accept="video/*"
        className="hidden"
        onChange={handleDirectVideoUpload}
      />

      {/* 1. Download Root Bar */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-3.5 shadow-lg flex flex-col md:flex-row items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2 text-slate-300">
          <span className="text-sky-400 font-bold flex items-center gap-1.5">
            <Folder className="w-4 h-4" /> Thư mục tải về gốc (Cha):
          </span>
          <span className="font-mono bg-slate-950 px-3 py-1 rounded-lg border border-slate-800 text-white font-semibold">
            {downloadRootDir}
          </span>
          <button
            onClick={handlePickDownloadRoot}
            className="px-3 py-1.5 bg-sky-500/15 hover:bg-sky-500/25 text-sky-300 rounded-lg border border-sky-500/30 flex items-center gap-1.5 font-semibold transition active:scale-95"
            title="Mở hộp thoại Windows Explorer để chọn thư mục tải về"
          >
            <Folder className="w-3.5 h-3.5" /> Chọn Thư Mục Khác
          </button>
          <button
            onClick={() => api.openFolder(downloadRootDir)}
            className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg border border-slate-700 flex items-center gap-1"
          >
            <ExternalLink className="w-3 h-3" /> Mở
          </button>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[11px] text-emerald-400 font-medium bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 rounded-lg">
            ✓ Tự động phân subfolder theo từng kênh: <code className="font-mono font-bold">downloads/&#123;account&#125;/</code>
          </span>
        </div>
      </div>

      {/* 2. Quick Download & Local Import Bar */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-xl flex flex-col md:flex-row items-center justify-between gap-3">
        <div className="flex-1 w-full flex items-center gap-2">
          <Download className="w-5 h-5 text-sky-400 shrink-0" />
          <input
            type="text"
            value={quickUrl}
            onChange={(e) => setQuickUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleQuickDownload()}
            placeholder="Dán link Douyin / TikTok / Kuaishou vào đây..."
            className="flex-1 bg-slate-950 border border-slate-800 focus:border-sky-500 rounded-xl px-3.5 py-2 text-xs text-white placeholder-slate-500 outline-none"
          />

          <select
            value={targetAccount}
            onChange={(e) => setTargetAccount(e.target.value)}
            className="bg-slate-950 border border-slate-800 rounded-xl px-2.5 py-2 text-xs text-slate-300 outline-none"
          >
            {sources.download_subfolders?.map(s => (
              <option key={s.id} value={s.folder_name}>Lưu vào: {s.folder_name}/</option>
            ))}
            <option value="_new_subfolder_">➕ [Tạo subfolder mới...]</option>
          </select>

          <button
            onClick={handleQuickDownload}
            className="px-4 py-2 bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold text-xs rounded-xl shadow-lg shadow-sky-500/20 flex items-center gap-1.5 shrink-0 transition active:scale-95"
          >
            <Download className="w-3.5 h-3.5" /> Tải Về
          </button>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={handlePickLocalFiles}
            className="px-3.5 py-2 bg-gradient-to-r from-emerald-500/20 to-teal-500/20 hover:from-emerald-500/30 hover:to-teal-500/30 text-emerald-300 border border-emerald-500/40 rounded-xl text-xs font-bold flex items-center gap-1.5 shadow-md transition active:scale-95"
            title="Mở Windows Explorer chọn trực tiếp 1 hoặc nhiều file video"
          >
            <FileVideo className="w-3.5 h-3.5" /> Chọn File Video (Máy)
          </button>

          <button
            onClick={handlePickLocalFolder}
            className="px-3.5 py-2 bg-gradient-to-r from-amber-500/20 to-orange-500/20 hover:from-amber-500/30 hover:to-orange-500/30 text-amber-300 border border-amber-500/40 rounded-xl text-xs font-bold flex items-center gap-1.5 shadow-md transition active:scale-95"
            title="Mở Windows Explorer chọn cả thư mục chứa video trên máy"
          >
            <Laptop className="w-3.5 h-3.5" /> Chọn Thư Mục Video (Máy)
          </button>

          <button
            onClick={() => fileInputRef.current?.click()}
            className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 rounded-xl text-xs font-semibold flex items-center gap-1.5"
            title="Nạp trực tiếp file video từ ổ đĩa vào Studio"
          >
            <Upload className="w-3.5 h-3.5" /> Nạp File
          </button>
        </div>
      </div>

      {/* 3. Ingestion Split View: Sources Tree + Video Repository */}
      <div className="grid grid-cols-12 gap-4 flex-1 min-h-[460px]">
        {/* Left Sidebar (4 cols) */}
        <div className="col-span-4 bg-slate-900 border border-slate-800 rounded-2xl p-3.5 flex flex-col">
          <div className="flex items-center justify-between pb-2.5 border-b border-slate-800">
            <span className="font-bold text-xs text-white uppercase tracking-wider flex items-center gap-1.5">
              <FolderPlus className="w-4 h-4 text-sky-400" /> Cây Thư Mục Nguồn
            </span>
            <button
              onClick={() => handleFilterFolder('all', 'all')}
              className="text-[10px] text-sky-400 hover:underline"
            >
              Hiện tất cả
            </button>
          </div>

          <div className="flex-1 overflow-y-auto space-y-2 mt-2.5 pr-1">
            <div className="text-[11px] text-slate-400 uppercase font-bold tracking-wider px-1">
              Tài Khoản Theo Dõi (Downloads):
            </div>
            {sources.download_subfolders?.map(sub => {
              const isAct = activeSourceType === 'subfolder' && activeSourceId === sub.id;
              return (
                <div
                  key={sub.id}
                  onClick={() => handleFilterFolder('subfolder', sub.id)}
                  className={`p-2.5 rounded-xl cursor-pointer transition flex items-center justify-between group ${
                    isAct ? 'bg-sky-500/10 border-2 border-sky-400' : 'bg-slate-950/80 border border-slate-800 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <Folder className="w-4 h-4 text-sky-400 shrink-0" />
                    <div className="min-w-0">
                      <p className="text-xs font-bold text-white truncate">{sub.name}</p>
                      <p className="text-[10px] text-slate-400 font-mono">{sub.video_count} video • Kênh tải về</p>
                    </div>
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); api.openFolder(sub.path); }}
                    className="text-[10px] text-slate-400 hover:text-white px-1.5 py-0.5 bg-slate-800 rounded border border-slate-700 shrink-0"
                  >
                    📂 Mở
                  </button>
                </div>
              );
            })}

            {/* Local Folders */}
            <div className="border-t border-slate-800 my-2 pt-2">
              <div className="text-[11px] text-amber-400 uppercase font-bold tracking-wider px-1">
                Thư Mục Có Sẵn Trên Máy:
              </div>
            </div>
            {sources.local_folders?.length > 0 ? (
              sources.local_folders.map(loc => {
                const isAct = activeSourceType === 'local' && activeSourceId === loc.id;
                return (
                  <div
                    key={loc.id}
                    onClick={() => handleFilterFolder('local', loc.id)}
                    className={`p-2.5 rounded-xl cursor-pointer transition flex items-center justify-between group ${
                      isAct ? 'bg-amber-500/10 border-2 border-amber-400' : 'bg-slate-950/80 border border-amber-500/30 hover:border-amber-400'
                    }`}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <Laptop className="w-4 h-4 text-amber-400 shrink-0" />
                      <div className="min-w-0">
                        <p className="text-xs font-semibold text-amber-200 truncate">{loc.name}</p>
                        <p className="text-[10px] text-slate-400 font-mono">{loc.video_count} video • Thư mục máy</p>
                      </div>
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); api.openFolder(loc.path); }}
                      className="text-[10px] text-slate-400 hover:text-white px-1.5 py-0.5 bg-slate-800 rounded border border-slate-700 shrink-0"
                    >
                      📂 Mở
                    </button>
                  </div>
                );
              })
            ) : (
              <p className="text-xs text-slate-500 px-2 py-1 italic">
                Chưa có thư mục máy nào
              </p>
            )}
          </div>

          <div className="space-y-1.5 mt-3 pt-2 border-t border-slate-800">
            <button
              onClick={handlePickLocalFolder}
              className="w-full py-2 bg-slate-800 hover:bg-slate-700 text-amber-300 rounded-xl text-xs font-bold border border-amber-500/30 flex items-center justify-center gap-1.5 transition active:scale-95"
              title="Mở Windows Explorer để duyệt và thêm thư mục"
            >
              <Laptop className="w-3.5 h-3.5" /> Thêm Thư Mục Máy Tính
            </button>

            <button
              onClick={handleManualPathPrompt}
              className="w-full py-1.5 bg-slate-950 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded-xl text-[11px] font-medium border border-slate-800 flex items-center justify-center gap-1.5 transition"
              title="Dán đường dẫn thư mục có sẵn trên ổ đĩa"
            >
              📋 Dán Đường Dẫn Thư Mục
            </button>
          </div>
        </div>

        {/* Right Video Cards Repository (8 cols) */}
        <div className="col-span-8 bg-slate-900 border border-slate-800 rounded-2xl p-4 flex flex-col">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <div>
              <span className="font-bold text-xs text-white uppercase tracking-wider">
                Danh Sách Video Trong: {activeSourceType === 'local' ? activeSourceId : `downloads/${activeSourceId}/`} ({videosList.length} video)
              </span>
            </div>

            {/* Filter tags */}
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setCategoryFilter('all')}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition ${
                  categoryFilter === 'all'
                    ? 'bg-sky-500/20 text-sky-400 border border-sky-500/30'
                    : 'bg-slate-800 text-slate-400 hover:text-white'
                }`}
              >
                Tất cả ({videosList.length})
              </button>
              <button
                onClick={() => setCategoryFilter('translate')}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition ${
                  categoryFilter === 'translate'
                    ? 'bg-sky-500/20 text-sky-400 border border-sky-500/30'
                    : 'bg-slate-800 text-slate-400 hover:text-white'
                }`}
              >
                🌐 Cần Dịch Sub
              </button>
              <button
                onClick={() => setCategoryFilter('remix')}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition ${
                  categoryFilter === 'remix'
                    ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                    : 'bg-slate-800 text-slate-400 hover:text-white'
                }`}
              >
                ⚡ Gợi Ý Remix
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto mt-3 space-y-2 pr-1">
            {loading ? (
              <div className="text-center py-12 text-slate-500 text-xs flex items-center justify-center gap-2">
                <RefreshCw className="w-4 h-4 animate-spin text-sky-400" /> Đang nạp danh sách video từ ổ đĩa...
              </div>
            ) : filteredVideos.length === 0 ? (
              <div className="text-center py-12 text-slate-500 text-xs space-y-3">
                <p>Không tìm thấy video nào trong thư mục này</p>
                <div className="flex items-center justify-center gap-2">
                  <button
                    onClick={handlePickLocalFiles}
                    className="px-3 py-1.5 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/30 rounded-lg text-xs font-semibold"
                  >
                    📂 Chọn File Video Từ Máy
                  </button>
                  <button
                    onClick={handlePickLocalFolder}
                    className="px-3 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/30 rounded-lg text-xs font-semibold"
                  >
                    📁 Quét Thư Mục Khác
                  </button>
                </div>
              </div>
            ) : (
              filteredVideos.map(v => (
                <div
                  key={v.path || v.filename}
                  className="p-3 rounded-xl bg-slate-950/70 border border-slate-800 hover:border-slate-700 transition flex items-center justify-between gap-4 group"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-12 h-16 rounded-lg bg-slate-800 shrink-0 film-frame relative overflow-hidden border border-slate-700 flex items-center justify-center text-xs">
                      {v.suggest_remix ? '💃' : '🎬'}
                      <span className="absolute bottom-0.5 right-0.5 bg-black/80 text-[9px] font-mono px-1 rounded text-white">
                        {v.duration_str || '00:15'}
                      </span>
                    </div>

                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-white truncate" title={v.path || v.filename}>
                        {v.filename}
                      </p>
                      <div className="flex items-center gap-2 text-[11px] text-slate-400 mt-0.5">
                        <span className="text-sky-300 font-mono text-[10px]">📁 {v.subfolder}/</span>
                        <span>• 9:16</span>
                        <span className="text-slate-500">{v.size_mb} MB</span>
                      </div>
                      <div className="flex items-center gap-1.5 mt-1">
                        {v.suggest_remix ? (
                          <span className="text-[10px] bg-amber-500/10 text-amber-300 border border-amber-500/30 px-1.5 py-0.2 rounded font-medium">
                            ⚡ Video nhạc nền (Gợi ý Remix)
                          </span>
                        ) : (
                          <span className="text-[10px] bg-sky-500/10 text-sky-300 border border-sky-500/30 px-1.5 py-0.2 rounded font-medium">
                            🌐 Có lời thoại Trung (Cần dịch)
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => onSelectVideo(v, 'translate')}
                      className="px-3 py-1.5 bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold text-xs rounded-lg shadow-md transition active:scale-95 flex items-center gap-1"
                    >
                      <Globe className="w-3.5 h-3.5" /> Dịch & Biên Tập
                    </button>
                    <button
                      onClick={() => onSelectVideo(v, 'remix')}
                      className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-amber-300 border border-amber-500/30 font-semibold text-xs rounded-lg transition active:scale-95 flex items-center gap-1"
                    >
                      <Zap className="w-3.5 h-3.5" /> Chỉ Lách BQ
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
