import React, { useState, useEffect, useRef } from 'react';
import { 
  Share2, Folder, ExternalLink, CheckCircle2, Clock, 
  Sparkles, Filter, Video, AlertTriangle 
} from 'lucide-react';
import * as api from '../services/api';

export default function PublishingScreen({ showToast }) {
  const [outputRootDir, setOutputRootDir] = useState('D:\\Mine\\dich-video\\output\\ready_to_upload\\');
  const [activeSubfolder, setActiveSubfolder] = useState('all');
  const [outputSubfolders, setOutputSubfolders] = useState([]);
  const [readyVideos, setReadyVideos] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  const folderInputRef = useRef(null);

  useEffect(() => {
    loadConfig();
    loadPublishData();
  }, [activeSubfolder]);

  const loadConfig = async () => {
    const cfg = await api.getConfig();
    if (cfg && cfg.output_root_dir) {
      setOutputRootDir(api.formatWinPath(cfg.output_root_dir));
    }
  };

  const loadPublishData = async () => {
    setIsLoading(true);
    try {
      const [subList, vidList] = await Promise.all([
        api.getPublishSubfolders(),
        api.getPublishVideos(activeSubfolder)
      ]);
      if (subList) setOutputSubfolders(subList);
      if (vidList) {
        setReadyVideos(vidList.map(v => ({
          id: v.id || v.filename,
          title: v.filename,
          subfolder: v.subfolder,
          duration: v.duration_str || '00:15',
          size_mb: v.size_mb,
          path: v.path,
          platforms: {
            tiktok: v.platforms?.tiktok?.is_published || false,
            reels: v.platforms?.reels?.is_published || false,
            shorts: v.platforms?.shorts?.is_published || false,
          }
        })));
      }
    } catch (e) {
      console.warn("Lỗi load publish data:", e);
    } finally {
      setIsLoading(false);
    }
  };

  const handleTogglePlatform = (videoId, platform) => {
    setReadyVideos(prev => prev.map(v => {
      if (v.id === videoId) {
        const nextStatus = !v.platforms[platform];
        api.togglePublish(videoId, platform, nextStatus).catch(() => {});
        showToast(
          nextStatus 
            ? `✓ Đã đánh dấu <b>Đã Đăng</b> lên ${platform.toUpperCase()}`
            : `Đã chuyển về <b>Chưa Đăng</b> trên ${platform.toUpperCase()}`,
          nextStatus ? 'success' : 'info'
        );
        return {
          ...v,
          platforms: { ...v.platforms, [platform]: nextStatus }
        };
      }
      return v;
    }));
  };

  // Browser folder picker cho output_root
  const triggerFolderPicker = async () => {
    if (window.showDirectoryPicker) {
      try {
        const dirHandle = await window.showDirectoryPicker({ mode: 'read' });
        const newPath = `D:/Mine/dich-video/output/${dirHandle.name}/`;
        setOutputRootDir(api.formatWinPath(newPath));
        await api.updateConfig({ output_root_dir: newPath });
        showToast(`✓ Đã đổi thư mục xuất thành phẩm: ${dirHandle.name}`, 'success');
        return;
      } catch (err) {
        if (err.name === 'AbortError') return;
      }
    }

    if (folderInputRef.current) {
      folderInputRef.current.value = '';
      folderInputRef.current.click();
    }
  };

  const handleFolderInput = (e) => {
    const files = Array.from(e.target.files);
    if (!files.length) return;
    const name = files[0].webkitRelativePath?.split('/')[0] || 'ready_to_upload';
    const newPath = `D:/Mine/dich-video/output/${name}/`;
    setOutputRootDir(api.formatWinPath(newPath));
    api.updateConfig({ output_root_dir: newPath });
    showToast(`✓ Đã đổi thư mục xuất thành phẩm: ${name}`, 'success');
  };

  const filteredVideos = activeSubfolder === 'all'
    ? readyVideos
    : readyVideos.filter(v => v.subfolder === activeSubfolder);

  const stats = {
    total: readyVideos.length,
    tiktok: readyVideos.filter(v => v.platforms.tiktok).length,
    reels: readyVideos.filter(v => v.platforms.reels).length,
    shorts: readyVideos.filter(v => v.platforms.shorts).length,
  };

  return (
    <div className="flex-1 flex flex-col p-4 overflow-y-auto bg-slate-950 space-y-4">
      {/* Hidden browser folder picker */}
      <input
        type="file"
        ref={folderInputRef}
        webkitdirectory="true"
        directory="true"
        multiple
        className="hidden"
        onChange={handleFolderInput}
      />

      {/* 1. Output Root Directory Bar */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-3.5 shadow-lg flex flex-col md:flex-row items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2 text-slate-300">
          <span className="text-emerald-400 font-bold flex items-center gap-1.5">
            <Folder className="w-4 h-4" /> Thư mục đầu ra gốc (Cha):
          </span>
          <span className="font-mono bg-slate-950 px-3 py-1 rounded-lg border border-slate-800 text-white font-semibold">
            {outputRootDir}
          </span>
          <button
            onClick={triggerFolderPicker}
            className="px-3 py-1.5 bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 rounded-lg border border-emerald-500/30 flex items-center gap-1.5 font-semibold transition active:scale-95"
          >
            <Folder className="w-3.5 h-3.5" /> Chọn Thư Mục Khác
          </button>
          <button
            onClick={() => api.openFolder(outputRootDir)}
            className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg border border-slate-700 flex items-center gap-1"
          >
            <ExternalLink className="w-3 h-3" /> Mở Thư Mục Cha
          </button>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[11px] text-sky-400 font-medium bg-sky-500/10 border border-sky-500/20 px-2.5 py-1 rounded-lg">
            ✓ Video thành phẩm tự động xuất theo subfolder: <code className="font-mono font-bold">ready_to_upload/&#123;subfolder&#125;/</code>
          </span>
        </div>
      </div>

      {/* 2. Stats Dashboard Cards */}
      <div className="grid grid-cols-4 gap-3">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 flex items-center justify-between">
          <div>
            <p className="text-[11px] text-slate-400">Tổng Video Đã Render</p>
            <p className="text-xl font-extrabold text-white mt-0.5">{stats.total}</p>
          </div>
          <span className="text-2xl">🎬</span>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 flex items-center justify-between">
          <div>
            <p className="text-[11px] text-slate-400">Đã Đăng TikTok</p>
            <p className="text-xl font-extrabold text-cyan-400 mt-0.5">{stats.tiktok}</p>
          </div>
          <span className="text-2xl">🎵</span>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 flex items-center justify-between">
          <div>
            <p className="text-[11px] text-slate-400">Đã Đăng Facebook Reels</p>
            <p className="text-xl font-extrabold text-blue-400 mt-0.5">{stats.reels}</p>
          </div>
          <span className="text-2xl">📘</span>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 flex items-center justify-between">
          <div>
            <p className="text-[11px] text-slate-400">Đã Đăng YouTube Shorts</p>
            <p className="text-xl font-extrabold text-rose-400 mt-0.5">{stats.shorts}</p>
          </div>
          <span className="text-2xl">▶️</span>
        </div>
      </div>

      {/* 3. Multi-platform Anti-duplicate Matrix Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 flex flex-col flex-1 shadow-xl">
        <div className="flex items-center justify-between pb-3 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <Share2 className="w-4 h-4 text-sky-400" />
            <span className="font-bold text-xs text-white uppercase tracking-wider">
              Ma Trận Kiểm Soát Xuất Bản Đa Nền Tảng (Chống Trùng Lặp)
            </span>
          </div>

          {/* Subfolder filters */}
          <div className="flex items-center gap-1.5 flex-wrap">
            <button
              onClick={() => setActiveSubfolder('all')}
              className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition ${
                activeSubfolder === 'all'
                  ? 'bg-sky-500 text-slate-950 font-bold'
                  : 'bg-slate-800 text-slate-400 hover:text-white'
              }`}
            >
              Tất cả kênh ({readyVideos.length})
            </button>
            {outputSubfolders.map(sub => (
              <button
                key={sub.id}
                onClick={() => setActiveSubfolder(sub.id)}
                className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition ${
                  activeSubfolder === sub.id
                    ? 'bg-sky-500 text-slate-950 font-bold'
                    : 'bg-slate-800 text-slate-400 hover:text-white'
                }`}
              >
                {sub.folder_name} ({sub.video_count})
              </button>
            ))}
          </div>
        </div>

        {/* Video Matrix List */}
        <div className="flex-1 overflow-y-auto mt-3 space-y-2.5 pr-1">
          {filteredVideos.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center text-slate-400">
              <Video className="w-12 h-12 text-slate-600 mb-3 stroke-1" />
              <p className="font-bold text-slate-300 text-sm">Chưa có video thành phẩm trong thư mục này</p>
              <p className="text-xs text-slate-500 mt-1 max-w-sm">
                Hãy vào tab <b>Studio</b> chọn video và bấm <b>Xuất Video (NVENC)</b> để tạo video đã lách bản quyền và phân phối!
              </p>
            </div>
          ) : (
            filteredVideos.map(v => (
            <div
              key={v.id}
              className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 hover:border-slate-700 transition flex items-center justify-between gap-4"
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-12 h-14 rounded-lg bg-slate-800 shrink-0 film-frame relative overflow-hidden flex items-center justify-center text-xs">
                  🎬
                  <span className="absolute bottom-0.5 right-0.5 bg-black/80 text-[9px] font-mono px-1 rounded text-white">
                    {v.duration}
                  </span>
                </div>
                <div className="min-w-0">
                  <p className="text-xs font-bold text-white truncate">{v.title}</p>
                  <p className="text-[11px] text-slate-400 font-mono mt-0.5">
                    Subfolder: <span className="text-sky-300">ready_to_upload/{v.subfolder}/</span> • {v.size_mb} MB
                  </p>
                </div>
              </div>

              {/* 3 Platforms Check Buttons */}
              <div className="flex items-center gap-2 shrink-0">
                {/* TikTok */}
                <button
                  onClick={() => handleTogglePlatform(v.id, 'tiktok')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 ${
                    v.platforms.tiktok
                      ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm shadow-cyan-500/10'
                      : 'bg-slate-800 text-slate-400 hover:text-white border border-slate-700'
                  }`}
                >
                  <span>🎵 TikTok:</span>
                  <span>{v.platforms.tiktok ? '✓ Đã Đăng' : '⏳ Chưa Đăng'}</span>
                </button>

                {/* Reels */}
                <button
                  onClick={() => handleTogglePlatform(v.id, 'reels')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 ${
                    v.platforms.reels
                      ? 'bg-blue-500/20 text-blue-300 border border-blue-500/40 shadow-sm shadow-blue-500/10'
                      : 'bg-slate-800 text-slate-400 hover:text-white border border-slate-700'
                  }`}
                >
                  <span>📘 FB Reels:</span>
                  <span>{v.platforms.reels ? '✓ Đã Đăng' : '⏳ Chưa Đăng'}</span>
                </button>

                {/* Shorts */}
                <button
                  onClick={() => handleTogglePlatform(v.id, 'shorts')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 ${
                    v.platforms.shorts
                      ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40 shadow-sm shadow-rose-500/10'
                      : 'bg-slate-800 text-slate-400 hover:text-white border border-slate-700'
                  }`}
                >
                  <span>▶️ Shorts:</span>
                  <span>{v.platforms.shorts ? '✓ Đã Đăng' : '⏳ Chưa Đăng'}</span>
                </button>

                <button
                  onClick={() => api.openFolder(`${outputRootDir}\\${v.subfolder}`)}
                  className="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-semibold border border-slate-700 flex items-center gap-1"
                  title="Mở thư mục chứa file trong Windows Explorer"
                >
                  <ExternalLink className="w-3.5 h-3.5" /> Mở File
                </button>
              </div>
            </div>
          )))}
        </div>
      </div>
    </div>
  );
}
