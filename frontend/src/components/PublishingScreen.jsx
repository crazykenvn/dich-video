import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  Share2, Folder, ExternalLink, CheckCircle2, Clock,
  Sparkles, Filter, Video, AlertTriangle, Play, Copy,
  Check, Search, X, CheckSquare, Square, RotateCcw,
  Eye, ChevronLeft, ChevronRight, RefreshCw, ChevronDown, FolderOpen, Settings
} from 'lucide-react';
import * as api from '../services/api';

function getCleanTitle(filename) {
  if (!filename) return '';
  let title = filename;
  title = title.replace(/\.(mp4|mov|mkv|webm|avi)$/i, '');
  title = title.replace(/(_remix|_stealth|_translated|_dubbed|_hardsub)+$/gi, '');
  title = title.replace(/_[0-9]{10,25}$/g, '');
  return title.trim();
}

export default function PublishingScreen({ showToast }) {
  const [outputRootDir, setOutputRootDir] = useState('');
  const [activeSubfolder, setActiveSubfolder] = useState('all');
  const [outputSubfolders, setOutputSubfolders] = useState([]);
  const [readyVideos, setReadyVideos] = useState([]);
  const [isLoading, setIsLoading] = useState(false);

  // Search & Filter
  const [searchQuery, setSearchQuery] = useState('');
  const [filterPending, setFilterPending] = useState('all'); // all, pending_tiktok, pending_reels, pending_shorts, pending_all, fully_published

  // Folder Selector Dropdown state
  const folderDropdownRef = useRef(null);
  const [isFolderDropdownOpen, setIsFolderDropdownOpen] = useState(false);
  const [folderSearchQuery, setFolderSearchQuery] = useState('');
  const [hideEmptyFolders, setHideEmptyFolders] = useState(true);

  // Multi-selection
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [isBulkProcessing, setIsBulkProcessing] = useState(false);

  // Video Preview Modal
  const [previewVideo, setPreviewVideo] = useState(null);
  const [copiedType, setCopiedType] = useState(null); // 'title' | 'path' | null

  // Storage Modal (đồng bộ với IngestionScreen)
  const [showStorageModal, setShowStorageModal] = useState(false);

  useEffect(() => {
    loadConfig();
  }, []);

  useEffect(() => {
    loadPublishData();
  }, [activeSubfolder]);

  // Click outside to close folder dropdown
  useEffect(() => {
    function handleClickOutside(event) {
      if (folderDropdownRef.current && !folderDropdownRef.current.contains(event.target)) {
        setIsFolderDropdownOpen(false);
      }
    }
    if (isFolderDropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isFolderDropdownOpen]);

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
        api.getPublishVideos(activeSubfolder, 'none')
      ]);
      if (subList) setOutputSubfolders(subList);
      if (vidList) {
        setReadyVideos(vidList.map(v => ({
          id: v.id || v.video_id,
          video_id: v.id || v.video_id,
          filename: v.filename,
          title: v.filename,
          subfolder: v.subfolder,
          duration: v.duration_str || '00:15',
          size_mb: v.size_mb,
          path: v.path,
          process_type: v.process_type || '🎬 Thành phẩm',
          platforms: {
            tiktok: v.platforms?.tiktok?.is_published ?? v.tiktok?.is_published ?? false,
            reels: v.platforms?.reels?.is_published ?? v.reels?.is_published ?? false,
            shorts: v.platforms?.shorts?.is_published ?? v.shorts?.is_published ?? false,
          }
        })));
      }
      // Dọn selection không còn tồn tại
      setSelectedIds(new Set());
    } catch (e) {
      console.warn("Lỗi load publish data:", e);
      if (showToast) showToast("Không thể tải danh sách video thành phẩm", "error");
    } finally {
      setIsLoading(false);
    }
  };

  // Toggle single platform
  const handleTogglePlatform = async (videoId, platform) => {
    const targetVideo = readyVideos.find(v => v.id === videoId);
    if (!targetVideo) return;

    const nextStatus = !targetVideo.platforms[platform];
    const platformLabel = platform === 'tiktok' ? 'TikTok' : platform === 'reels' ? 'FB Reels' : 'YT Shorts';

    // Optimistic UI update
    setReadyVideos(prev => prev.map(v => {
      if (v.id === videoId) {
        return {
          ...v,
          platforms: { ...v.platforms, [platform]: nextStatus }
        };
      }
      return v;
    }));

    if (previewVideo && previewVideo.id === videoId) {
      setPreviewVideo(prev => ({
        ...prev,
        platforms: { ...prev.platforms, [platform]: nextStatus }
      }));
    }

    try {
      await api.togglePublish(videoId, platform, nextStatus);
      if (showToast) {
        showToast(
          nextStatus 
            ? `✓ Đã đánh dấu <b>Đã Đăng</b> lên ${platformLabel}`
            : `Đã chuyển về <b>Chưa Đăng</b> trên ${platformLabel}`,
          nextStatus ? 'success' : 'info'
        );
      }
    } catch (err) {
      // Revert upon failure
      setReadyVideos(prev => prev.map(v => {
        if (v.id === videoId) {
          return {
            ...v,
            platforms: { ...v.platforms, [platform]: !nextStatus }
          };
        }
        return v;
      }));
      if (showToast) showToast(`Lỗi cập nhật trạng thái ${platformLabel}: ${err.message}`, 'error');
    }
  };

  // Bulk toggle status
  const handleBulkToggle = async (platform, isPublished) => {
    if (selectedIds.size === 0) return;
    const ids = Array.from(selectedIds);
    setIsBulkProcessing(true);

    try {
      await api.bulkTogglePublish(ids, platform, isPublished);
      
      setReadyVideos(prev => prev.map(v => {
        if (selectedIds.has(v.id)) {
          if (platform === 'all') {
            return {
              ...v,
              platforms: {
                tiktok: isPublished,
                reels: isPublished,
                shorts: isPublished,
              }
            };
          } else {
            return {
              ...v,
              platforms: {
                ...v.platforms,
                [platform]: isPublished,
              }
            };
          }
        }
        return v;
      }));

      const targetLabel = platform === 'all' 
        ? 'Tất cả 3 nền tảng' 
        : platform === 'tiktok' ? 'TikTok' : platform === 'reels' ? 'FB Reels' : 'YT Shorts';
      
      if (showToast) {
        showToast(
          isPublished 
            ? `✓ Đã đánh dấu Đã Đăng ${targetLabel} cho ${ids.length} video` 
            : `Đã reset về Chưa Đăng cho ${ids.length} video`,
          'success'
        );
      }
      setSelectedIds(new Set());
    } catch (err) {
      if (showToast) showToast(`Lỗi thao tác hàng loạt: ${err.message}`, 'error');
    } finally {
      setIsBulkProcessing(false);
    }
  };

  // Selection helpers
  const toggleSelectVideo = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === displayedVideos.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(displayedVideos.map(v => v.id)));
    }
  };

  // Native Windows Explorer folder picker
  const triggerFolderPicker = async () => {
    const res = await api.pickFolder();
    if (res && res.success && res.path) {
      setOutputRootDir(api.formatWinPath(res.path));
      await api.updateConfig({ output_root_dir: res.path });
      if (showToast) {
        showToast(`✓ Đã đổi thư mục xuất thành phẩm thành:<br/><span class="font-mono text-white text-[11px]">${api.formatWinPath(res.path)}</span>`, 'success');
      }
      loadPublishData();
    }
  };

  // Quick Copy utilities
  const handleCopyText = (text, type = 'text') => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopiedType(type);
    setTimeout(() => setCopiedType(null), 1800);
    if (showToast) {
      showToast(
        type === 'title' 
          ? '✓ Đã sao chép <b>Tiêu đề video</b> sạch vào clipboard!'
          : '✓ Đã sao chép <b>Đường dẫn file</b> vào clipboard!',
        'success'
      );
    }
  };

  // Filtered & Searched videos
  const displayedVideos = useMemo(() => {
    return readyVideos.filter(v => {
      // 1. Subfolder filter
      if (activeSubfolder !== 'all' && v.subfolder !== activeSubfolder) {
        return false;
      }

      // 2. Anti-duplicate status filter
      if (filterPending === 'pending_tiktok' && v.platforms.tiktok) return false;
      if (filterPending === 'pending_reels' && v.platforms.reels) return false;
      if (filterPending === 'pending_shorts' && v.platforms.shorts) return false;
      if (filterPending === 'pending_all' && (v.platforms.tiktok || v.platforms.reels || v.platforms.shorts)) return false;
      if (filterPending === 'fully_published' && !(v.platforms.tiktok && v.platforms.reels && v.platforms.shorts)) return false;

      // 3. Search query filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchTitle = v.filename.toLowerCase().includes(q);
        const matchSubfolder = v.subfolder.toLowerCase().includes(q);
        if (!matchTitle && !matchSubfolder) return false;
      }

      return true;
    });
  }, [readyVideos, activeSubfolder, filterPending, searchQuery]);

  // Overall statistics
  const stats = useMemo(() => {
    const list = activeSubfolder === 'all' 
      ? readyVideos 
      : readyVideos.filter(v => v.subfolder === activeSubfolder);
    const total = list.length;
    const tiktok = list.filter(v => v.platforms.tiktok).length;
    const reels = list.filter(v => v.platforms.reels).length;
    const shorts = list.filter(v => v.platforms.shorts).length;
    const fully = list.filter(v => v.platforms.tiktok && v.platforms.reels && v.platforms.shorts).length;
    const pendingAny = list.filter(v => !v.platforms.tiktok || !v.platforms.reels || !v.platforms.shorts).length;

    return { total, tiktok, reels, shorts, fully, pendingAny };
  }, [readyVideos, activeSubfolder]);

  // Active folder details
  const activeSubfolderObj = useMemo(() => {
    if (activeSubfolder === 'all') return { id: 'all', folder_name: 'Tất cả thư mục', video_count: readyVideos.length };
    return outputSubfolders.find(s => s.id === activeSubfolder) || { id: activeSubfolder, folder_name: activeSubfolder, video_count: 0 };
  }, [activeSubfolder, outputSubfolders, readyVideos]);

  // Count empty folders (0 videos)
  const emptyFoldersCount = useMemo(() => {
    return outputSubfolders.filter(s => s.video_count === 0).length;
  }, [outputSubfolders]);

  // Filtered subfolders inside dropdown
  const filteredSubfolders = useMemo(() => {
    return outputSubfolders.filter(sub => {
      if (hideEmptyFolders && sub.video_count === 0 && sub.id !== activeSubfolder) {
        return false;
      }
      if (folderSearchQuery.trim()) {
        const q = folderSearchQuery.toLowerCase().trim();
        return sub.folder_name.toLowerCase().includes(q);
      }
      return true;
    });
  }, [outputSubfolders, hideEmptyFolders, folderSearchQuery, activeSubfolder]);

  // Navigation for preview modal
  const handlePrevPreview = () => {
    if (!previewVideo) return;
    const currentIndex = displayedVideos.findIndex(v => v.id === previewVideo.id);
    if (currentIndex > 0) {
      setPreviewVideo(displayedVideos[currentIndex - 1]);
    }
  };

  const handleNextPreview = () => {
    if (!previewVideo) return;
    const currentIndex = displayedVideos.findIndex(v => v.id === previewVideo.id);
    if (currentIndex >= 0 && currentIndex < displayedVideos.length - 1) {
      setPreviewVideo(displayedVideos[currentIndex + 1]);
    }
  };

  return (
    <div className="flex-1 flex flex-col p-3 overflow-y-auto bg-slate-950 space-y-2.5">
      {/* 1. Minimal Top Header Bar (Đồng bộ chuẩn 100% với Setup Dữ Liệu Nguồn) */}
      <div className="flex items-center justify-between pb-1 flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <h1 className="text-sm font-bold text-white flex items-center gap-2">
            <Share2 className="w-4 h-4 text-sky-400" /> Quản Lý Phân Phối Đa Nền Tảng
          </h1>
          <span className="text-[11px] font-mono text-slate-400 bg-slate-900 border border-slate-800 px-2 py-0.5 rounded-lg">
            {stats.total} video
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Nút Cài đặt Thư mục tải/xuất gốc (Giống hệt Image 1 từ IngestionScreen) */}
          <button
            onClick={() => setShowStorageModal(true)}
            className="px-2.5 py-1.5 bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white rounded-xl border border-slate-800 flex items-center gap-2 text-xs font-medium transition active:scale-95 shadow-sm"
            title={`Cài đặt thư mục tải: ${outputRootDir}`}
          >
            <Folder className="w-3.5 h-3.5 text-sky-400" />
            <span className="hidden sm:inline text-slate-400">Thư mục tải:</span>
            <span className="font-mono text-sky-300 max-w-[150px] truncate font-semibold">
              {outputRootDir ? (outputRootDir.split(/[\\/]/).pop() || outputRootDir) : 'ready_to_upload'}
            </span>
            <Settings className="w-3.5 h-3.5 text-slate-400 hover:text-sky-300" />
          </button>

          <button
            onClick={loadPublishData}
            disabled={isLoading}
            className="px-2.5 py-1 bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white rounded-xl border border-slate-800 flex items-center gap-1.5 text-xs font-medium transition active:scale-95 shadow-sm disabled:opacity-50"
            title="Làm mới danh sách video"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin text-sky-400' : ''}`} />
            <span className="hidden sm:inline">Làm Mới</span>
          </button>
        </div>
      </div>

      {/* 2. Stats Dashboard Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-[11px] text-slate-400 font-medium">Tổng Đã Render</p>
            <p className="text-xl font-extrabold text-white mt-0.5">{stats.total}</p>
          </div>
          <span className="text-2xl">🎬</span>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-[11px] text-slate-400 font-medium">Đã Đăng TikTok</p>
            <p className="text-xl font-extrabold text-cyan-400 mt-0.5">{stats.tiktok}</p>
          </div>
          <span className="text-2xl">🎵</span>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-[11px] text-slate-400 font-medium">Đã Đăng FB Reels</p>
            <p className="text-xl font-extrabold text-blue-400 mt-0.5">{stats.reels}</p>
          </div>
          <span className="text-2xl">📘</span>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-[11px] text-slate-400 font-medium">Đã Đăng YT Shorts</p>
            <p className="text-xl font-extrabold text-rose-400 mt-0.5">{stats.shorts}</p>
          </div>
          <span className="text-2xl">▶️</span>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-[11px] text-slate-400 font-medium">Đủ 3 Nền Tảng</p>
            <p className="text-xl font-extrabold text-emerald-400 mt-0.5">{stats.fully}</p>
          </div>
          <span className="text-2xl">✨</span>
        </div>
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-3 flex items-center justify-between shadow-sm">
          <div>
            <p className="text-[11px] text-slate-400 font-medium">Đang Chờ Đăng</p>
            <p className="text-xl font-extrabold text-amber-400 mt-0.5">{stats.pendingAny}</p>
          </div>
          <span className="text-2xl">⏳</span>
        </div>
      </div>

      {/* 3. Multi-platform Anti-duplicate Matrix Table & Controls */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 flex flex-col flex-1 shadow-xl space-y-3">
        {/* Header: Title & Subfolder Tabs */}
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-3 pb-3 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <Share2 className="w-5 h-5 text-sky-400" />
            <div>
              <span className="font-bold text-sm text-white uppercase tracking-wider">
                Quản Lý Xuất Bản Đa Nền Tảng (Chống Up Trùng)
              </span>
              <p className="text-[11px] text-slate-400">
                Kiểm soát chính xác video nào đã đăng lên TikTok, FB Reels, YT Shorts để phân phối tối đa không trùng lặp
              </p>
            </div>
          </div>

          {/* Compact Searchable Subfolder Dropdown Selector */}
          <div className="flex items-center gap-2 relative" ref={folderDropdownRef}>
            {/* Quick "Tất cả" shortcut */}
            <button
              onClick={() => setActiveSubfolder('all')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 ${
                activeSubfolder === 'all'
                  ? 'bg-sky-500 text-slate-950 font-bold shadow-md shadow-sky-500/20'
                  : 'bg-slate-800 text-slate-300 hover:text-white border border-slate-700'
              }`}
              title="Xem tất cả video từ mọi thư mục"
            >
              <span>Tất cả ({readyVideos.length})</span>
            </button>

            {/* Dropdown Trigger Button */}
            <button
              onClick={() => setIsFolderDropdownOpen(prev => !prev)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold border flex items-center gap-2 transition max-w-[260px] ${
                activeSubfolder !== 'all'
                  ? 'bg-sky-500/15 border-sky-500/40 text-sky-300 shadow-sm shadow-sky-500/10'
                  : 'bg-slate-800 hover:bg-slate-700 border-slate-700 text-slate-200'
              }`}
              title="Chọn lọc theo thư mục / kênh cụ thể"
            >
              <Folder className="w-3.5 h-3.5 text-sky-400 shrink-0" />
              <span className="truncate">
                {activeSubfolder === 'all' ? 'Chọn thư mục kênh...' : activeSubfolderObj.folder_name}
              </span>
              {activeSubfolder !== 'all' && (
                <span className="px-1.5 py-0.2 rounded text-[10px] bg-sky-500/25 text-sky-200 font-bold shrink-0">
                  {activeSubfolderObj.video_count}
                </span>
              )}
              <ChevronDown className={`w-3.5 h-3.5 text-slate-400 transition-transform shrink-0 ${isFolderDropdownOpen ? 'rotate-180' : ''}`} />
            </button>

            {/* Clear filter button when a specific subfolder is selected */}
            {activeSubfolder !== 'all' && (
              <button
                onClick={() => setActiveSubfolder('all')}
                className="p-1.5 bg-slate-800 hover:bg-rose-500/20 text-slate-400 hover:text-rose-300 rounded-lg border border-slate-700 transition"
                title="Bỏ lọc thư mục (quay lại xem tất cả)"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}

            {/* Dropdown Menu Modal / Popover */}
            {isFolderDropdownOpen && (
              <div className="absolute right-0 top-full mt-1.5 w-80 bg-slate-900 border border-slate-700 rounded-xl shadow-2xl p-2.5 z-40 animate-in fade-in zoom-in-95 duration-150">
                {/* Search folder input */}
                <div className="relative mb-2">
                  <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    value={folderSearchQuery}
                    onChange={(e) => setFolderSearchQuery(e.target.value)}
                    placeholder="Tìm kiếm thư mục / kênh..."
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg pl-8 pr-7 py-1 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-sky-500"
                    autoFocus
                  />
                  {folderSearchQuery && (
                    <button
                      onClick={() => setFolderSearchQuery('')}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  )}
                </div>

                {/* Filter toolbar: Hide 0-video folders */}
                {emptyFoldersCount > 0 && (
                  <div className="flex items-center justify-between px-1 py-1 mb-1 text-[11px] text-slate-400 border-b border-slate-800">
                    <label className="flex items-center gap-1.5 cursor-pointer select-none">
                      <input
                        type="checkbox"
                        checked={hideEmptyFolders}
                        onChange={(e) => setHideEmptyFolders(e.target.checked)}
                        className="rounded bg-slate-950 border-slate-700 text-sky-500 focus:ring-0 w-3 h-3 cursor-pointer"
                      />
                      <span>Ẩn thư mục trống ({emptyFoldersCount})</span>
                    </label>
                    <span className="text-[10px] text-slate-500">{filteredSubfolders.length} thư mục</span>
                  </div>
                )}

                {/* Folder Items List */}
                <div className="max-h-60 overflow-y-auto space-y-1 pr-0.5">
                  {/* All option */}
                  <button
                    onClick={() => {
                      setActiveSubfolder('all');
                      setIsFolderDropdownOpen(false);
                    }}
                    className={`w-full px-2.5 py-1.5 rounded-lg text-xs font-semibold flex items-center justify-between transition ${
                      activeSubfolder === 'all'
                        ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30'
                        : 'hover:bg-slate-800 text-slate-300'
                    }`}
                  >
                    <span className="flex items-center gap-2 truncate">
                      <FolderOpen className="w-3.5 h-3.5 text-sky-400" />
                      <span>Tất cả thư mục</span>
                    </span>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <span className="px-1.5 py-0.2 rounded text-[10px] bg-slate-800 text-slate-400 font-mono">
                        {readyVideos.length}
                      </span>
                      {activeSubfolder === 'all' && <Check className="w-3.5 h-3.5 text-sky-400" />}
                    </div>
                  </button>

                  {/* List of subfolders */}
                  {filteredSubfolders.length === 0 ? (
                    <div className="py-4 text-center text-slate-500 text-xs">
                      Không tìm thấy thư mục nào khớp
                    </div>
                  ) : (
                    filteredSubfolders.map(sub => {
                      const isSelected = activeSubfolder === sub.id;
                      const isEmpty = sub.video_count === 0;

                      return (
                        <button
                          key={sub.id}
                          onClick={() => {
                            setActiveSubfolder(sub.id);
                            setIsFolderDropdownOpen(false);
                          }}
                          className={`w-full px-2.5 py-1.5 rounded-lg text-xs flex items-center justify-between transition ${
                            isSelected
                              ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30 font-bold'
                              : isEmpty
                              ? 'text-slate-500 hover:bg-slate-800/60 hover:text-slate-300'
                              : 'text-slate-300 hover:bg-slate-800 font-medium'
                          }`}
                        >
                          <span className="flex items-center gap-2 truncate min-w-0 pr-2">
                            <Folder className={`w-3.5 h-3.5 shrink-0 ${isSelected ? 'text-sky-400' : isEmpty ? 'text-slate-600' : 'text-slate-400'}`} />
                            <span className="truncate">{sub.folder_name}</span>
                          </span>
                          <div className="flex items-center gap-1.5 shrink-0">
                            <span className={`px-1.5 py-0.2 rounded text-[10px] font-mono ${
                              isSelected
                                ? 'bg-sky-500/30 text-sky-200'
                                : isEmpty
                                ? 'bg-slate-950 text-slate-600'
                                : 'bg-slate-800 text-slate-300 font-bold'
                            }`}>
                              {sub.video_count}
                            </span>
                            {isSelected && <Check className="w-3.5 h-3.5 text-sky-400" />}
                          </div>
                        </button>
                      );
                    })
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Toolbar: Search input + Anti-duplicate Filter Tabs */}
        <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3 bg-slate-950/60 p-2.5 rounded-xl border border-slate-800/80">
          {/* Search box */}
          <div className="relative flex-1 max-w-md">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Tìm theo tên video, ID, subfolder..."
              className="w-full bg-slate-900 border border-slate-700/80 rounded-lg pl-9 pr-8 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-sky-500"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Anti-duplicate Smart Filter Pills */}
          <div className="flex items-center gap-1.5 flex-wrap text-xs">
            <span className="text-slate-400 text-[11px] font-semibold flex items-center gap-1 mr-1">
              <Filter className="w-3.5 h-3.5 text-slate-400" /> Lọc trạng thái:
            </span>
            {[
              { id: 'all', label: 'Tất Cả' },
              { id: 'pending_tiktok', label: '🎵 Chưa Đăng TikTok' },
              { id: 'pending_reels', label: '📘 Chưa Đăng Reels' },
              { id: 'pending_shorts', label: '▶️ Chưa Đăng Shorts' },
              { id: 'pending_all', label: '⏳ Chưa Đăng Kênh Nào' },
              { id: 'fully_published', label: '✨ Đã Đăng Đủ 3 Kênh' },
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setFilterPending(tab.id)}
                className={`px-2.5 py-1 rounded-lg font-medium transition ${
                  filterPending === tab.id
                    ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40 font-bold'
                    : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {/* Multi-Selection Sticky Action Bar */}
        {selectedIds.size > 0 && (
          <div className="bg-sky-950/50 border border-sky-500/40 rounded-xl p-3 flex flex-wrap items-center justify-between gap-3 animate-in fade-in slide-in-from-top-2 duration-200">
            <div className="flex items-center gap-2">
              <CheckSquare className="w-4 h-4 text-sky-400" />
              <span className="text-xs font-bold text-white">
                Đã chọn <span className="text-sky-300 font-extrabold">{selectedIds.size}</span> video
              </span>
              <button
                onClick={() => setSelectedIds(new Set())}
                className="text-[11px] text-slate-400 hover:text-slate-200 underline ml-2"
              >
                Bỏ chọn tất cả
              </button>
            </div>

            <div className="flex items-center gap-2 flex-wrap text-xs">
              <span className="text-[11px] text-slate-400 font-semibold mr-1">Hành động hàng loạt:</span>
              <button
                onClick={() => handleBulkToggle('tiktok', true)}
                disabled={isBulkProcessing}
                className="px-2.5 py-1 bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/40 rounded-lg font-bold transition disabled:opacity-50"
              >
                🎵 Đã Đăng TikTok
              </button>
              <button
                onClick={() => handleBulkToggle('reels', true)}
                disabled={isBulkProcessing}
                className="px-2.5 py-1 bg-blue-500/20 hover:bg-blue-500/30 text-blue-300 border border-blue-500/40 rounded-lg font-bold transition disabled:opacity-50"
              >
                📘 Đã Đăng FB Reels
              </button>
              <button
                onClick={() => handleBulkToggle('shorts', true)}
                disabled={isBulkProcessing}
                className="px-2.5 py-1 bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/40 rounded-lg font-bold transition disabled:opacity-50"
              >
                ▶️ Đã Đăng Shorts
              </button>
              <button
                onClick={() => handleBulkToggle('all', true)}
                disabled={isBulkProcessing}
                className="px-2.5 py-1 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 rounded-lg font-bold transition disabled:opacity-50"
              >
                ✨ Đã Đăng Cả 3 Kênh
              </button>
              <button
                onClick={() => handleBulkToggle('all', false)}
                disabled={isBulkProcessing}
                className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-amber-300 border border-slate-700 rounded-lg font-medium transition flex items-center gap-1 disabled:opacity-50"
              >
                <RotateCcw className="w-3 h-3 text-amber-400" /> Reset Chưa Đăng
              </button>
            </div>
          </div>
        )}

        {/* Master Select All Row */}
        <div className="flex items-center justify-between px-3 py-1.5 bg-slate-950/40 rounded-lg border border-slate-800/50 text-xs text-slate-400">
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={displayedVideos.length > 0 && selectedIds.size === displayedVideos.length}
              onChange={toggleSelectAll}
              className="rounded bg-slate-900 border-slate-700 text-sky-500 focus:ring-0 w-3.5 h-3.5 cursor-pointer"
            />
            <span className="font-semibold text-slate-300">
              Chọn tất cả ({displayedVideos.length} video hiển thị)
            </span>
          </label>

          <span className="text-[11px] text-slate-500">
            Click vào nút nền tảng để đổi trạng thái tức thì
          </span>
        </div>

        {/* Video Matrix List */}
        <div className="flex-1 overflow-y-auto space-y-2.5 pr-1 min-h-[300px]">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-20 text-slate-400">
              <RefreshCw className="w-8 h-8 text-sky-400 animate-spin mb-2" />
              <p className="text-xs">Đang tải danh sách video thành phẩm...</p>
            </div>
          ) : displayedVideos.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center text-slate-400">
              <Video className="w-12 h-12 text-slate-600 mb-3 stroke-1" />
              <p className="font-bold text-slate-300 text-sm">
                {searchQuery || filterPending !== 'all' 
                  ? 'Không có video nào khớp với bộ lọc hiện tại'
                  : 'Chưa có video thành phẩm trong thư mục này'}
              </p>
              <p className="text-xs text-slate-500 mt-1 max-w-sm">
                {searchQuery || filterPending !== 'all'
                  ? 'Thử xóa từ khóa tìm kiếm hoặc chọn bộ lọc trạng thái khác.'
                  : 'Hãy vào tab Studio chọn video và xuất video hoàn chỉnh để bắt đầu phân phối!'}
              </p>
            </div>
          ) : (
            displayedVideos.map(v => {
              const isSelected = selectedIds.has(v.id);
              const cleanTitle = getCleanTitle(v.filename);
              const isFullyPublished = v.platforms.tiktok && v.platforms.reels && v.platforms.shorts;

              return (
                <div
                  key={v.id}
                  className={`p-3 rounded-xl border transition flex flex-col md:flex-row items-start md:items-center justify-between gap-3.5 ${
                    isSelected 
                      ? 'bg-sky-950/20 border-sky-500/50' 
                      : isFullyPublished
                      ? 'bg-slate-950/50 border-slate-800/80 hover:border-slate-700 opacity-90'
                      : 'bg-slate-950/80 border-slate-800 hover:border-slate-700'
                  }`}
                >
                  {/* Left Column: Checkbox, Thumbnail/Play, Video Meta */}
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    {/* Checkbox */}
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleSelectVideo(v.id)}
                      className="rounded bg-slate-900 border-slate-700 text-sky-500 focus:ring-0 w-4 h-4 cursor-pointer shrink-0"
                    />

                    {/* Thumbnail / Play Preview Trigger */}
                    <div
                      onClick={() => setPreviewVideo(v)}
                      className="w-14 h-16 rounded-lg bg-slate-900 shrink-0 border border-slate-800 relative overflow-hidden flex flex-col items-center justify-center cursor-pointer group hover:border-sky-500 transition"
                      title="Bấm để xem trước video"
                    >
                      <Play className="w-5 h-5 text-slate-400 group-hover:text-sky-400 group-hover:scale-110 transition" />
                      <span className="text-[9px] font-mono text-slate-400 group-hover:text-white mt-1">
                        Xem
                      </span>
                      <span className="absolute bottom-0.5 right-0.5 bg-black/80 text-[8px] font-mono px-1 rounded text-white">
                        {v.duration}
                      </span>
                    </div>

                    {/* Metadata & Quick Copy Buttons */}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p 
                          onClick={() => setPreviewVideo(v)}
                          className="text-xs font-bold text-white truncate cursor-pointer hover:text-sky-300 transition"
                          title={v.filename}
                        >
                          {cleanTitle || v.filename}
                        </p>
                        {isFullyPublished && (
                          <span className="px-1.5 py-0.2 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-[10px] font-bold shrink-0">
                            ✓ Đủ 3 Kênh
                          </span>
                        )}
                      </div>

                      <p className="text-[11px] text-slate-400 font-mono mt-0.5 truncate" title={v.path}>
                        📁 <span className="text-sky-300">ready_to_upload/{v.subfolder}/</span> • {v.size_mb} MB • <span className="text-slate-500">{v.process_type}</span>
                      </p>

                      {/* Creator Quick Utilities */}
                      <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                        <button
                          onClick={() => handleCopyText(cleanTitle, 'title')}
                          className="px-2 py-0.5 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded text-[11px] font-medium border border-slate-700 flex items-center gap-1 transition active:scale-95"
                          title="Sao chép tiêu đề sạch (không đuôi .mp4, không ID số)"
                        >
                          <Copy className="w-3 h-3 text-slate-400" />
                          <span>Copy Tiêu Đề</span>
                        </button>

                        <button
                          onClick={() => handleCopyText(v.path, 'path')}
                          className="px-2 py-0.5 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white rounded text-[11px] font-medium border border-slate-700 flex items-center gap-1 transition active:scale-95"
                          title="Sao chép đường dẫn file để paste tải lên"
                        >
                          <Copy className="w-3 h-3 text-slate-400" />
                          <span>Copy Đường Dẫn File</span>
                        </button>

                        <button
                          onClick={() => api.openFolder(v.path.substring(0, v.path.lastIndexOf('\\')) || outputRootDir)}
                          className="px-2 py-0.5 bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white rounded text-[11px] font-medium border border-slate-700 flex items-center gap-1 transition active:scale-95"
                          title="Mở thư mục chứa file trong Windows Explorer"
                        >
                          <ExternalLink className="w-3 h-3" />
                          <span>Mở Thư Mục</span>
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Right Column: 3 Platform Toggle Buttons */}
                  <div className="flex items-center gap-2 shrink-0 self-end md:self-center">
                    {/* TikTok Toggle */}
                    <button
                      onClick={() => handleTogglePlatform(v.id, 'tiktok')}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 active:scale-95 ${
                        v.platforms.tiktok
                          ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm shadow-cyan-500/10'
                          : 'bg-slate-900 text-slate-400 hover:text-white border border-slate-800 hover:border-slate-700'
                      }`}
                      title={v.platforms.tiktok ? 'Đã đăng lên TikTok (bấm để chuyển về Chưa Đăng)' : 'Chưa đăng lên TikTok (bấm để đánh dấu Đã Đăng)'}
                    >
                      <span>🎵 TikTok:</span>
                      <span>{v.platforms.tiktok ? '✓ Đã Đăng' : '⏳ Chưa Đăng'}</span>
                    </button>

                    {/* Facebook Reels Toggle */}
                    <button
                      onClick={() => handleTogglePlatform(v.id, 'reels')}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 active:scale-95 ${
                        v.platforms.reels
                          ? 'bg-blue-500/20 text-blue-300 border border-blue-500/40 shadow-sm shadow-blue-500/10'
                          : 'bg-slate-900 text-slate-400 hover:text-white border border-slate-800 hover:border-slate-700'
                      }`}
                      title={v.platforms.reels ? 'Đã đăng lên FB Reels (bấm để chuyển về Chưa Đăng)' : 'Chưa đăng lên FB Reels (bấm để đánh dấu Đã Đăng)'}
                    >
                      <span>📘 FB Reels:</span>
                      <span>{v.platforms.reels ? '✓ Đã Đăng' : '⏳ Chưa Đăng'}</span>
                    </button>

                    {/* YouTube Shorts Toggle */}
                    <button
                      onClick={() => handleTogglePlatform(v.id, 'shorts')}
                      className={`px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 active:scale-95 ${
                        v.platforms.shorts
                          ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40 shadow-sm shadow-rose-500/10'
                          : 'bg-slate-900 text-slate-400 hover:text-white border border-slate-800 hover:border-slate-700'
                      }`}
                      title={v.platforms.shorts ? 'Đã đăng lên YouTube Shorts (bấm để chuyển về Chưa Đăng)' : 'Chưa đăng lên YouTube Shorts (bấm để đánh dấu Đã Đăng)'}
                    >
                      <span>▶️ Shorts:</span>
                      <span>{v.platforms.shorts ? '✓ Đã Đăng' : '⏳ Chưa Đăng'}</span>
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* 4. Video Preview Player Modal */}
      {previewVideo && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-200">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-4xl w-full overflow-hidden shadow-2xl flex flex-col max-h-[90vh]">
            {/* Modal Header */}
            <div className="p-3.5 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2 min-w-0 pr-2">
                <Play className="w-4 h-4 text-sky-400 shrink-0" />
                <h3 className="font-bold text-sm text-white truncate">
                  {getCleanTitle(previewVideo.filename)}
                </h3>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={handlePrevPreview}
                  disabled={displayedVideos.findIndex(v => v.id === previewVideo.id) <= 0}
                  className="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg border border-slate-700 disabled:opacity-30 transition"
                  title="Video trước"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <button
                  onClick={handleNextPreview}
                  disabled={displayedVideos.findIndex(v => v.id === previewVideo.id) >= displayedVideos.length - 1}
                  className="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg border border-slate-700 disabled:opacity-30 transition"
                  title="Video kế tiếp"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setPreviewVideo(null)}
                  className="p-1.5 bg-slate-800 hover:bg-rose-500/20 text-slate-400 hover:text-rose-300 rounded-lg border border-slate-700 transition"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Modal Player Content */}
            <div className="flex-1 bg-black flex items-center justify-center overflow-hidden p-2">
              <video
                src={api.getVideoStreamUrl(previewVideo.path)}
                controls
                autoPlay
                className="max-h-[60vh] max-w-full rounded-lg shadow-lg"
              />
            </div>

            {/* Modal Footer: Info & Quick Action Toggles */}
            <div className="p-4 bg-slate-950 border-t border-slate-800 flex flex-col md:flex-row items-start md:items-center justify-between gap-3 text-xs">
              <div className="min-w-0 flex-1">
                <p className="text-white font-mono truncate text-[11px]">
                  File: <span className="text-slate-400">{previewVideo.filename}</span>
                </p>
                <div className="flex items-center gap-2 mt-1.5">
                  <button
                    onClick={() => handleCopyText(getCleanTitle(previewVideo.filename), 'title')}
                    className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg border border-slate-700 flex items-center gap-1.5 font-medium transition active:scale-95"
                  >
                    <Copy className="w-3.5 h-3.5 text-slate-400" />
                    Copy Tiêu Đề Sạch
                  </button>
                  <button
                    onClick={() => handleCopyText(previewVideo.path, 'path')}
                    className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg border border-slate-700 flex items-center gap-1.5 font-medium transition active:scale-95"
                  >
                    <Copy className="w-3.5 h-3.5 text-slate-400" />
                    Copy Đường Dẫn File
                  </button>
                </div>
              </div>

              {/* In-Modal Toggle Buttons */}
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => handleTogglePlatform(previewVideo.id, 'tiktok')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 active:scale-95 ${
                    previewVideo.platforms.tiktok
                      ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm shadow-cyan-500/10'
                      : 'bg-slate-900 text-slate-400 hover:text-white border border-slate-800'
                  }`}
                >
                  <span>🎵 TikTok:</span>
                  <span>{previewVideo.platforms.tiktok ? '✓ Đã Đăng' : '⏳ Chưa Đăng'}</span>
                </button>

                <button
                  onClick={() => handleTogglePlatform(previewVideo.id, 'reels')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 active:scale-95 ${
                    previewVideo.platforms.reels
                      ? 'bg-blue-500/20 text-blue-300 border border-blue-500/40 shadow-sm shadow-blue-500/10'
                      : 'bg-slate-900 text-slate-400 hover:text-white border border-slate-800'
                  }`}
                >
                  <span>📘 FB Reels:</span>
                  <span>{previewVideo.platforms.reels ? '✓ Đã Đăng' : '⏳ Chưa Đăng'}</span>
                </button>

                <button
                  onClick={() => handleTogglePlatform(previewVideo.id, 'shorts')}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 active:scale-95 ${
                    previewVideo.platforms.shorts
                      ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40 shadow-sm shadow-rose-500/10'
                      : 'bg-slate-900 text-slate-400 hover:text-white border border-slate-800'
                  }`}
                >
                  <span>▶️ Shorts:</span>
                  <span>{previewVideo.platforms.shorts ? '✓ Đã Đăng' : '⏳ Chưa Đăng'}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    
      {/* 5. MODAL CÀI ĐẶT THƯ MỤC XUẤT THÀNH PHẨM GỐC (Đồng bộ với modal setup nguồn) */}
      {showStorageModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-150">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl p-6 w-full max-w-lg shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <Settings className="w-4 h-4 text-sky-400" /> Cài Đặt Thư Mục Xuất Thành Phẩm Gốc
              </h3>
              <button
                onClick={() => setShowStorageModal(false)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-4 text-xs">
              <div className="space-y-1.5">
                <label className="text-slate-300 font-semibold flex items-center gap-1.5">
                  <Folder className="w-3.5 h-3.5 text-sky-400" /> Đường dẫn thư mục xuất thành phẩm hiện tại:
                </label>
                <div className="font-mono bg-slate-950 p-2.5 rounded-xl border border-slate-800 text-sky-300 select-all break-all text-xs">
                  {outputRootDir || 'Chưa thiết lập'}
                </div>
              </div>

              <div className="flex items-center gap-2 pt-1">
                <button
                  type="button"
                  onClick={async () => {
                    await triggerFolderPicker();
                    setShowStorageModal(false);
                  }}
                  className="flex-1 py-2.5 bg-sky-500/20 hover:bg-sky-500/30 text-sky-300 border border-sky-500/40 rounded-xl font-bold flex items-center justify-center gap-1.5 transition active:scale-95"
                >
                  <Folder className="w-3.5 h-3.5" /> Chọn Thư Mục Khác Trên Máy
                </button>
                {outputRootDir && (
                  <button
                    type="button"
                    onClick={() => api.openFolder(outputRootDir)}
                    className="py-2.5 px-3.5 bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 rounded-xl font-semibold flex items-center gap-1.5 transition"
                    title="Mở thư mục trong Windows Explorer"
                  >
                    <ExternalLink className="w-3.5 h-3.5" /> Mở Explorer
                  </button>
                )}
              </div>

              <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-emerald-300 text-[11px] space-y-1">
                <p className="font-bold flex items-center gap-1">
                  <Check className="w-3.5 h-3.5 text-emerald-400" /> Cơ chế phân phối đa nền tảng:
                </p>
                <p className="text-slate-400 leading-relaxed">
                  Khi render video xong, file thành phẩm sẽ được lưu vào thư mục này theo từng subfolder kênh để quản lý phân phối đa nền tảng (TikTok, FB Reels, YT Shorts) và chống up trùng lặp.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
