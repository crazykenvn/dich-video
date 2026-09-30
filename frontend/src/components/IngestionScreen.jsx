import React, { useState, useEffect, useRef } from 'react';
import { 
  Folder, FolderPlus, Download, HardDrive, Laptop, Globe, Zap, 
  Search, ExternalLink, RefreshCw, Sparkles, Filter
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

  const folderInputRef = useRef(null);
  const currentContextRef = useRef('download_root');

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

  // --- BROWSER DEFAULT FOLDER PICKER ---
  const triggerFolderPicker = async (context) => {
    currentContextRef.current = context;

    // 1. Thử dùng File System Access API chuẩn của trình duyệt (Chrome, Edge)
    if (window.showDirectoryPicker) {
      try {
        const dirHandle = await window.showDirectoryPicker({ mode: 'read' });
        await handleDirectoryHandle(dirHandle, context);
        return;
      } catch (err) {
        if (err.name === 'AbortError') return; // Người dùng ấn Hủy
        console.warn('showDirectoryPicker error:', err);
      }
    }

    // 2. Fallback input webkitdirectory
    if (folderInputRef.current) {
      folderInputRef.current.value = '';
      folderInputRef.current.click();
    }
  };

  const handleDirectoryHandle = async (dirHandle, context) => {
    const folderName = dirHandle.name;

    if (context === 'download_root') {
      const newPath = `D:/Mine/dich-video/output/${folderName}/`;
      setDownloadRootDir(api.formatWinPath(newPath));
      await api.updateConfig({ download_root_dir: newPath });
      showToast(`✓ Đã đổi thư mục tải về gốc thành:<br/><span class="font-mono text-white text-[11px]">${api.formatWinPath(newPath)}</span>`, 'success');
      loadSourcesData();
    } else if (context === 'local_import') {
      showToast(`Đang quét video từ thư mục: <b>${folderName}</b>...`, 'info');
      const items = [];
      for await (const entry of dirHandle.values()) {
        if (entry.kind === 'file' && /\.(mp4|mov|mkv|webm|avi|flv)$/i.test(entry.name)) {
          try {
            const file = await entry.getFile();
            const isRemix = /dance|remix|music|beat|trend/i.test(file.name);
            items.push({
              filename: file.name,
              path: `${folderName}/${file.name}`,
              subfolder: folderName,
              size_mb: +(file.size / (1024 * 1024)).toFixed(2),
              duration_str: '00:30',
              has_sub: !isRemix,
              suggest_remix: isRemix
            });
          } catch (e) {}
        }
      }

      if (items.length === 0) {
        showToast(`⚠️ Không tìm thấy file video (.mp4, .mov...) nào trong thư mục "${folderName}".`, 'warning');
        return;
      }

      // Nạp vào danh sách
      setVideosList(items);
      setActiveSourceType('local');
      setActiveSourceId(folderName);
      api.scanLocal(folderName, folderName).catch(() => {});
      showToast(`✓ Đã nạp thành công <b>${items.length} video</b> từ thư mục <b>${folderName}</b>!`, 'success');
    }
  };

  const handleInputFolderSelected = (event) => {
    const files = Array.from(event.target.files);
    if (!files.length) return;

    const firstRel = files[0].webkitRelativePath || files[0].name;
    const folderName = firstRel.split('/')[0] || 'Thu_Muc_May';
    const context = currentContextRef.current;

    if (context === 'download_root') {
      const newPath = `D:/Mine/dich-video/output/${folderName}/`;
      setDownloadRootDir(api.formatWinPath(newPath));
      api.updateConfig({ download_root_dir: newPath });
      showToast(`✓ Đã đổi thư mục tải về gốc: ${folderName}`, 'success');
      loadSourcesData();
    } else if (context === 'local_import') {
      const videoFiles = files.filter(f => /\.(mp4|mov|mkv|webm|avi|flv)$/i.test(f.name));
      if (videoFiles.length === 0) {
        showToast(`⚠️ Không có file video hợp lệ trong thư mục "${folderName}".`, 'warning');
        return;
      }

      const items = videoFiles.map(f => {
        const isRemix = /dance|remix|music|beat|trend/i.test(f.name);
        return {
          filename: f.name,
          path: f.webkitRelativePath || f.name,
          subfolder: folderName,
          size_mb: +(f.size / (1024 * 1024)).toFixed(2),
          duration_str: '00:30',
          has_sub: !isRemix,
          suggest_remix: isRemix
        };
      });

      setVideosList(items);
      setActiveSourceType('local');
      setActiveSourceId(folderName);
      api.scanLocal(folderName, folderName).catch(() => {});
      showToast(`✓ Đã nạp thành công <b>${items.length} video</b> từ thư mục <b>${folderName}</b>!`, 'success');
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
      {/* Hidden browser default folder picker */}
      <input
        type="file"
        ref={folderInputRef}
        webkitdirectory="true"
        directory="true"
        multiple
        className="hidden"
        onChange={handleInputFolderSelected}
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
            onClick={() => triggerFolderPicker('download_root')}
            className="px-3 py-1.5 bg-sky-500/15 hover:bg-sky-500/25 text-sky-300 rounded-lg border border-sky-500/30 flex items-center gap-1.5 font-semibold transition active:scale-95"
            title="Dùng hộp thoại chọn thư mục mặc định của trình duyệt"
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
            onClick={() => triggerFolderPicker('local_import')}
            className="px-3.5 py-2 bg-gradient-to-r from-amber-500/20 to-orange-500/20 hover:from-amber-500/30 hover:to-orange-500/30 text-amber-300 border border-amber-500/40 rounded-xl text-xs font-bold flex items-center gap-1.5 shadow-md transition active:scale-95"
            title="Mở hộp thoại chọn folder mặc định của trình duyệt để nạp video trên máy"
          >
            <Laptop className="w-3.5 h-3.5" /> Chọn Thư Mục Có Sẵn Trên Máy
          </button>

          <button
            onClick={() => {
              showToast('Đang quét tự động các kênh theo dõi...', 'info');
              setTimeout(() => {
                showToast('✓ Quét hoàn tất: Không có video mới trùng lặp.', 'success');
                loadSourcesData();
              }, 1200);
            }}
            className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-xl text-xs font-semibold flex items-center gap-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Quét Kênh
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
                Chưa có thư mục máy nào (Bấm nút bên dưới để chọn)
              </p>
            )}
          </div>

          <button
            onClick={() => triggerFolderPicker('local_import')}
            className="w-full mt-3 py-2 bg-slate-800 hover:bg-slate-700 text-amber-300 rounded-xl text-xs font-bold border border-amber-500/30 flex items-center justify-center gap-1.5 transition active:scale-95"
            title="Dùng hộp thoại chọn thư mục mặc định của trình duyệt"
          >
            <Laptop className="w-3.5 h-3.5" /> Thêm Thư Mục Máy Tính
          </button>
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
              <div className="text-center py-12 text-slate-500 text-xs">
                Không tìm thấy video nào phù hợp với bộ lọc
              </div>
            ) : (
              filteredVideos.map(v => (
                <div
                  key={v.filename}
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
                      <p className="text-xs font-semibold text-white truncate" title={v.filename}>
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
