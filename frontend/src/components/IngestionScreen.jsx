import React, { useState, useEffect, useRef } from 'react';
import { 
  Folder, FolderPlus, Download, HardDrive, Laptop, Globe, Zap, 
  Search, ExternalLink, RefreshCw, Sparkles, Filter, FileVideo, 
  PlusCircle, Upload, Trash2, Plus, Play, ToggleLeft, ToggleRight, 
  Radio, X, Check, CheckCircle2, Rss, RotateCcw, ChevronLeft, ChevronRight, CheckSquare, Square, Key, Film,
  Settings, Link as LinkIcon, AlertCircle, Edit3, Clock
} from 'lucide-react';
import * as api from '../services/api';

export default function IngestionScreen({ onSelectVideo, showToast }) {
  const [downloadRootDir, setDownloadRootDir] = useState('');
  const [sources, setSources] = useState({ download_subfolders: [], local_folders: [] });
  const [accounts, setAccounts] = useState([]);
  const [activeSourceType, setActiveSourceType] = useState('subfolder');
  const [activeSourceId, setActiveSourceId] = useState('all');
  const [videosList, setVideosList] = useState([]);
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [loading, setLoading] = useState(false);
  const [quickUrl, setQuickUrl] = useState('');
  const [targetAccount, setTargetAccount] = useState('general_inbox');
  const [isDownloadingQuick, setIsDownloadingQuick] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const [scanState, setScanState] = useState({
    active: false,
    accountId: null,
    accountName: '',
    platform: '',
    forceFullScan: false,
    elapsed: 0,
    statusText: '',
    minimized: false,
  });
  const [downloadingVideoIds, setDownloadingVideoIds] = useState(new Set());
  const [selectedAccountIds, setSelectedAccountIds] = useState(new Set());

  // Channel search & filter states
  const [accountSearchQuery, setAccountSearchQuery] = useState('');
  const [accountPlatformFilter, setAccountPlatformFilter] = useState('all');

  // Edit Account Modal states
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingAccount, setEditingAccount] = useState(null);
  const [isSavingEdit, setIsSavingEdit] = useState(false);

  // Compact modal states
  const [showStorageModal, setShowStorageModal] = useState(false);
  const [showQuickDownloadModal, setShowQuickDownloadModal] = useState(false);
  const [showDouyinLoginModal, setShowDouyinLoginModal] = useState(false);
  const [isDouyinLoggedIn, setIsDouyinLoggedIn] = useState(false);
  const [douyinCookieInput, setDouyinCookieInput] = useState('');
  const [isSavingCookie, setIsSavingCookie] = useState(false);
  const [isCheckingDouyinStatus, setIsCheckingDouyinStatus] = useState(false);
  const [isLaunchingEdge, setIsLaunchingEdge] = useState(false);
  const [isUploadingCookieFile, setIsUploadingCookieFile] = useState(false);
  const cookieFileInputRef = useRef(null);

  // Multi-selection & Pagination state
  const [selectedVideoKeys, setSelectedVideoKeys] = useState(new Set());
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(24);
  const [searchQuery, setSearchQuery] = useState('');
  const [isBulkDownloading, setIsBulkDownloading] = useState(false);
  const [bulkDownloadProgress, setBulkDownloadProgress] = useState({ current: 0, total: 0 });

  // Modal thêm kênh cào video
  const [showAddModal, setShowAddModal] = useState(false);
  const [modalPlatform, setModalPlatform] = useState('douyin');
  const [modalUrl, setModalUrl] = useState('');
  const [modalName, setModalName] = useState('');
  const [modalMode, setModalMode] = useState('remix');

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
    const [srcData, accData, dyStatus] = await Promise.all([
      api.getSources(),
      api.getCrawlerAccounts(),
      api.getDouyinStatus().catch(() => null),
    ]);

    if (dyStatus && typeof dyStatus.logged_in === 'boolean') {
      setIsDouyinLoggedIn(dyStatus.logged_in);
    }

    if (accData && Array.isArray(accData)) {
      setAccounts(accData);
    }

    if (srcData) {
      setSources(srcData);
      if (accData && accData.length > 0) {
        const first = accData[0];
        const firstFolder = `${first.platform || 'douyin'}_${first.account_id}`;
        if (activeSourceId === 'all') {
          setActiveSourceType('subfolder');
          setActiveSourceId(firstFolder);
          setTargetAccount(firstFolder);
          loadVideos('subfolder', firstFolder);
        } else {
          loadVideos(activeSourceType, activeSourceId);
        }
      } else if (srcData.local_folders?.length > 0) {
        const first = srcData.local_folders[0];
        if (activeSourceId === 'all') {
          setActiveSourceType('local');
          setActiveSourceId(first.id);
          loadVideos('local', first.id);
        } else {
          loadVideos(activeSourceType, activeSourceId);
        }
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

  // 6. Xóa / Gỡ bỏ thư mục nguồn (Local folders hoặc Subfolder downloads)
  const handleRemoveFolder = async (path, folderType, folderName) => {
    const isLocal = folderType === 'local';
    const confirmMsg = isLocal
      ? `Bạn có chắc chắn muốn gỡ bỏ thư mục máy tính "${folderName}" khỏi danh sách theo dõi của Studio?\n(Các file video trên máy bạn vẫn được giữ nguyên an toàn)`
      : `Bạn có chắc muốn xóa thư mục tải về "${folderName}" không?\n(Toàn bộ file trong thư mục này trên ổ đĩa sẽ bị xóa)`;

    if (!window.confirm(confirmMsg)) return;

    showToast(`Đang xử lý gỡ bỏ thư mục ${folderName}...`, 'info');
    const res = await api.removeFolder(path, folderType);
    if (res && res.success) {
      showToast(`✓ Đã gỡ bỏ thư mục <b>${folderName}</b> thành công!`, 'success');
      await loadSourcesData();
      if (activeSourceId === path || activeSourceId === folderName) {
        handleFilterFolder('all', 'all');
      }
    } else {
      showToast(`❌ Lỗi khi gỡ bỏ: ${res?.detail || 'Không thể thực hiện'}`, 'error');
    }
  };

  // 7. Thêm tài khoản Crawler mới
  const handleAddAccountSubmit = async (e) => {
    if (e) e.preventDefault();
    if (!modalUrl.trim()) {
      alert('Vui lòng nhập link tài khoản / kênh!');
      return;
    }
    showToast('Đang thêm kênh vào hệ thống theo dõi...', 'info');
    const res = await api.addCrawlerAccount({
      platform: modalPlatform,
      url: modalUrl.trim(),
      name: modalName.trim() || undefined,
      mode: modalMode,
      auto_process: true,
    });
    if (res && res.success) {
      showToast(`✓ Đã thêm kênh [${modalPlatform.toUpperCase()}] thành công!`, 'success');
      setShowAddModal(false);
      setModalUrl('');
      setModalName('');
      await loadSourcesData();
    } else {
      showToast(`❌ Lỗi: ${res?.detail || 'Không thể thêm tài khoản'}`, 'error');
    }
  };

  // 8. Bật / Tắt trạng thái quét của tài khoản
  const handleToggleAccount = async (acc) => {
    const nextState = !Boolean(acc.is_active);
    const res = await api.toggleCrawlerAccount(acc.account_id, nextState);
    if (res && res.success) {
      setAccounts(prev => prev.map(a => a.account_id === acc.account_id ? { ...a, is_active: nextState ? 1 : 0 } : a));
      showToast(`${nextState ? '✓ Đã BẬT' : 'Đã TẮT'} tự động quét kênh <b>${acc.account_name}</b>`, nextState ? 'success' : 'info');
    }
  };

  // Helper định dạng thời gian tương đối
  const formatRelativeTime = (isoStr) => {
    if (!isoStr) return 'Chưa quét';
    try {
      const d = new Date(isoStr);
      if (isNaN(d.getTime())) return 'Chưa quét';
      const diffSec = Math.floor((Date.now() - d.getTime()) / 1000);
      if (diffSec < 60) return 'Vừa xong';
      const diffMin = Math.floor(diffSec / 60);
      if (diffMin < 60) return `${diffMin}p trước`;
      const diffHour = Math.floor(diffMin / 60);
      if (diffHour < 24) return `${diffHour}h trước`;
      const diffDay = Math.floor(diffHour / 24);
      if (diffDay < 30) return `${diffDay} ngày trước`;
      return d.toLocaleDateString('vi-VN');
    } catch {
      return 'Chưa quét';
    }
  };

  // Danh sách kênh lọc theo tìm kiếm và nền tảng
  const filteredAccounts = accounts.filter(acc => {
    if (accountPlatformFilter !== 'all' && (acc.platform || '').toLowerCase() !== accountPlatformFilter.toLowerCase()) {
      return false;
    }
    if (accountSearchQuery.trim()) {
      const q = accountSearchQuery.toLowerCase();
      const name = (acc.account_name || '').toLowerCase();
      const id = (acc.account_id || '').toLowerCase();
      if (!name.includes(q) && !id.includes(q)) return false;
    }
    return true;
  });

  // 9a. Mở modal chỉnh sửa tài khoản
  const handleOpenEditAccount = (acc, e) => {
    if (e) e.stopPropagation();
    setEditingAccount({
      account_id: acc.account_id,
      platform: acc.platform || 'douyin',
      account_name: acc.account_name || '',
      account_url: acc.account_url || '',
      process_mode: acc.process_mode || 'remix',
      auto_process: Boolean(acc.auto_process),
    });
    setShowEditModal(true);
  };

  // 9a2. Lưu chỉnh sửa tài khoản
  const handleEditAccountSubmit = async (e) => {
    if (e) e.preventDefault();
    if (!editingAccount) return;
    setIsSavingEdit(true);
    showToast(`Đang cập nhật kênh <b>${editingAccount.account_name}</b>...`, 'info');
    try {
      const res = await api.updateCrawlerAccount(editingAccount.account_id, {
        account_name: editingAccount.account_name.trim(),
        account_url: editingAccount.account_url.trim(),
        process_mode: editingAccount.process_mode,
        auto_process: editingAccount.auto_process,
      });
      if (res && res.success) {
        showToast(`✓ Đã cập nhật kênh <b>${editingAccount.account_name || editingAccount.account_id}</b> thành công!`, 'success');
        setAccounts(prev => prev.map(a => a.account_id === editingAccount.account_id ? {
          ...a,
          account_name: editingAccount.account_name.trim(),
          account_url: editingAccount.account_url.trim(),
          process_mode: editingAccount.process_mode,
          auto_process: editingAccount.auto_process ? 1 : 0,
        } : a));
        setShowEditModal(false);
      } else {
        showToast(`❌ Lỗi cập nhật: ${res?.detail || 'Không thể cập nhật'}`, 'error');
      }
    } catch (err) {
      showToast(`❌ Lỗi: ${err.message}`, 'error');
    } finally {
      setIsSavingEdit(false);
    }
  };

  // 9. Xóa tài khoản Crawler
  const handleDeleteAccount = async (acc) => {
    if (!window.confirm(`Bạn có chắc muốn xóa kênh [${acc.platform.toUpperCase()}] "${acc.account_name}" khỏi danh sách theo dõi?`)) return;
    const res = await api.deleteCrawlerAccount(acc.account_id);
    if (res && res.success) {
      showToast(`✓ Đã xóa kênh <b>${acc.account_name}</b> khỏi danh sách theo dõi`, 'success');
      setAccounts(prev => prev.filter(a => a.account_id !== acc.account_id));
      await loadSourcesData();
    } else {
      showToast(`❌ Không thể xóa kênh: ${res?.detail || 'Lỗi server'}`, 'error');
    }
  };

  // 9b. Tích chọn/bỏ chọn 1 tài khoản
  const handleToggleSelectAccount = (accountId) => {
    setSelectedAccountIds(prev => {
      const next = new Set(prev);
      if (next.has(accountId)) next.delete(accountId);
      else next.add(accountId);
      return next;
    });
  };

  // 9c. Chọn tất cả / Bỏ chọn tất cả tài khoản
  const handleSelectAllAccounts = () => {
    const visibleIds = filteredAccounts.map(a => a.account_id);
    const allVisibleSelected = visibleIds.length > 0 && visibleIds.every(id => selectedAccountIds.has(id));
    if (allVisibleSelected) {
      setSelectedAccountIds(prev => {
        const next = new Set(prev);
        visibleIds.forEach(id => next.delete(id));
        return next;
      });
    } else {
      setSelectedAccountIds(prev => {
        const next = new Set(prev);
        visibleIds.forEach(id => next.add(id));
        return next;
      });
    }
  };

  // 9d. Xóa hàng loạt các kênh đã chọn
  const handleBulkDeleteAccounts = async () => {
    if (selectedAccountIds.size === 0) return;
    const count = selectedAccountIds.size;
    const confirmMsg = `Bạn có chắc muốn xóa ${count} kênh đã chọn khỏi danh sách theo dõi của Studio?\n\n(Lưu ý: Các video và file đã tải về máy vẫn an toàn, không bị xóa)`;
    if (!window.confirm(confirmMsg)) return;

    showToast(`Đang xóa ${count} kênh...`, 'info');
    let deletedCount = 0;
    for (const accId of selectedAccountIds) {
      try {
        const res = await api.deleteCrawlerAccount(accId);
        if (res && res.success) deletedCount++;
      } catch (err) {
        console.warn(`Lỗi xóa kênh ${accId}:`, err);
      }
    }
    showToast(`✓ Đã xóa thành công ${deletedCount}/${count} kênh!`, 'success');
    setSelectedAccountIds(new Set());
    await loadSourcesData();
    handleFilterFolder('all', 'all');
  };

  // 9e. Quét hàng loạt (Quét mới hoặc Quét lại toàn bộ)
  const handleBulkScanAccounts = async (forceFullScan = false) => {
    if (selectedAccountIds.size === 0) {
      if (forceFullScan) {
        if (!window.confirm("Bạn có chắc muốn Reset mốc quét và quét lại TOÀN BỘ video từ đầu cho tất cả các kênh?")) return;
      }
      await handleScanAccounts(null, forceFullScan);
      return;
    }

    const selectedList = Array.from(selectedAccountIds);
    if (selectedList.length === 1) {
      if (forceFullScan) {
        const acc = accounts.find(a => a.account_id === selectedList[0]);
        const confirmMsg = `Bạn có chắc muốn Reset mốc quét cho kênh "${acc?.account_name || selectedList[0]}"?\n\nHệ thống sẽ quét lại toàn bộ video từ trước đến nay của kênh này.`;
        if (!window.confirm(confirmMsg)) return;
      }
      await handleScanAccounts(selectedList[0], forceFullScan);
    } else {
      if (forceFullScan) {
        const confirmMsg = `Bạn có chắc muốn Reset mốc quét và quét lại TOÀN BỘ video từ trước đến nay cho ${selectedList.length} kênh đã chọn?`;
        if (!window.confirm(confirmMsg)) return;
      }
      for (let i = 0; i < selectedList.length; i++) {
        const accId = selectedList[i];
        await handleScanAccounts(accId, forceFullScan);
      }
    }
  };

  // 10. Quét video từ tài khoản (Tất cả hoặc 1 kênh)
  const handleScanAccounts = async (accountId = null, forceFullScan = false) => {
    setIsScanning(true);
    const targetAcc = accountId ? accounts.find(a => a.account_id === accountId) : null;
    const targetName = targetAcc ? targetAcc.account_name : (accountId ? accountId : 'Tất cả các kênh theo dõi');
    const targetPlatform = targetAcc ? targetAcc.platform : 'douyin';
    const modeName = forceFullScan ? 'toàn bộ video từ trước đến nay' : 'video mới nhất';

    setScanState({
      active: true,
      accountId,
      accountName: targetName,
      platform: targetPlatform,
      forceFullScan,
      elapsed: 0,
      statusText: 'Đang khởi động trình duyệt Headless & nạp Cookie...',
      minimized: false,
    });

    const timer = setInterval(() => {
      setScanState(prev => {
        if (!prev.active) return prev;
        const nextElapsed = prev.elapsed + 1;
        let text = prev.statusText;
        if (nextElapsed <= 3) {
          text = 'Đang khởi động trình duyệt Headless & nạp Cookie Douyin...';
        } else if (nextElapsed <= 7) {
          text = 'Đang truy cập trang kênh Douyin & kiểm tra chứng thực bảo mật...';
        } else if (nextElapsed <= 16) {
          text = 'Đang cuộn trang tự nhiên và trích xuất danh sách video (/aweme/post)...';
        } else if (nextElapsed <= 28) {
          text = 'Đang trích xuất link phát HD không logo & tải thumbnail vào bộ đệm cache...';
        } else {
          text = 'Đang xử lý đồng bộ dữ liệu vào cơ sở dữ liệu Studio...';
        }
        return {
          ...prev,
          elapsed: nextElapsed,
          statusText: text,
        };
      });
    }, 1000);

    showToast(
      accountId
        ? `Đang quét ${modeName} từ kênh "${targetName}"...`
        : `Đang quét ${modeName} tất cả kênh đang bật theo dõi...`,
      'info'
    );
    try {
      const res = await api.scanCrawlerAccounts(accountId, null, forceFullScan);
      if (res && res.success) {
        showToast(`🎉 ${res.message}`, 'success');
        if (res.warning) {
          showToast(`⚠️ ${res.warning}`, 'warning');
        }
        const srcData = await api.getSources();
        const accData = await api.getCrawlerAccounts();
        if (accData && Array.isArray(accData)) setAccounts(accData);
        if (srcData) setSources(srcData);

        if (accountId) {
          const matchingSub = srcData?.download_subfolders?.find(s => s.id.includes(accountId));
          const targetSubId = matchingSub ? matchingSub.id : `${targetPlatform}_${accountId}`;
          setActiveSourceType('subfolder');
          setActiveSourceId(targetSubId);
          await loadVideos('subfolder', targetSubId);
        } else {
          await loadVideos(activeSourceType, activeSourceId);
        }
      } else {
        showToast(`❌ Quét thất bại: ${res?.detail || 'Lỗi kết nối mạng/WAF hoặc không có video'}`, 'error');
      }
    } catch (err) {
      showToast(`❌ Lỗi: ${err.message}`, 'error');
    } finally {
      clearInterval(timer);
      setIsScanning(false);
      setScanState(prev => ({ ...prev, active: false }));
    }
  };

  // 10c. Reset mốc quét của kênh (quét lại toàn bộ từ đầu)
  const handleResetAccountScan = async (acc) => {
    const confirmMsg = `Bạn có chắc muốn Reset mốc quét cho kênh [${acc.platform.toUpperCase()}] "${acc.account_name}"?\n\n• Hệ thống sẽ xóa mốc cũ và quét lại toàn bộ video từ trước đến nay của kênh này.\n• Bắt đầu quét ngay bây giờ?`;
    if (!window.confirm(confirmMsg)) return;
    await handleScanAccounts(acc.account_id, true);
  };

  // 10d. Xóa một video hoặc thumbnail khỏi danh sách
  const handleDeleteVideoItem = async (video) => {
    const isDiscovered = video.download_status === 'discovered';
    const confirmMsg = isDiscovered
      ? `Bạn có chắc muốn xóa thumbnail và gỡ video "${video.filename}" khỏi danh sách chờ tải?`
      : `Bạn có chắc muốn xóa video "${video.filename}" khỏi danh sách?`;

    if (!window.confirm(confirmMsg)) return;

    showToast(`Đang xóa ${isDiscovered ? 'thumbnail' : 'video'}...`, 'info');
    try {
      const res = await api.deleteVideoItem(video.id, video.path, !isDiscovered);
      if (res && res.success) {
        showToast(`✓ Đã xóa thành công!`, 'success');
        setVideosList(prev => prev.filter(v => (video.id ? v.id !== video.id : v.path !== video.path)));
        await loadSourcesData();
      } else {
        showToast(`❌ Không thể xóa: ${res?.detail || 'Lỗi server'}`, 'error');
      }
    } catch (err) {
      showToast(`❌ Lỗi xóa: ${err.message}`, 'error');
    }
  };

  // 10e. Xóa tất cả thumbnail đang chờ tải
  const handleClearAllThumbnails = async () => {
    const count = videosList.filter(v => v.download_status === 'discovered').length;
    if (count === 0) {
      showToast('Không có thumbnail video chờ tải nào để xóa!', 'info');
      return;
    }

    const targetAccountPart = activeSourceType === 'subfolder' && activeSourceId !== 'all' ? activeSourceId : null;
    const confirmMsg = targetAccountPart
      ? `Bạn có chắc muốn xóa TẤT CẢ ${count} thumbnail video đang chờ tải của thư mục này?`
      : `Bạn có chắc muốn xóa TẤT CẢ ${count} thumbnail video đang chờ tải trong toàn bộ hệ thống?`;

    if (!window.confirm(confirmMsg)) return;

    showToast(`Đang dọn dẹp ${count} thumbnail...`, 'info');
    try {
      const accId = targetAccountPart && targetAccountPart.includes('_') ? targetAccountPart.split('_', 1)[1] : targetAccountPart;
      const res = await api.clearThumbnails(accId);
      if (res && res.success) {
        showToast(`✓ ${res.message}`, 'success');
        setVideosList(prev => prev.filter(v => v.download_status !== 'discovered'));
        await loadSourcesData();
      } else {
        showToast(`❌ Lỗi khi dọn dẹp: ${res?.detail || 'Lỗi'}`, 'error');
      }
    } catch (err) {
      showToast(`❌ Lỗi: ${err.message}`, 'error');
    }
  };

  // 10b. Tải video vật lý (.mp4) theo quyết định của người dùng
  const handleDownloadSingleVideo = async (video) => {
    if (!video.id) {
      showToast('❌ Không tìm thấy ID video trong cơ sở dữ liệu!', 'error');
      return;
    }
    setDownloadingVideoIds(prev => new Set(prev).add(video.id));
    showToast(`Đang tải file video vật lý về máy: <b>${video.filename}</b>...`, 'info');
    try {
      const res = await api.downloadDiscoveredVideo(video.id);
      if (res && res.download_status === 'downloaded') {
        showToast(`✓ Đã tải xong video: <b>${res.filename}</b>!`, 'success');
        setVideosList(prev => prev.map(v => (v.id === video.id ? res : v)));
        await loadSourcesData();
      } else {
        showToast(`❌ Lỗi tải video: ${res?.detail || 'Không xác định'}`, 'error');
      }
    } catch (err) {
      showToast(`❌ Lỗi khi tải video: ${err.message}`, 'error');
    } finally {
      setDownloadingVideoIds(prev => {
        const next = new Set(prev);
        next.delete(video.id);
        return next;
      });
    }
  };

  // 11. Tải nhanh video từ link
  const handleQuickDownload = async () => {
    if (!quickUrl.trim()) {
      alert('Vui lòng dán link video Douyin / TikTok / YouTube / FB vào ô nhập!');
      return;
    }

    let acc = targetAccount;
    if (acc === '_new_subfolder_') {
      const name = prompt('Nhập tên subfolder tài khoản mới (ví dụ: ken_channel):', 'ken_channel');
      if (!name) return;
      acc = name.trim();
    }

    setIsDownloadingQuick(true);
    showToast(`Đang tải video thực tế từ link vào: <code class="text-sky-300">downloads/${acc}/</code> (Vui lòng chờ)...`, 'info');
    try {
      const res = await api.quickDownload(quickUrl.trim(), acc);
      if (res && res.success) {
        showToast(`✓ ${res.message}`, 'success');
        setQuickUrl('');
        if (res.video) {
          setVideosList(prev => [res.video, ...prev]);
        }
        await loadSourcesData();
      } else {
        showToast(`❌ Không thể tải video: ${res?.detail || 'Lỗi mạng hoặc liên kết'}`, 'error');
      }
    } catch (err) {
      showToast(`❌ Lỗi tải: ${err.message}`, 'error');
    } finally {
      setIsDownloadingQuick(false);
    }
  };

  // Helper định danh video duy nhất
  const getVideoKey = (v) => String(v.id || v.path || v.platform_video_id || v.filename);

  // Chọn / Bỏ chọn từng video
  const toggleSelectVideo = (key) => {
    setSelectedVideoKeys(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  // Chọn / Bỏ chọn tất cả video trên trang hiện tại
  const handleSelectAllCurrentPage = () => {
    const pageKeys = paginatedVideos.map(getVideoKey);
    const allSelected = pageKeys.length > 0 && pageKeys.every(k => selectedVideoKeys.has(k));
    setSelectedVideoKeys(prev => {
      const next = new Set(prev);
      if (allSelected) {
        pageKeys.forEach(k => next.delete(k));
      } else {
        pageKeys.forEach(k => next.add(k));
      }
      return next;
    });
  };

  // Chọn tất cả video trong bộ lọc
  const handleSelectAllFiltered = () => {
    const allKeys = filteredVideos.map(getVideoKey);
    const allSelected = allKeys.length > 0 && allKeys.every(k => selectedVideoKeys.has(k));
    setSelectedVideoKeys(prev => {
      const next = new Set(prev);
      if (allSelected) {
        allKeys.forEach(k => next.delete(k));
      } else {
        allKeys.forEach(k => next.add(k));
      }
      return next;
    });
  };

  // Bỏ chọn tất cả
  const handleClearSelection = () => {
    setSelectedVideoKeys(new Set());
  };

  // Action dùng chung 1: Tải hàng loạt video đã chọn
  const handleBulkDownloadSelected = async () => {
    const selectedItems = videosList.filter(v => selectedVideoKeys.has(getVideoKey(v)));
    const discoveredItems = selectedItems.filter(v => v.download_status === 'discovered' && v.id);
    if (discoveredItems.length === 0) {
      showToast('Không có video nào ở trạng thái chờ tải trong các mục đã chọn!', 'warning');
      return;
    }
    if (!window.confirm(`Bạn có chắc muốn tải về máy ${discoveredItems.length} video đã chọn?`)) return;

    setIsBulkDownloading(true);
    setBulkDownloadProgress({ current: 0, total: discoveredItems.length });
    showToast(`Bắt đầu tải hàng loạt ${discoveredItems.length} video...`, 'info');

    let successCount = 0;
    for (let i = 0; i < discoveredItems.length; i++) {
      const v = discoveredItems[i];
      setBulkDownloadProgress({ current: i + 1, total: discoveredItems.length });
      try {
        const res = await api.downloadDiscoveredVideo(v.id);
        if (res && res.download_status === 'downloaded') {
          successCount++;
          setVideosList(prev => prev.map(item => item.id === v.id ? res : item));
        }
      } catch (err) {
        console.error('Lỗi tải video:', v.filename, err);
      }
    }
    setIsBulkDownloading(false);
    showToast(`✓ Đã hoàn thành tải xong ${successCount}/${discoveredItems.length} video!`, 'success');
    await loadSourcesData();
  };

  // Action dùng chung 2: Xóa hàng loạt các mục đã chọn
  const handleBulkDeleteSelected = async () => {
    const selectedItems = videosList.filter(v => selectedVideoKeys.has(getVideoKey(v)));
    if (selectedItems.length === 0) return;
    const confirmMsg = `Bạn có chắc muốn xóa ${selectedItems.length} mục đã chọn khỏi danh sách?`;
    if (!window.confirm(confirmMsg)) return;

    showToast(`Đang xóa ${selectedItems.length} mục đã chọn...`, 'info');
    let delCount = 0;
    for (const v of selectedItems) {
      const isDiscovered = v.download_status === 'discovered';
      try {
        await api.deleteVideoItem(v.id, v.path, !isDiscovered);
        delCount++;
      } catch (e) {
        console.error(e);
      }
    }
    const deletedKeys = new Set(selectedItems.map(getVideoKey));
    setVideosList(prev => prev.filter(v => !deletedKeys.has(getVideoKey(v))));
    setSelectedVideoKeys(new Set());
    showToast(`✓ Đã xóa thành công ${delCount} mục!`, 'success');
    await loadSourcesData();
  };

  // Action dùng chung 3: Nạp video vào Studio để dịch & biên tập
  const handleBulkSendToStudio = () => {
    const selectedItems = videosList.filter(v => selectedVideoKeys.has(getVideoKey(v)));
    const downloadedItems = selectedItems.filter(v => v.download_status !== 'discovered');
    if (downloadedItems.length === 0) {
      showToast('Vui lòng chọn ít nhất 1 video đã tải để chuyển vào Studio!', 'warning');
      return;
    }
    const target = downloadedItems[0];
    const isTargetProcessed = Boolean(target.is_processed || target.status === 'ready' || target.status === 'completed');
    onSelectVideo(target, 'translate');
    if (isTargetProcessed) {
      showToast(`ℹ️ <b>${target.filename}</b> đã có bản xuất thành phẩm. Đang mở lại trong Studio...`, 'info');
    } else {
      showToast(`✓ Đã nạp video <b>${target.filename}</b> vào Studio!`, 'success');
    }
  };

  // Mở modal kết nối tài khoản Douyin (Không tự ý spam polling)
  const handleDouyinLogin = () => {
    setShowDouyinLoginModal(true);
  };

  // Nạp file Cookie JSON từ extension (Cookie-Editor, EditThisCookie, J2Team...)
  const handleCookieFileSelect = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setIsUploadingCookieFile(true);
    try {
      const res = await api.uploadDouyinCookieFile(file);
      if (res && res.success) {
        setIsDouyinLoggedIn(Boolean(res.logged_in));
        showToast(res.message, 'success');
        if (res.logged_in) {
          setShowDouyinLoginModal(false);
          setDouyinCookieInput('');
        } else {
          showToast('⚠️ File cookie chưa có sessionid đăng nhập. Hãy đảm bảo bạn đã đăng nhập nick trên Douyin trước khi Export!', 'warning');
        }
      } else {
        showToast('❌ ' + (res?.message || 'Không thể lưu cookie từ file'), 'error');
      }
    } catch (err) {
      showToast('❌ Lỗi nạp file: ' + err.message, 'error');
    } finally {
      setIsUploadingCookieFile(false);
      if (cookieFileInputRef.current) cookieFileInputRef.current.value = '';
    }
  };

  // Lưu Cookie / JSON Douyin do người dùng dán vào (JSON hoặc text)
  const handleSaveDouyinCookie = async () => {
    const raw = douyinCookieInput.trim();
    if (!raw) {
      showToast('Vui lòng dán nội dung JSON hoặc cookie vào ô nhập!', 'warning');
      return;
    }
    setIsSavingCookie(true);
    try {
      const res = await api.saveDouyinCookie(raw);
      if (res && res.success) {
        setIsDouyinLoggedIn(Boolean(res.logged_in));
        showToast(res.message, 'success');
        if (res.logged_in) {
          setShowDouyinLoginModal(false);
          setDouyinCookieInput('');
        } else {
          showToast('⚠️ Đã lưu cookie nhưng chưa thấy sessionid đăng nhập. Hãy đảm bảo bạn đã đăng nhập tài khoản trên Douyin!', 'warning');
        }
      } else {
        showToast('❌ Lỗi: ' + (res?.detail || res?.message || 'Không thể lưu cookie'), 'error');
      }
    } catch (err) {
      showToast('❌ Lỗi: ' + err.message, 'error');
    } finally {
      setIsSavingCookie(false);
    }
  };

  // Mở trình duyệt Edge thật trên Windows để người dùng quét QR
  const handleLaunchEdgeForLogin = async () => {
    setIsLaunchingEdge(true);
    showToast('Đang mở cửa sổ trình duyệt Edge trên màn hình máy tính...', 'info');
    try {
      const res = await api.openDouyinLogin();
      if (res && res.success) {
        showToast(res.message, 'success');
      } else {
        showToast('❌ Không thể mở Edge: ' + (res?.detail || res?.message || 'Lỗi'), 'error');
      }
    } catch (err) {
      showToast('❌ Lỗi: ' + err.message, 'error');
    } finally {
      setIsLaunchingEdge(false);
    }
  };

  // Kiểm tra trạng thái Douyin theo yêu cầu (Chỉ gọi 1 lần khi người dùng bấm nút)
  const handleCheckDouyinStatus = async () => {
    setIsCheckingDouyinStatus(true);
    try {
      const res = await api.getDouyinStatus();
      if (res && res.logged_in) {
        setIsDouyinLoggedIn(true);
        showToast('🎉 ' + res.message, 'success');
      } else {
        setIsDouyinLoggedIn(false);
        showToast('Chưa ghi nhận đăng nhập Douyin. Hãy quét mã QR trên Edge hoặc dán Cookie!', 'info');
      }
    } catch (err) {
      showToast('❌ Lỗi kiểm tra: ' + err.message, 'error');
    } finally {
      setIsCheckingDouyinStatus(false);
    }
  };

  // Xác nhận đã quét mã QR trên Edge: Đóng cửa sổ Edge và lưu phiên duyệt
  const handleConfirmDouyinLogin = async () => {
    setIsCheckingDouyinStatus(true);
    showToast('Đang kiểm tra và lưu phiên đăng nhập Douyin...', 'info');
    try {
      const res = await api.confirmDouyinLogin();
      if (res && res.logged_in) {
        setIsDouyinLoggedIn(true);
        showToast(res.message, 'success');
        setShowDouyinLoginModal(false);
      } else {
        setIsDouyinLoggedIn(false);
        showToast(res?.message || 'Chưa ghi nhận đăng nhập Douyin. Hãy quét mã QR trên Edge hoặc dán Cookie!', 'warning');
      }
    } catch (err) {
      showToast('❌ Lỗi xác nhận: ' + err.message, 'error');
    } finally {
      setIsCheckingDouyinStatus(false);
    }
  };

  // Render các nút số trang
  const renderPaginationButtons = (current, total, setPage) => {
    const pages = [];
    const maxButtons = 7;
    if (total <= maxButtons) {
      for (let i = 1; i <= total; i++) pages.push(i);
    } else {
      pages.push(1);
      if (current > 3) pages.push('...');
      const start = Math.max(2, current - 1);
      const end = Math.min(total - 1, current + 1);
      for (let i = start; i <= end; i++) {
        if (!pages.includes(i)) pages.push(i);
      }
      if (current < total - 2) pages.push('...');
      if (!pages.includes(total)) pages.push(total);
    }

    return pages.map((p, idx) => {
      if (p === '...') {
        return <span key={`dots-${idx}`} className="px-2 text-slate-500 text-xs select-none">...</span>;
      }
      const isAct = p === current;
      return (
        <button
          key={p}
          onClick={() => setPage(p)}
          className={`w-7 h-7 rounded-lg text-xs font-bold transition ${
            isAct
              ? 'bg-sky-500 text-slate-950 shadow-md font-extrabold'
              : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
          }`}
        >
          {p}
        </button>
      );
    });
  };

  const countDiscovered = videosList.filter(v => v.download_status === 'discovered').length;
  const countDownloaded = videosList.filter(v => v.download_status === 'downloaded').length;
  const countProcessed = videosList.filter(v => v.is_processed || v.status === 'ready' || v.status === 'completed').length;
  const countUnprocessed = videosList.filter(v => !v.is_processed && v.status !== 'ready' && v.status !== 'completed' && v.download_status === 'downloaded').length;
  const countTranslate = videosList.filter(v => v.has_sub).length;
  const countRemix = videosList.filter(v => v.suggest_remix).length;

  const filteredVideos = videosList.filter(v => {
    if (categoryFilter === 'discovered' && v.download_status !== 'discovered') return false;
    if (categoryFilter === 'downloaded' && v.download_status !== 'downloaded') return false;
    if (categoryFilter === 'processed' && !v.is_processed && v.status !== 'ready' && v.status !== 'completed') return false;
    if (categoryFilter === 'unprocessed' && (v.is_processed || v.status === 'ready' || v.status === 'completed' || v.download_status === 'discovered')) return false;
    if (categoryFilter === 'translate' && !v.has_sub) return false;
    if (categoryFilter === 'remix' && !v.suggest_remix) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const fn = (v.filename || '').toLowerCase();
      const sub = (v.subfolder || '').toLowerCase();
      if (!fn.includes(q) && !sub.includes(q)) return false;
    }
    return true;
  });

  const totalPages = Math.max(1, Math.ceil(filteredVideos.length / pageSize));
  const safeCurrentPage = Math.min(currentPage, totalPages);
  const paginatedVideos = filteredVideos.slice(
    (safeCurrentPage - 1) * pageSize,
    safeCurrentPage * pageSize
  );

  const selectedInFiltered = filteredVideos.filter(v => selectedVideoKeys.has(getVideoKey(v)));
  const selectedDiscoveredCount = selectedInFiltered.filter(v => v.download_status === 'discovered').length;
  const selectedDownloadedCount = selectedInFiltered.filter(v => v.download_status !== 'discovered').length;

  const getPlatformBadge = (platform) => {
    switch ((platform || '').toLowerCase()) {
      case 'douyin':
        return <span className="text-[9px] px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30 font-bold uppercase">Douyin</span>;
      case 'tiktok':
        return <span className="text-[9px] px-1.5 py-0.5 rounded bg-sky-500/20 text-sky-300 border border-sky-500/30 font-bold uppercase">TikTok</span>;
      case 'bilibili':
        return <span className="text-[9px] px-1.5 py-0.5 rounded bg-pink-500/20 text-pink-300 border border-pink-500/30 font-bold uppercase">Bilibili</span>;
      case 'facebook':
        return <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30 font-bold uppercase">Facebook</span>;
      case 'instagram':
        return <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 font-bold uppercase">Instagram</span>;
      default:
        return <span className="text-[9px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 font-bold uppercase">{platform || 'Video'}</span>;
    }
  };

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

      {/* 1. Minimal Top Header Bar */}
      <div className="flex items-center justify-between pb-1 flex-wrap gap-2">
        <div className="flex items-center gap-3">
          <h1 className="text-sm font-bold text-white flex items-center gap-2">
            <FolderPlus className="w-4 h-4 text-sky-400" /> Nguồn Dữ Liệu & Kho Video
          </h1>
          <span className="text-[11px] font-mono text-slate-400 bg-slate-900 border border-slate-800 px-2 py-0.5 rounded-lg">
            {sources.total_videos || videosList.length} video
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Nút Cài đặt Thư mục tải về gốc (Button setting nhỏ theo yêu cầu người dùng) */}
          <button
            onClick={() => setShowStorageModal(true)}
            className="px-2.5 py-1.5 bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white rounded-xl border border-slate-800 flex items-center gap-2 text-xs font-medium transition active:scale-95 shadow-sm"
            title={`Cài đặt thư mục tải về: ${downloadRootDir}`}
          >
            <Folder className="w-3.5 h-3.5 text-sky-400" />
            <span className="hidden sm:inline text-slate-400">Thư mục tải:</span>
            <span className="font-mono text-sky-300 max-w-[150px] truncate font-semibold">
              {downloadRootDir ? (downloadRootDir.split('\\').pop() || downloadRootDir) : 'downloads'}
            </span>
            <Settings className="w-3.5 h-3.5 text-slate-400 hover:text-sky-300" />
          </button>

          {/* Nút Tải theo Link (nếu thỉnh thoảng cần tải lẻ 1 link) */}
          <button
            onClick={() => setShowQuickDownloadModal(true)}
            className="px-2.5 py-1.5 bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white rounded-xl border border-slate-800 flex items-center gap-1.5 text-xs font-medium transition active:scale-95 shadow-sm"
            title="Dán link video đơn lẻ (Douyin, TikTok, YouTube...) để tải về"
          >
            <LinkIcon className="w-3.5 h-3.5 text-emerald-400" />
            <span className="hidden sm:inline">Tải Theo Link</span>
          </button>
        </div>
      </div>

      {/* 3. Ingestion Split View: Sources Tree + Video Repository */}
      <div className="grid grid-cols-12 gap-4 flex-1 min-h-[460px]">
        {/* Left Sidebar (4 cols): Quản lý kênh crawl và thư mục máy */}
        <div className="col-span-4 bg-slate-900 border border-slate-800 rounded-2xl p-3.5 flex flex-col">
          <div className="flex items-center justify-between pb-2.5 border-b border-slate-800">
            <span className="font-bold text-xs text-white uppercase tracking-wider flex items-center gap-1.5">
              <FolderPlus className="w-4 h-4 text-sky-400" /> Nguồn Dữ Liệu
            </span>
            <button
              onClick={() => handleFilterFolder('all', 'all')}
              className="text-[10px] text-sky-400 hover:underline font-semibold"
            >
              Hiện tất cả video
            </button>
          </div>

          <div className="flex-1 overflow-y-auto space-y-3 mt-2.5 pr-1">
            {/* 3.1. Kênh Cào Video Tự Động (Crawler Accounts) */}
            <div className="space-y-2">
              <div className="flex items-center justify-between px-1 pb-1">
                <div className="text-[11px] text-sky-400 uppercase font-bold tracking-wider flex items-center gap-1.5">
                  <Rss className="w-3.5 h-3.5" /> Kênh Crawl ({accounts.length})
                </div>
                <div className="flex items-center gap-1.5">
                  {/* Douyin Login status */}
                  <button
                    type="button"
                    onClick={handleDouyinLogin}
                    className={`px-2 py-0.5 rounded text-[10px] font-bold flex items-center gap-1 transition active:scale-95 ${
                      isDouyinLoggedIn
                        ? 'bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 border border-emerald-500/30'
                        : 'bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 border border-rose-500/30'
                    }`}
                    title={
                      isDouyinLoggedIn
                        ? 'Douyin đã đăng nhập thành công. Bấm nếu muốn kiểm tra hoặc nhập cookie mới'
                        : 'BẮT BUỘC: Đăng nhập Douyin một lần duy nhất để cào toàn bộ video!'
                    }
                  >
                    {isDouyinLoggedIn ? (
                      <>
                        <Check className="w-3 h-3 text-emerald-400" /> Đã Login
                      </>
                    ) : (
                      <>
                        <Key className="w-3 h-3 text-rose-400" /> Chưa Login
                      </>
                    )}
                  </button>

                  {/* Thêm Kênh */}
                  <button
                    type="button"
                    onClick={() => setShowAddModal(true)}
                    className="px-2 py-0.5 bg-sky-500/20 hover:bg-sky-500/30 text-sky-300 border border-sky-500/30 rounded text-[10px] font-bold flex items-center gap-1 transition active:scale-95"
                    title="Thêm tài khoản Douyin/TikTok/Bilibili mới để theo dõi"
                  >
                    <Plus className="w-3 h-3" /> Thêm Kênh
                  </button>
                </div>
              </div>

              {/* Tầng 2: Contextual Bulk Action Bar */}
              {accounts.length > 0 && (
                <div className={`p-1.5 rounded-xl border flex items-center justify-between gap-1.5 transition ${
                  selectedAccountIds.size > 0 
                    ? 'bg-sky-950/70 border-sky-500/50 shadow-sm' 
                    : 'bg-slate-950/60 border-slate-800'
                }`}>
                  {/* Select All & Counter */}
                  <div className="flex items-center gap-1.5 shrink-0 pl-0.5">
                    <button
                      type="button"
                      onClick={handleSelectAllAccounts}
                      className="text-slate-400 hover:text-white transition p-0.5 flex items-center gap-1"
                      title={filteredAccounts.length > 0 && filteredAccounts.every(a => selectedAccountIds.has(a.account_id)) ? "Bỏ chọn tất cả" : "Chọn tất cả kênh đang hiển thị"}
                    >
                      {filteredAccounts.length > 0 && filteredAccounts.every(a => selectedAccountIds.has(a.account_id)) ? (
                        <CheckSquare className="w-3.5 h-3.5 text-sky-400" />
                      ) : (
                        <Square className="w-3.5 h-3.5 text-slate-500" />
                      )}
                    </button>
                    <span className="text-[10px] font-mono text-slate-300">
                      {selectedAccountIds.size > 0 ? (
                        <span className="font-bold text-sky-400">{selectedAccountIds.size}/{filteredAccounts.length}</span>
                      ) : (
                        <span className="text-slate-500">Tất cả ({filteredAccounts.length})</span>
                      )}
                    </span>
                  </div>

                  {/* Action buttons */}
                  <div className="flex items-center gap-1 shrink-0">
                    {/* Quét mới */}
                    <button
                      type="button"
                      onClick={() => handleBulkScanAccounts(false)}
                      disabled={isScanning || accounts.length === 0}
                      className="px-2 py-0.5 bg-emerald-500/20 hover:bg-emerald-500/30 disabled:bg-slate-800 text-emerald-300 disabled:text-slate-500 border border-emerald-500/30 rounded text-[10px] font-bold flex items-center gap-1 transition active:scale-95"
                      title={selectedAccountIds.size > 0 ? `Quét video mới cho ${selectedAccountIds.size} kênh đã chọn` : "Quét video mới cho tất cả các kênh"}
                    >
                      {isScanning && !scanState.forceFullScan ? (
                        <RefreshCw className="w-3 h-3 animate-spin text-emerald-400" />
                      ) : (
                        <Play className="w-3 h-3" />
                      )}
                      {selectedAccountIds.size > 0 ? `Quét (${selectedAccountIds.size})` : 'Quét Mới'}
                    </button>

                    {/* Quét lại (Reset full) */}
                    <button
                      type="button"
                      onClick={() => handleBulkScanAccounts(true)}
                      disabled={isScanning || accounts.length === 0}
                      className="px-2 py-0.5 bg-amber-500/20 hover:bg-amber-500/30 disabled:bg-slate-800 text-amber-300 disabled:text-slate-500 border border-amber-500/30 rounded text-[10px] font-bold flex items-center gap-1 transition active:scale-95"
                      title={selectedAccountIds.size > 0 ? `Reset mốc & Quét lại toàn bộ cho ${selectedAccountIds.size} kênh đã chọn` : "Reset mốc quét và quét lại TOÀN BỘ video từ trước đến nay của tất cả kênh"}
                    >
                      {isScanning && scanState.forceFullScan ? (
                        <RefreshCw className="w-3 h-3 animate-spin text-amber-400" />
                      ) : (
                        <RotateCcw className="w-3 h-3" />
                      )}
                      {selectedAccountIds.size > 0 ? `Quét Lại (${selectedAccountIds.size})` : 'Quét Lại'}
                    </button>

                    {/* Xóa các kênh đã chọn */}
                    {selectedAccountIds.size > 0 && (
                      <button
                        type="button"
                        onClick={handleBulkDeleteAccounts}
                        disabled={isScanning}
                        className="px-2 py-0.5 bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/30 rounded text-[10px] font-bold flex items-center gap-1 transition active:scale-95 animate-in fade-in"
                        title={`Xóa ${selectedAccountIds.size} kênh đã chọn khỏi danh sách theo dõi`}
                      >
                        <Trash2 className="w-3 h-3" /> Xóa ({selectedAccountIds.size})
                      </button>
                    )}
                  </div>
                </div>
              )}

              {/* Tầng 3: Tìm kiếm & Lọc kênh theo nền tảng */}
              {accounts.length > 0 && (
                <div className="space-y-1.5 pt-0.5">
                  {/* Search Input */}
                  <div className="relative">
                    <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
                    <input
                      type="text"
                      value={accountSearchQuery}
                      onChange={(e) => setAccountSearchQuery(e.target.value)}
                      placeholder="Tìm kênh theo tên hoặc ID..."
                      className="w-full bg-slate-950/80 border border-slate-800 rounded-xl pl-8 pr-7 py-1 text-[11px] text-slate-200 placeholder-slate-500 outline-none focus:border-sky-500/60 transition"
                    />
                    {accountSearchQuery && (
                      <button
                        type="button"
                        onClick={() => setAccountSearchQuery('')}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 p-0.5"
                        title="Xóa tìm kiếm"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    )}
                  </div>

                  {/* Platform Filter Pills */}
                  <div className="flex items-center gap-1 overflow-x-auto pb-0.5 scrollbar-thin">
                    {['all', 'douyin', 'tiktok', 'bilibili'].filter(p => p === 'all' || accounts.some(a => (a.platform || '').toLowerCase() === p)).map(plat => {
                      const count = plat === 'all' ? accounts.length : accounts.filter(a => (a.platform || '').toLowerCase() === plat).length;
                      const isAct = accountPlatformFilter === plat;
                      return (
                        <button
                          key={plat}
                          type="button"
                          onClick={() => setAccountPlatformFilter(plat)}
                          className={`px-2 py-0.5 rounded-lg text-[10px] font-semibold whitespace-nowrap transition flex items-center gap-1 ${
                            isAct
                              ? 'bg-sky-500 text-slate-950 font-bold shadow-sm'
                              : 'bg-slate-950 border border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200'
                          }`}
                        >
                          <span>{plat === 'all' ? 'Tất cả' : plat.toUpperCase()}</span>
                          <span className={`text-[9px] px-1 rounded-full ${isAct ? 'bg-slate-950/20 text-slate-950 font-bold' : 'bg-slate-900 text-slate-500'}`}>{count}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              {accounts.length === 0 ? (
                <div className="p-3 bg-slate-950/60 border border-dashed border-slate-800 rounded-xl text-center space-y-1.5">
                  <p className="text-[11px] text-slate-400">Chưa có kênh nào trong danh sách theo dõi.</p>
                  <button
                    onClick={() => setShowAddModal(true)}
                    className="text-xs text-sky-400 hover:underline font-semibold"
                  >
                    ➕ Thêm kênh Douyin / TikTok ngay
                  </button>
                </div>
              ) : filteredAccounts.length === 0 ? (
                <div className="p-3 bg-slate-950/60 border border-dashed border-slate-800 rounded-xl text-center space-y-1.5">
                  <p className="text-[11px] text-slate-400">Không tìm thấy kênh nào khớp bộ lọc.</p>
                  <button
                    onClick={() => { setAccountSearchQuery(''); setAccountPlatformFilter('all'); }}
                    className="text-xs text-sky-400 hover:underline font-semibold"
                  >
                    Xóa bộ lọc tìm kiếm
                  </button>
                </div>
              ) : (
                <div className="space-y-1.5 max-h-[380px] overflow-y-auto pr-1">
                  {filteredAccounts.map(acc => {
                    const isSelected = activeSourceType === 'subfolder' && activeSourceId.includes(acc.account_id);
                    const isChecked = selectedAccountIds.has(acc.account_id);
                    const isCurrentScanning = scanState.active && scanState.accountId === acc.account_id;
                    const matchingSub = sources.download_subfolders?.find(s => s.id.includes(acc.account_id));
                    const fallbackVidCount = matchingSub?.video_count ?? 0;
                    const discoveredCount = acc.total_discovered ?? 0;
                    const downloadedCount = acc.total_downloaded ?? fallbackVidCount;
                    const channelUrl = acc.account_url || (
                      (acc.platform || '').toLowerCase() === 'douyin' ? `https://www.douyin.com/user/${acc.account_id}` :
                      (acc.platform || '').toLowerCase() === 'tiktok' ? `https://www.tiktok.com/@${acc.account_id.replace(/^@/, '')}` :
                      (acc.platform || '').toLowerCase() === 'bilibili' ? `https://space.bilibili.com/${acc.account_id}` :
                      ''
                    );

                    return (
                      <div
                        key={acc.id || acc.account_id}
                        onClick={() => {
                          if (matchingSub) {
                            handleFilterFolder('subfolder', matchingSub.id);
                          } else {
                            handleFilterFolder('subfolder', `${acc.platform || 'douyin'}_${acc.account_id}`);
                          }
                        }}
                        className={`p-2 rounded-xl cursor-pointer transition flex items-center justify-between group ${
                          isSelected ? 'bg-sky-500/15 border-2 border-sky-400 shadow-sm' : 'bg-slate-950/80 border border-slate-800 hover:border-slate-700'
                        }`}
                      >
                        <div className="flex items-center gap-2 min-w-0 flex-1">
                          {/* Checkbox chọn */}
                          <div
                            onClick={(e) => {
                              e.stopPropagation();
                              handleToggleSelectAccount(acc.account_id);
                            }}
                            className="p-0.5 cursor-pointer text-slate-400 hover:text-white transition shrink-0"
                            title={isChecked ? "Bỏ chọn kênh này" : "Chọn kênh này"}
                          >
                            {isChecked ? (
                              <CheckSquare className="w-4 h-4 text-sky-400" />
                            ) : (
                              <Square className="w-4 h-4 text-slate-600 group-hover:text-slate-400" />
                            )}
                          </div>

                          <div className="shrink-0">{getPlatformBadge(acc.platform)}</div>

                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-1.5 min-w-0">
                              <p className="text-xs font-bold text-white truncate">{acc.account_name}</p>
                              {channelUrl && (
                                <a
                                  href={channelUrl}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  onClick={(e) => e.stopPropagation()}
                                  className="text-slate-500 hover:text-sky-400 transition p-0.5 rounded hover:bg-slate-800 shrink-0"
                                  title={`Mở kênh chính chủ: ${channelUrl}`}
                                >
                                  <ExternalLink className="w-3 h-3" />
                                </a>
                              )}
                              {isCurrentScanning && (
                                <span className="inline-flex items-center gap-1 px-1.5 py-0.2 text-[9px] font-bold bg-sky-500/20 text-sky-300 border border-sky-500/30 rounded-full animate-pulse shrink-0">
                                  <RefreshCw className="w-2.5 h-2.5 animate-spin" /> {scanState.elapsed}s
                                </span>
                              )}
                            </div>
                            <p className="text-[10px] text-slate-400 font-mono truncate mt-0.5" title={`ID: ${acc.account_id}`}>
                              ID: {acc.account_id}
                            </p>
                            <div className="flex items-center gap-2 mt-0.5 text-[9px] text-slate-500">
                              <span className="flex items-center gap-1 font-mono" title={`Quét gần nhất: ${acc.last_checked_at || 'Chưa có'}`}>
                                <Clock className="w-2.5 h-2.5 text-slate-600" /> {formatRelativeTime(acc.last_checked_at)}
                              </span>
                              {acc.process_mode && (
                                <span className="px-1 rounded bg-slate-900 border border-slate-800 text-slate-400 uppercase text-[8px]">
                                  {acc.process_mode}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>

                        {/* Right side: Statistical Badges & Action Buttons */}
                        <div className="shrink-0 flex items-center gap-1 pl-1">
                          {isCurrentScanning ? (
                            <div className="flex items-center gap-1 text-[10px] font-mono text-sky-400 bg-sky-950/80 px-2 py-0.5 rounded border border-sky-800/80 animate-pulse">
                              <RefreshCw className="w-3 h-3 animate-spin" />
                              <span>{scanState.elapsed}s</span>
                            </div>
                          ) : (
                            <div className="flex items-center gap-1">
                              {/* Badge Chờ Tải */}
                              {discoveredCount > 0 && (
                                <span
                                  className="text-[9px] font-bold font-mono px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30"
                                  title={`${discoveredCount} video chờ tải`}
                                >
                                  📥 {discoveredCount}
                                </span>
                              )}
                              {/* Badge Đã Tải */}
                              {downloadedCount > 0 ? (
                                <span
                                  className="text-[9px] font-bold font-mono px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                                  title={`${downloadedCount} video đã tải về máy`}
                                >
                                  💾 {downloadedCount}
                                </span>
                              ) : (discoveredCount === 0 && (
                                <span className="text-[10px] text-slate-500 font-mono bg-slate-900/60 px-1.5 py-0.5 rounded border border-slate-800">
                                  0 vid
                                </span>
                              ))}
                            </div>
                          )}

                          {/* Nút Mở Kênh Chính Chủ */}
                          {channelUrl && (
                            <a
                              href={channelUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="p-1 text-slate-500 hover:text-sky-300 hover:bg-sky-500/20 rounded-lg transition"
                              title={`Mở trang cá nhân / kênh chính chủ trong tab mới: ${channelUrl}`}
                            >
                              <ExternalLink className="w-3.5 h-3.5" />
                            </a>
                          )}

                          {/* Nút Sửa Kênh */}
                          <button
                            type="button"
                            onClick={(e) => handleOpenEditAccount(acc, e)}
                            className="p-1 text-slate-500 hover:text-sky-300 hover:bg-sky-500/20 rounded-lg transition"
                            title="Chỉnh sửa thông tin kênh"
                          >
                            <Edit3 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* 3.2. Thư Mục Máy Tính (Chỉ hiển thị khi người dùng đã thêm thư mục trên máy) */}
            {sources.local_folders?.length > 0 && (
              <div className="space-y-1.5 pt-2 border-t border-slate-800">
                <div className="flex items-center justify-between px-1">
                  <div className="text-[11px] text-amber-400 uppercase font-bold tracking-wider flex items-center gap-1.5">
                    <Laptop className="w-3.5 h-3.5" /> Thư Mục Máy Tính ({sources.local_folders.length}):
                  </div>
                </div>
                <div className="space-y-1.5 max-h-[220px] overflow-y-auto pr-1">
                  {sources.local_folders.map(loc => {
                    const isAct = activeSourceType === 'local' && activeSourceId === loc.id;
                    return (
                      <div
                        key={loc.id}
                        onClick={() => handleFilterFolder('local', loc.id)}
                        className={`p-2 rounded-xl cursor-pointer transition flex items-center justify-between group ${
                          isAct ? 'bg-amber-500/10 border-2 border-amber-400' : 'bg-slate-950/80 border border-slate-800 hover:border-slate-700'
                        }`}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <Laptop className="w-4 h-4 text-amber-400 shrink-0" />
                          <div className="min-w-0">
                            <p className="text-xs font-semibold text-amber-200 truncate">{loc.name}</p>
                            <p className="text-[10px] text-slate-400 font-mono truncate">{loc.video_count} video • {loc.path}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); api.openFolder(loc.path); }}
                            className="text-[10px] text-slate-400 hover:text-white px-1.5 py-0.5 bg-slate-800 rounded border border-slate-700 shrink-0"
                            title="Mở thư mục trong Windows Explorer"
                          >
                            📂 Mở
                          </button>
                          <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); handleRemoveFolder(loc.path, 'local', loc.name); }}
                            className="text-[10px] text-rose-400 hover:text-white hover:bg-rose-500/40 p-1 bg-slate-800 rounded border border-rose-500/30 shrink-0 transition"
                            title="Gỡ bỏ thư mục này khỏi danh sách Studio"
                          >
                            <Trash2 className="w-3 h-3" />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          <div className="space-y-1.5 mt-3 pt-2 border-t border-slate-800">
            <div className="flex items-center gap-2">
              <button
                onClick={handlePickLocalFolder}
                className="flex-1 py-1.5 bg-slate-800 hover:bg-slate-700 text-amber-300 rounded-xl text-xs font-bold border border-amber-500/30 flex items-center justify-center gap-1.5 transition active:scale-95"
                title="Mở Windows Explorer để duyệt và thêm thư mục video"
              >
                <Laptop className="w-3.5 h-3.5" /> + Thư Mục Máy
              </button>
              <button
                onClick={handlePickLocalFiles}
                className="py-1.5 px-3 bg-slate-800 hover:bg-slate-700 text-emerald-300 rounded-xl text-xs font-bold border border-emerald-500/30 flex items-center justify-center gap-1.5 transition active:scale-95"
                title="Mở Windows Explorer chọn trực tiếp 1 hoặc nhiều file video"
              >
                <FileVideo className="w-3.5 h-3.5" /> + File
              </button>
            </div>

            <button
              onClick={handleManualPathPrompt}
              className="w-full py-1 bg-slate-950 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded-xl text-[11px] font-medium border border-slate-800 flex items-center justify-center gap-1.5 transition"
              title="Dán đường dẫn thư mục có sẵn trên ổ đĩa"
            >
              📋 Dán Đường Dẫn Thư Mục
            </button>
          </div>
        </div>

        {/* Right Video Cards Repository (8 cols) - THUMBNAIL GRID & BULK ACTIONS */}
        <div className="col-span-8 bg-slate-900 border border-slate-800 rounded-2xl p-4 flex flex-col min-h-[560px]">
          {/* Scanning Live Notification Bar */}
          {scanState.active && (
            <div className="mb-3 p-3 bg-sky-950/60 border border-sky-500/40 rounded-xl flex items-center justify-between gap-3 shadow-lg">
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-8 h-8 rounded-lg bg-sky-500/20 text-sky-400 flex items-center justify-center shrink-0">
                  <RefreshCw className="w-4 h-4 animate-spin" />
                </div>
                <div className="text-xs min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-bold text-sky-300">Đang cào dữ liệu từ kênh:</span>
                    <span className="text-white font-semibold truncate">{scanState.accountName}</span>
                    <span className="text-[10px] px-1.5 py-0.5 bg-sky-500/20 text-sky-300 rounded border border-sky-500/30">
                      {scanState.forceFullScan ? 'Toàn bộ từ đầu' : 'Video mới'}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 truncate mt-0.5 flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping shrink-0" />
                    {scanState.statusText}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="font-mono text-xs font-bold text-sky-400 bg-sky-950 px-2 py-1 rounded-lg border border-sky-800">
                  ⏱️ {Math.floor(scanState.elapsed / 60)}:{(scanState.elapsed % 60).toString().padStart(2, '0')}s
                </span>
                {scanState.minimized && (
                  <button
                    onClick={() => setScanState(prev => ({ ...prev, minimized: false }))}
                    className="text-[11px] text-sky-300 hover:text-white px-2 py-1 bg-sky-500/20 hover:bg-sky-500/30 rounded border border-sky-500/30 font-medium"
                  >
                    Xem chi tiết
                  </button>
                )}
              </div>
            </div>
          )}

          {/* 1. Header & Filter Tabs */}
          <div className="flex items-center justify-between pb-3 border-b border-slate-800 flex-wrap gap-2">
            <div>
              <span className="font-bold text-xs text-white uppercase tracking-wider">
                {activeSourceId === 'all'
                  ? 'Tất cả video'
                  : (accounts.find(a => activeSourceId.includes(a.account_id))?.account_name
                      || (activeSourceType === 'local' ? activeSourceId : `downloads/${activeSourceId}/`))} ({filteredVideos.length} video)
              </span>
            </div>

            {/* Filter tags */}
            <div className="flex items-center gap-1.5 flex-wrap">
              <button
                onClick={() => { setCategoryFilter('all'); setCurrentPage(1); }}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition ${
                  categoryFilter === 'all'
                    ? 'bg-sky-500/20 text-sky-400 border border-sky-500/30 font-bold'
                    : 'bg-slate-800 text-slate-400 hover:text-white'
                }`}
              >
                Tất cả ({videosList.length})
              </button>
              {countDiscovered > 0 && (
                <button
                  onClick={() => { setCategoryFilter('discovered'); setCurrentPage(1); }}
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium transition ${
                    categoryFilter === 'discovered'
                      ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30 font-bold'
                      : 'bg-slate-800 text-amber-400 hover:text-amber-200'
                  }`}
                >
                  📥 Chờ Tải ({countDiscovered})
                </button>
              )}
              {countDownloaded > 0 && (
                <button
                  onClick={() => { setCategoryFilter('downloaded'); setCurrentPage(1); }}
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium transition ${
                    categoryFilter === 'downloaded'
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-bold'
                      : 'bg-slate-800 text-slate-400 hover:text-white'
                  }`}
                >
                  ✅ Đã Tải ({countDownloaded})
                </button>
              )}
              {countUnprocessed > 0 && (
                <button
                  onClick={() => { setCategoryFilter('unprocessed'); setCurrentPage(1); }}
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium transition flex items-center gap-1 ${
                    categoryFilter === 'unprocessed'
                      ? 'bg-teal-600 text-white font-bold shadow-md shadow-teal-500/20'
                      : 'bg-teal-500/10 text-teal-300 border border-teal-500/30 hover:bg-teal-500/20'
                  }`}
                  title="Chỉ hiển thị các video đã tải về máy nhưng chưa xử lý"
                >
                  ⏳ Chưa Xử Lý ({countUnprocessed})
                </button>
              )}
              {countProcessed > 0 && (
                <button
                  onClick={() => { setCategoryFilter('processed'); setCurrentPage(1); }}
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium transition flex items-center gap-1 ${
                    categoryFilter === 'processed'
                      ? 'bg-violet-600 text-white font-bold shadow-md shadow-violet-500/20'
                      : 'bg-violet-500/10 text-violet-300 border border-violet-500/30 hover:bg-violet-500/20'
                  }`}
                  title="Chỉ hiển thị các video đã được xử lý / xuất thành phẩm"
                >
                  <Sparkles className="w-3 h-3 text-violet-400" />
                  ⭐ Đã Xử Lý ({countProcessed})
                </button>
              )}
              <button
                onClick={() => { setCategoryFilter('translate'); setCurrentPage(1); }}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition ${
                  categoryFilter === 'translate'
                    ? 'bg-sky-500/20 text-sky-400 border border-sky-500/30 font-bold'
                    : 'bg-slate-800 text-slate-400 hover:text-white'
                }`}
              >
                🌐 Cần Dịch Sub ({countTranslate})
              </button>
              <button
                onClick={() => { setCategoryFilter('remix'); setCurrentPage(1); }}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition ${
                  categoryFilter === 'remix'
                    ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30 font-bold'
                    : 'bg-slate-800 text-slate-400 hover:text-white'
                }`}
              >
                ⚡ Gợi Ý Remix ({countRemix})
              </button>
            </div>
          </div>

          {/* 2. SHARED ACTION BAR & SELECTION TOOLBAR */}
          <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-2.5 my-3 flex items-center justify-between flex-wrap gap-2.5">
            <div className="flex items-center gap-2 flex-wrap">
              <button
                onClick={handleSelectAllCurrentPage}
                className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition active:scale-95 border border-slate-700"
                title="Chọn hoặc bỏ chọn tất cả video trên trang hiện tại"
              >
                {paginatedVideos.length > 0 && paginatedVideos.every(v => selectedVideoKeys.has(getVideoKey(v))) ? (
                  <CheckSquare className="w-3.5 h-3.5 text-sky-400" />
                ) : (
                  <Square className="w-3.5 h-3.5 text-slate-400" />
                )}
                Chọn Trang Này
              </button>

              {filteredVideos.length > paginatedVideos.length && (
                <button
                  onClick={handleSelectAllFiltered}
                  className="px-2.5 py-1 bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded-lg text-xs font-medium transition"
                >
                  Chọn toàn bộ ({filteredVideos.length})
                </button>
              )}

              {selectedVideoKeys.size > 0 && (
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-sky-400 bg-sky-500/10 border border-sky-500/20 px-2 py-0.5 rounded-md">
                    Đã chọn {selectedVideoKeys.size} video
                  </span>
                  <button
                    onClick={handleClearSelection}
                    className="text-xs text-slate-400 hover:text-rose-400 transition"
                  >
                    Bỏ chọn
                  </button>
                </div>
              )}
            </div>

            {/* Bulk Action Buttons (Dùng chung cho các video đã chọn) */}
            <div className="flex items-center gap-2 flex-wrap ml-auto">
              {selectedVideoKeys.size > 0 ? (
                <>
                  {selectedDiscoveredCount > 0 && (
                    <button
                      onClick={handleBulkDownloadSelected}
                      disabled={isBulkDownloading}
                      className="px-3.5 py-1.5 bg-gradient-to-r from-sky-500 to-blue-600 hover:from-sky-400 hover:to-blue-500 text-white font-bold text-xs rounded-xl shadow-lg transition active:scale-95 flex items-center gap-1.5 disabled:opacity-50"
                      title="Tải video vật lý .mp4 về máy cho các mục đã chọn"
                    >
                      {isBulkDownloading ? (
                        <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Download className="w-3.5 h-3.5" />
                      )}
                      {isBulkDownloading
                        ? `Đang tải (${bulkDownloadProgress.current}/${bulkDownloadProgress.total})...`
                        : `Tải ${selectedDiscoveredCount} Video Đã Chọn`}
                    </button>
                  )}

                  {selectedDownloadedCount > 0 && (
                    <button
                      onClick={handleBulkSendToStudio}
                      className="px-3 py-1.5 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/30 font-bold text-xs rounded-xl transition active:scale-95 flex items-center gap-1.5"
                      title="Nạp video đã tải vào Studio để dịch và biên tập"
                    >
                      <Globe className="w-3.5 h-3.5" /> Nạp Vào Studio
                    </button>
                  )}

                  <button
                    onClick={handleBulkDeleteSelected}
                    className="px-3 py-1.5 bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/30 font-bold text-xs rounded-xl transition active:scale-95 flex items-center gap-1.5"
                    title="Xóa các mục đã chọn"
                  >
                    <Trash2 className="w-3.5 h-3.5" /> Xóa ({selectedVideoKeys.size})
                  </button>
                </>
              ) : (
                <>
                  {/* Search input khi không có selection */}
                  <div className="relative">
                    <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
                    <input
                      type="text"
                      placeholder="Tìm tiêu đề video..."
                      value={searchQuery}
                      onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(1); }}
                      className="pl-8 pr-3 py-1 bg-slate-900 border border-slate-800 rounded-lg text-xs text-white placeholder-slate-500 focus:outline-none focus:border-sky-500 w-44 transition"
                    />
                    {searchQuery && (
                      <button
                        onClick={() => { setSearchQuery(''); setCurrentPage(1); }}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    )}
                  </div>

                  {countDiscovered > 0 && (
                    <button
                      onClick={handleClearAllThumbnails}
                      className="px-2.5 py-1 rounded-lg text-xs font-semibold text-rose-300 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 flex items-center gap-1 transition active:scale-95"
                      title="Xóa tất cả thumbnail video chờ tải đang hiển thị"
                    >
                      <Trash2 className="w-3 h-3" /> Dọn Thumbnail ({countDiscovered})
                    </button>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Bulk Download Progress Bar */}
          {isBulkDownloading && (
            <div className="mb-3 p-2.5 bg-sky-950/60 border border-sky-500/30 rounded-xl space-y-1.5">
              <div className="flex items-center justify-between text-xs text-sky-300 font-semibold">
                <span className="flex items-center gap-1.5">
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Đang tải hàng loạt video về máy...
                </span>
                <span>{bulkDownloadProgress.current} / {bulkDownloadProgress.total}</span>
              </div>
              <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                <div
                  className="bg-sky-500 h-full transition-all duration-300"
                  style={{
                    width: `${bulkDownloadProgress.total > 0 ? (bulkDownloadProgress.current / bulkDownloadProgress.total) * 100 : 0}%`,
                  }}
                />
              </div>
            </div>
          )}

          {/* 3. THUMBNAIL GRID REPOSITORY */}
          <div className="flex-1 overflow-y-auto pr-1">
            {loading ? (
              <div className="text-center py-16 text-slate-500 text-xs flex items-center justify-center gap-2">
                <RefreshCw className="w-4 h-4 animate-spin text-sky-400" /> Đang nạp danh sách video...
              </div>
            ) : filteredVideos.length === 0 ? (
              <div className="text-center py-16 text-slate-500 text-xs space-y-3">
                <p>Không tìm thấy video nào phù hợp</p>
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
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3 pt-1 pb-4">
                {paginatedVideos.map(v => {
                  const vKey = getVideoKey(v);
                  const isSelected = selectedVideoKeys.has(vKey);
                  const isDiscovered = v.download_status === 'discovered';
                  const isDownloadingThis = downloadingVideoIds.has(v.id);
                  const isProcessed = Boolean(v.is_processed || v.status === 'ready' || v.status === 'completed');
                  const thumbSrc = v.thumbnail_url
                    ? (v.thumbnail_url.startsWith('http')
                        ? v.thumbnail_url
                        : `/api/fs/file?path=${encodeURIComponent(v.thumbnail_url)}`)
                    : null;

                  return (
                    <div
                      key={vKey}
                      onClick={() => toggleSelectVideo(vKey)}
                      onDoubleClick={() => {
                        if (!isDiscovered) {
                          onSelectVideo(v, 'translate');
                          if (isProcessed) {
                            showToast(`ℹ️ <b>${v.filename}</b> đã có bản xuất thành phẩm. Đang mở lại trong Studio...`, 'info');
                          } else {
                            showToast(`✓ Đã nạp video <b>${v.filename}</b> vào Studio!`, 'success');
                          }
                        }
                      }}
                      className={`group relative rounded-xl overflow-hidden border cursor-pointer transition-all duration-200 flex flex-col select-none ${
                        isSelected
                          ? 'bg-sky-950/70 border-sky-400 ring-2 ring-sky-500 shadow-lg shadow-sky-500/20'
                          : isProcessed
                            ? 'bg-gradient-to-b from-slate-950/90 to-violet-950/25 border-violet-500/50 hover:border-violet-400 shadow-md shadow-violet-950/20 ring-1 ring-violet-500/20'
                            : 'bg-slate-950/80 border-slate-800 hover:border-slate-600 hover:shadow-md'
                      }`}
                    >
                      {/* Thumbnail Container (Portrait Card Aspect 9:14) */}
                      <div className="relative aspect-[9/14] bg-slate-900 overflow-hidden">
                        {thumbSrc ? (
                          <img
                            src={thumbSrc}
                            alt={v.filename}
                            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                            loading="lazy"
                            onError={(e) => { e.currentTarget.style.display = 'none'; }}
                          />
                        ) : (
                          <div className="w-full h-full flex flex-col items-center justify-center text-slate-600 gap-1">
                            <Film className="w-8 h-8 opacity-40" />
                            <span className="text-[10px]">{v.suggest_remix ? 'Remix' : 'Video'}</span>
                          </div>
                        )}

                        {/* Top-Left Selection Checkbox */}
                        <div
                          onClick={(e) => { e.stopPropagation(); toggleSelectVideo(vKey); }}
                          className={`absolute top-2 left-2 z-10 w-5 h-5 rounded-md flex items-center justify-center transition-all ${
                            isSelected
                              ? 'bg-sky-500 text-slate-950 shadow-md ring-2 ring-white/70'
                              : 'bg-slate-950/70 border border-slate-600 text-transparent hover:border-sky-400 group-hover:bg-slate-900/90'
                          }`}
                        >
                          <Check className={`w-3.5 h-3.5 stroke-[3] ${isSelected ? 'block text-slate-950' : 'hidden group-hover:block text-slate-400'}`} />
                        </div>

                        {/* Top-Right Status Badge */}
                        <div className="absolute top-2 right-2 z-10 flex items-center gap-1">
                          {v.is_pinned > 0 && (
                            <span className="text-[9px] font-bold bg-rose-600 text-white px-1.5 py-0.5 rounded shadow backdrop-blur-sm">
                              📌 Ghim
                            </span>
                          )}
                          {isProcessed ? (
                            <span className="text-[9px] font-bold bg-violet-600 text-white px-2 py-0.5 rounded shadow-lg ring-1 ring-violet-300/40 flex items-center gap-1 backdrop-blur-sm">
                              <CheckCircle2 className="w-3 h-3 stroke-[2.5]" /> Đã xử lý
                            </span>
                          ) : isDiscovered ? (
                            <span className="text-[9px] font-bold bg-amber-500/90 text-slate-950 px-1.5 py-0.5 rounded shadow backdrop-blur-sm">
                              Chờ tải
                            </span>
                          ) : (
                            <span className="text-[9px] font-bold bg-emerald-500/90 text-slate-950 px-1.5 py-0.5 rounded shadow backdrop-blur-sm">
                              ✓ Đã tải
                            </span>
                          )}
                        </div>

                        {/* Duration Chip (Bottom Right) */}
                        <div className="absolute bottom-1.5 right-1.5 z-10">
                          <span className="bg-black/80 backdrop-blur-sm text-[10px] font-mono font-medium px-1.5 py-0.5 rounded text-slate-200 shadow">
                            {v.duration_str || '00:15'}
                          </span>
                        </div>

                        {/* Platform indicator (Bottom Left) */}
                        {v.platform && (
                          <div className="absolute bottom-1.5 left-1.5 z-10">
                            <span className="text-[8px] uppercase font-bold bg-slate-950/80 px-1 py-0.5 rounded text-slate-300 shadow">
                              {v.platform}
                            </span>
                          </div>
                        )}

                        {/* Spinner Overlay when downloading this specific video */}
                        {isDownloadingThis && (
                          <div className="absolute inset-0 bg-black/70 flex flex-col items-center justify-center gap-1 z-20">
                            <RefreshCw className="w-5 h-5 text-sky-400 animate-spin" />
                            <span className="text-[9px] font-bold text-sky-300">Đang tải...</span>
                          </div>
                        )}
                      </div>

                      {/* Card Content (Title & info) */}
                      <div className="p-2 flex-1 flex flex-col justify-between">
                        <p
                          className="text-xs font-semibold text-slate-200 line-clamp-2 leading-tight group-hover:text-white transition-colors"
                          title={v.filename}
                        >
                          {v.filename}
                        </p>

                        <div className="flex items-center justify-between mt-1.5 pt-1.5 border-t border-slate-900 text-[10px] text-slate-400">
                          <span className="truncate max-w-[85px] font-mono text-slate-500" title={v.published_at || ''}>
                            {v.published_at ? new Date(v.published_at).toLocaleDateString('vi-VN') : (isDiscovered ? 'Chờ tải' : `${v.size_mb || 0} MB`)}
                          </span>
                          <div className="flex items-center gap-1">
                            {isProcessed ? (
                              <span
                                className="text-[9px] px-1.5 py-0.5 rounded bg-violet-500/20 text-violet-300 border border-violet-500/40 font-semibold flex items-center gap-0.5"
                                title={v.processed_video_path ? `Đã xuất: ${v.processed_video_path}` : 'Đã có video thành phẩm'}
                              >
                                <Sparkles className="w-2.5 h-2.5 text-violet-400" /> Đã xuất
                              </span>
                            ) : v.has_sub_file ? (
                              <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-semibold">
                                Có Sub
                              </span>
                            ) : null}
                            {v.suggest_remix ? (
                              <span className="text-purple-400 font-medium">⚡ Remix</span>
                            ) : (
                              <span className="text-sky-400 font-medium">🌐 Sub</span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* 4. PAGINATION CONTROLS */}
          {filteredVideos.length > 0 && (
            <div className="flex items-center justify-between pt-3 mt-auto border-t border-slate-800 flex-wrap gap-2 text-xs">
              <div className="text-slate-400">
                Hiển thị <span className="font-bold text-white">{(safeCurrentPage - 1) * pageSize + 1}</span> -{' '}
                <span className="font-bold text-white">{Math.min(safeCurrentPage * pageSize, filteredVideos.length)}</span> trên tổng số{' '}
                <span className="font-bold text-white">{filteredVideos.length}</span> video
              </div>

              {totalPages > 1 && (
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                    disabled={safeCurrentPage === 1}
                    className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed border border-slate-700 flex items-center gap-1 transition"
                  >
                    <ChevronLeft className="w-3.5 h-3.5" /> Trước
                  </button>

                  {renderPaginationButtons(safeCurrentPage, totalPages, setCurrentPage)}

                  <button
                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                    disabled={safeCurrentPage === totalPages}
                    className="px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed border border-slate-700 flex items-center gap-1 transition"
                  >
                    Sau <ChevronRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}

              <div className="flex items-center gap-2">
                <span className="text-slate-400">Hiển thị:</span>
                <select
                  value={pageSize}
                  onChange={(e) => { setPageSize(Number(e.target.value)); setCurrentPage(1); }}
                  className="bg-slate-950 border border-slate-800 rounded-lg px-2 py-1 text-xs text-slate-300 focus:outline-none focus:border-sky-500"
                >
                  <option value={18}>18 / trang</option>
                  <option value={24}>24 / trang</option>
                  <option value={36}>36 / trang</option>
                  <option value={48}>48 / trang</option>
                  <option value={96}>96 / trang</option>
                </select>
              </div>
            </div>
          )}
        </div>
      </div>


      {/* 4. MODAL THÊM KÊNH THEO DÕI (CRAWLER) */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl p-6 w-full max-w-md shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <Rss className="w-4 h-4 text-sky-400" /> Thêm Kênh Cào Video Tự Động
              </h3>
              <button
                onClick={() => setShowAddModal(false)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleAddAccountSubmit} className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-300 font-semibold mb-1">Nền tảng mạng xã hội:</label>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { id: 'douyin', label: 'Douyin' },
                    { id: 'tiktok', label: 'TikTok' },
                    { id: 'bilibili', label: 'Bilibili' },
                    { id: 'facebook', label: 'Facebook' },
                    { id: 'instagram', label: 'Instagram' },
                  ].map(p => (
                    <button
                      type="button"
                      key={p.id}
                      onClick={() => setModalPlatform(p.id)}
                      className={`py-1.5 rounded-lg border font-semibold text-center transition ${
                        modalPlatform === p.id
                          ? 'bg-sky-500/20 border-sky-400 text-sky-300'
                          : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700'
                      }`}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-slate-300 font-semibold mb-1">Link trang cá nhân hoặc Kênh:</label>
                <input
                  type="text"
                  required
                  value={modalUrl}
                  onChange={(e) => setModalUrl(e.target.value)}
                  placeholder="https://www.douyin.com/user/... hoặc https://www.tiktok.com/@creator"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white outline-none focus:border-sky-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-semibold mb-1">Tên gợi nhớ (Tùy chọn):</label>
                <input
                  type="text"
                  value={modalName}
                  onChange={(e) => setModalName(e.target.value)}
                  placeholder="Ví dụ: Kênh Review Phim Hay"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white outline-none focus:border-sky-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-semibold mb-1">Chế độ xử lý sau khi tải:</label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setModalMode('remix')}
                    className={`py-2 px-3 rounded-xl border text-left font-medium transition ${
                      modalMode === 'remix'
                        ? 'bg-amber-500/20 border-amber-400 text-amber-300'
                        : 'bg-slate-950 border-slate-800 text-slate-400'
                    }`}
                  >
                    ⚡ Chỉ Lách Bản Quyền (Remix)
                  </button>
                  <button
                    type="button"
                    onClick={() => setModalMode('dub')}
                    className={`py-2 px-3 rounded-xl border text-left font-medium transition ${
                      modalMode === 'dub'
                        ? 'bg-sky-500/20 border-sky-400 text-sky-300'
                        : 'bg-slate-950 border-slate-800 text-slate-400'
                    }`}
                  >
                    🌐 Dịch Sub & Lồng Tiếng AI (Dub)
                  </button>
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl font-semibold"
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold rounded-xl shadow-lg shadow-sky-500/20 flex items-center gap-1.5"
                >
                  <Plus className="w-3.5 h-3.5" /> Lưu Kênh Theo Dõi
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 4b. MODAL CHỈNH SỬA KÊNH THEO DÕI */}
      {showEditModal && editingAccount && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl p-6 w-full max-w-md shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <Edit3 className="w-4 h-4 text-sky-400" />
                <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                  Chỉnh Sửa Kênh Theo Dõi
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowEditModal(false)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleEditAccountSubmit} className="space-y-3.5 text-xs">
              {/* Platform & Account ID Info (Read-only) */}
              <div className="p-2.5 bg-slate-950/80 border border-slate-800 rounded-xl space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-slate-400">Nền tảng:</span>
                  <div>{getPlatformBadge(editingAccount.platform)}</div>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[11px] text-slate-400">ID Kênh (Cố định):</span>
                  <span className="text-[10px] font-mono text-slate-300 max-w-[200px] truncate" title={editingAccount.account_id}>
                    {editingAccount.account_id}
                  </span>
                </div>
              </div>

              {/* Tên gợi nhớ */}
              <div>
                <label className="block text-slate-300 font-semibold mb-1">Tên gợi nhớ của kênh:</label>
                <input
                  type="text"
                  required
                  value={editingAccount.account_name}
                  onChange={(e) => setEditingAccount(prev => ({ ...prev, account_name: e.target.value }))}
                  placeholder="Ví dụ: Kênh Review Phim Hay"
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white outline-none focus:border-sky-500"
                />
              </div>

              {/* Link kênh */}
              <div>
                <label className="block text-slate-300 font-semibold mb-1">Đường dẫn trang cá nhân / Kênh:</label>
                <input
                  type="text"
                  required
                  value={editingAccount.account_url}
                  onChange={(e) => setEditingAccount(prev => ({ ...prev, account_url: e.target.value }))}
                  placeholder="https://www.douyin.com/user/..."
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white font-mono text-[11px] outline-none focus:border-sky-500"
                />
              </div>

              {/* Chế độ xử lý mặc định */}
              <div>
                <label className="block text-slate-300 font-semibold mb-1">Chế độ xử lý mặc định sau khi tải:</label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setEditingAccount(prev => ({ ...prev, process_mode: 'remix' }))}
                    className={`py-2 px-3 rounded-xl border text-left font-medium transition ${
                      editingAccount.process_mode === 'remix'
                        ? 'bg-amber-500/20 border-amber-400 text-amber-300 font-bold'
                        : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700'
                    }`}
                  >
                    ⚡ Lách Bản Quyền (Remix)
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditingAccount(prev => ({ ...prev, process_mode: 'dub' }))}
                    className={`py-2 px-3 rounded-xl border text-left font-medium transition ${
                      editingAccount.process_mode === 'dub'
                        ? 'bg-sky-500/20 border-sky-400 text-sky-300 font-bold'
                        : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700'
                    }`}
                  >
                    🌐 Dịch & Lồng Tiếng (Dub)
                  </button>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowEditModal(false)}
                  disabled={isSavingEdit}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl font-semibold transition"
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  disabled={isSavingEdit}
                  className="px-5 py-2 bg-sky-500 hover:bg-sky-400 disabled:bg-slate-700 text-slate-950 font-bold rounded-xl shadow-lg shadow-sky-500/20 flex items-center gap-1.5 transition active:scale-95"
                >
                  {isSavingEdit ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Đang lưu...
                    </>
                  ) : (
                    <>
                      <Check className="w-3.5 h-3.5" /> Lưu Thay Đổi
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 5. MODAL CÀI ĐẶT THƯ MỤC TẢI VỀ GỐC */}
      {showStorageModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl p-6 w-full max-w-lg shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <Settings className="w-4 h-4 text-sky-400" /> Cài Đặt Thư Mục Tải Về Gốc
              </h3>
              <button
                onClick={() => setShowStorageModal(false)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-4 text-xs">
              <div className="space-y-1.5">
                <label className="text-slate-300 font-semibold flex items-center gap-1.5">
                  <Folder className="w-3.5 h-3.5 text-sky-400" /> Đường dẫn thư mục tải về hiện tại:
                </label>
                <div className="font-mono bg-slate-950 p-2.5 rounded-xl border border-slate-800 text-sky-300 select-all break-all text-xs">
                  {downloadRootDir || 'Chưa thiết lập'}
                </div>
              </div>

              <div className="flex items-center gap-2 pt-1">
                <button
                  type="button"
                  onClick={async () => {
                    await handlePickDownloadRoot();
                  }}
                  className="flex-1 py-2.5 bg-sky-500/20 hover:bg-sky-500/30 text-sky-300 border border-sky-500/40 rounded-xl font-bold flex items-center justify-center gap-1.5 transition active:scale-95"
                >
                  <Folder className="w-3.5 h-3.5" /> Chọn Thư Mục Khác Trên Máy
                </button>
                {downloadRootDir && (
                  <button
                    type="button"
                    onClick={() => api.openFolder(downloadRootDir)}
                    className="py-2.5 px-3.5 bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 rounded-xl font-semibold flex items-center gap-1.5 transition"
                    title="Mở thư mục trong Windows Explorer"
                  >
                    <ExternalLink className="w-3.5 h-3.5" /> Mở Explorer
                  </button>
                )}
              </div>

              <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-emerald-300 text-[11px] space-y-1">
                <p className="font-bold flex items-center gap-1">
                  <Check className="w-3.5 h-3.5 text-emerald-400" /> Cơ chế tự động phân loại:
                </p>
                <p className="text-slate-400 leading-relaxed">
                  Khi cào video từ các kênh Douyin/TikTok, hệ thống sẽ tự động tạo từng thư mục con riêng biệt bên trong thư mục gốc này: <code className="font-mono text-emerald-300">downloads/&#123;tên_kênh&#125;/</code>
                </p>
              </div>

              <div className="flex justify-end pt-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowStorageModal(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-xl font-semibold transition"
                >
                  Đóng
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 6. MODAL TẢI NHANH VIDEO THEO LINK */}
      {showQuickDownloadModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl p-6 w-full max-w-lg shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <Download className="w-4 h-4 text-emerald-400" /> Tải Video Theo Đường Link
              </h3>
              <button
                onClick={() => setShowQuickDownloadModal(false)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-4 text-xs">
              <div className="space-y-1.5">
                <label className="text-slate-300 font-semibold">Dán liên kết video (Douyin / TikTok / YouTube / Facebook):</label>
                <input
                  type="text"
                  value={quickUrl}
                  onChange={(e) => setQuickUrl(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && !isDownloadingQuick && handleQuickDownload()}
                  placeholder="https://www.douyin.com/video/... hoặc https://vt.tiktok.com/..."
                  className="w-full bg-slate-950 border border-slate-800 focus:border-sky-500 rounded-xl px-3.5 py-2.5 text-white placeholder-slate-500 outline-none text-xs"
                  disabled={isDownloadingQuick}
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-slate-300 font-semibold">Lưu vào thư mục:</label>
                <select
                  value={targetAccount}
                  onChange={(e) => setTargetAccount(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-slate-300 outline-none text-xs"
                  disabled={isDownloadingQuick}
                >
                  {sources.download_subfolders?.map(s => (
                    <option key={s.id} value={s.folder_name}>Lưu vào: downloads/{s.folder_name}/</option>
                  ))}
                  <option value="_new_subfolder_">➕ [Tạo subfolder mới...]</option>
                </select>
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setShowQuickDownloadModal(false)}
                  disabled={isDownloadingQuick}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl font-semibold"
                >
                  Đóng
                </button>
                <button
                  type="button"
                  onClick={async () => {
                    await handleQuickDownload();
                    if (!isDownloadingQuick) setShowQuickDownloadModal(false);
                  }}
                  disabled={isDownloadingQuick || !quickUrl.trim()}
                  className="px-5 py-2 bg-emerald-500 hover:bg-emerald-400 disabled:bg-slate-800 disabled:text-slate-500 text-slate-950 font-bold rounded-xl shadow-lg shadow-emerald-500/20 flex items-center gap-1.5 transition active:scale-95"
                >
                  {isDownloadingQuick ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Đang tải...
                    </>
                  ) : (
                    <>
                      <Download className="w-3.5 h-3.5" /> Bắt Đầu Tải Về
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 7. MODAL ĐĂNG NHẬP / KẾT NỐI COOKIE DOUYIN */}
      {showDouyinLoginModal && (
        <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl p-6 w-full max-w-xl shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            {/* Header */}
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-rose-500/20 text-rose-400 flex items-center justify-center font-bold">
                  <Key className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                    Kết Nối Tài Khoản Douyin
                  </h3>
                  <p className="text-[11px] text-slate-400">
                    Mở khóa cào toàn bộ 100% video của kênh (vượt giới hạn 21 video)
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowDouyinLoginModal(false)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Trạng thái hiện tại */}
            <div className={`p-3 rounded-xl border flex items-center justify-between ${
              isDouyinLoggedIn
                ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                : 'bg-rose-500/10 border-rose-500/30 text-rose-300'
            }`}>
              <div className="flex items-center gap-2 text-xs">
                {isDouyinLoggedIn ? <Check className="w-4 h-4 text-emerald-400 shrink-0" /> : <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />}
                <span className="font-semibold">
                  {isDouyinLoggedIn
                    ? 'Douyin: Đã kết nối / Đã có Cookie đăng nhập (Sẵn sàng cào toàn bộ kênh)'
                    : 'Douyin: Chưa đăng nhập (Douyin sẽ chặn tải sau video thứ 21)'}
                </span>
              </div>
              <button
                type="button"
                onClick={handleCheckDouyinStatus}
                disabled={isCheckingDouyinStatus}
                className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-[11px] font-medium flex items-center gap-1 shrink-0 transition"
              >
                <RefreshCw className={`w-3 h-3 ${isCheckingDouyinStatus ? 'animate-spin' : ''}`} />
                Kiểm tra lại
              </button>
            </div>

            {/* CÁCH 1: NẠP FILE COOKIE HOẶC DÁN JSON (KHUYÊN DÙNG NHẤT) */}
            <div className="p-4 bg-slate-950/70 border border-sky-500/30 rounded-xl space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-sky-400 uppercase tracking-wide flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-amber-400" /> Nạp Cookie JSON (Không Cần Quét QR)
                </span>
                <span className="text-[10px] bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded-full font-semibold">
                  Khuyên dùng • Nhanh 1 chạm
                </span>
              </div>

              {/* Hướng dẫn ngắn gọn */}
              <div className="text-[11px] text-slate-300 space-y-1 bg-slate-900/80 p-3 rounded-xl border border-slate-800">
                <p className="font-semibold text-sky-300">Cách lấy file cookie từ trình duyệt (Chrome / Edge):</p>
                <ol className="list-decimal list-inside space-y-1 text-slate-400">
                  <li>Mở tab <span className="text-white font-mono">douyin.com</span> (đã đăng nhập tài khoản của bạn).</li>
                  <li>Cài tiện ích <b>Cookie-Editor</b> (hoặc <i>EditThisCookie / J2Team</i>).</li>
                  <li>Bấm vào icon Cookie-Editor &rarr; bấm nút <b>Export</b> &rarr; chọn <b>Export as JSON</b>.</li>
                </ol>
              </div>

              {/* VÙNG CHỌN / KÉO THẢ FILE JSON */}
              <div>
                <input
                  type="file"
                  ref={cookieFileInputRef}
                  accept=".json,.txt"
                  onChange={handleCookieFileSelect}
                  className="hidden"
                />
                <div
                  onClick={() => cookieFileInputRef.current?.click()}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                      handleCookieFileSelect({ target: { files: e.dataTransfer.files } });
                    }
                  }}
                  className="border-2 border-dashed border-sky-500/40 hover:border-sky-400 bg-sky-500/5 hover:bg-sky-500/10 rounded-xl p-4 flex flex-col items-center justify-center cursor-pointer transition text-center group"
                >
                  {isUploadingCookieFile ? (
                    <div className="flex items-center gap-2 text-sky-400 text-xs font-medium py-2">
                      <RefreshCw className="w-5 h-5 animate-spin" />
                      <span>Đang nạp và lưu file cookie...</span>
                    </div>
                  ) : (
                    <>
                      <Upload className="w-6 h-6 text-sky-400 group-hover:scale-110 transition-transform mb-1.5" />
                      <span className="text-xs font-semibold text-slate-200">
                        Bấm để chọn file Cookie JSON hoặc kéo thả file vào đây
                      </span>
                      <span className="text-[10px] text-slate-400 mt-0.5 font-mono">
                        (Hỗ trợ file .json xuất từ Cookie-Editor, ví dụ: www.douyin.com_*.json)
                      </span>
                    </>
                  )}
                </div>
              </div>

              <div className="relative flex py-1 items-center">
                <div className="flex-grow border-t border-slate-800"></div>
                <span className="flex-shrink mx-3 text-[10px] text-slate-500 uppercase font-semibold">Hoặc Dán Nội Dung JSON / Cookie</span>
                <div className="flex-grow border-t border-slate-800"></div>
              </div>

              <textarea
                rows={3}
                value={douyinCookieInput}
                onChange={(e) => setDouyinCookieInput(e.target.value)}
                placeholder="Dán nội dung JSON (ví dụ: [{'name': 'sessionid', ...}] hoặc {'cookies': [...]}) hoặc chuỗi cookie vào đây..."
                className="w-full bg-slate-900 border border-slate-700 focus:border-sky-500 rounded-xl p-2.5 text-xs text-slate-200 placeholder-slate-500 outline-none font-mono resize-none"
              />

              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={handleSaveDouyinCookie}
                  disabled={isSavingCookie || !douyinCookieInput.trim()}
                  className="px-4 py-2 bg-sky-500 hover:bg-sky-400 disabled:bg-slate-800 disabled:text-slate-500 text-slate-950 font-bold rounded-xl text-xs flex items-center gap-1.5 transition active:scale-95 shadow-md shadow-sky-500/20"
                >
                  {isSavingCookie ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Đang lưu...
                    </>
                  ) : (
                    <>
                      <Check className="w-3.5 h-3.5" /> Lưu Cookie & Kích Hoạt Ngay
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* CÁCH 2: MỞ CỬA SỔ EDGE QUÉT MÃ QR */}
            <div className="p-4 bg-slate-950/70 border border-slate-800 rounded-xl space-y-3">
              <span className="text-xs font-bold text-slate-300 uppercase tracking-wide flex items-center gap-1.5">
                <Globe className="w-3.5 h-3.5 text-slate-400" /> Cách 2: Mở Cửa Sổ Edge Để Quét Mã QR
              </span>

              <p className="text-[11px] text-slate-400 leading-relaxed">
                Hệ thống sẽ mở một cửa sổ trình duyệt Edge trên màn hình máy tính của bạn. Dùng ứng dụng Douyin trên điện thoại quét mã QR để đăng nhập.
              </p>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleLaunchEdgeForLogin}
                  disabled={isLaunchingEdge}
                  className="flex-1 py-2 px-3 bg-slate-800 hover:bg-slate-700 text-white rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 transition active:scale-95 border border-slate-700"
                >
                  {isLaunchingEdge ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <ExternalLink className="w-3.5 h-3.5" />
                  )}
                  Mở Trình Duyệt Edge Trên Màn Hình
                </button>
                <button
                  type="button"
                  onClick={handleConfirmDouyinLogin}
                  disabled={isCheckingDouyinStatus}
                  className="py-2 px-4 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 rounded-xl text-xs font-bold flex items-center gap-1.5 transition active:scale-95"
                >
                  <Check className="w-3.5 h-3.5" /> Đã Quét Xong, Xác Nhận
                </button>
              </div>
            </div>

            {/* Footer */}
            <div className="flex justify-end pt-2 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setShowDouyinLoginModal(false)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl font-semibold text-xs transition"
              >
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 5. CRAWLER SCANNING PROGRESS OVERLAY MODAL */}
      {scanState.active && !scanState.minimized && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-md flex items-center justify-center z-50 p-4 animate-in fade-in duration-200">
          <div className="bg-[#111827] border border-sky-500/40 rounded-3xl max-w-lg w-full p-6 shadow-2xl space-y-5 relative overflow-hidden">
            {/* Top animated gradient bar */}
            <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-sky-400 via-indigo-500 to-emerald-400 animate-pulse" />

            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3.5 min-w-0">
                <div className="relative w-12 h-12 rounded-2xl bg-sky-500/20 text-sky-400 flex items-center justify-center shrink-0 border border-sky-500/30 shadow-inner">
                  <RefreshCw className="w-6 h-6 animate-spin text-sky-400" />
                  <span className="absolute -top-1 -right-1 flex h-3 w-3">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sky-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-3 w-3 bg-sky-500"></span>
                  </span>
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider bg-sky-500/20 text-sky-300 border border-sky-500/30">
                      {scanState.platform.toUpperCase() || 'DOUYIN'} CRAWLER
                    </span>
                    <span className="text-[11px] text-slate-400 font-medium">
                      • {scanState.forceFullScan ? 'Quét toàn bộ từ đầu' : 'Quét video mới'}
                    </span>
                  </div>
                  <h3 className="text-sm font-bold text-white truncate mt-1">
                    Đang quét: {scanState.accountName}
                  </h3>
                </div>
              </div>

              {/* Minimize button */}
              <button
                type="button"
                onClick={() => setScanState(prev => ({ ...prev, minimized: true }))}
                className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-xl transition text-xs flex items-center gap-1 border border-slate-700/60"
                title="Thu nhỏ xuống góc màn hình để tiếp tục thao tác"
              >
                <span>Thu nhỏ</span>
              </button>
            </div>

            {/* Status box & elapsed timer */}
            <div className="bg-slate-900/90 rounded-2xl p-4 border border-slate-800 space-y-3">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400 flex items-center gap-1.5 font-medium">
                  <Sparkles className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
                  Tiến trình hệ thống:
                </span>
                <span className="font-mono font-bold text-sky-400 bg-sky-950/90 px-2.5 py-0.5 rounded-lg border border-sky-800/80">
                  ⏱️ {Math.floor(scanState.elapsed / 60)}:{(scanState.elapsed % 60).toString().padStart(2, '0')}s
                </span>
              </div>

              <div className="flex items-center gap-2.5 text-xs text-white bg-slate-950/70 p-3 rounded-xl border border-slate-800/60">
                <div className="w-2 h-2 rounded-full bg-emerald-400 animate-ping shrink-0" />
                <span className="leading-relaxed font-medium">{scanState.statusText}</span>
              </div>

              {/* Animated Progress Bar */}
              <div className="w-full bg-slate-950 rounded-full h-2 overflow-hidden border border-slate-800">
                <div 
                  className="bg-gradient-to-r from-sky-500 via-indigo-500 to-emerald-400 h-full rounded-full transition-all duration-500 relative"
                  style={{
                    width: `${Math.min(95, Math.max(12, scanState.elapsed * 3.5))}%`
                  }}
                >
                  <div className="absolute inset-0 bg-white/20 animate-pulse" />
                </div>
              </div>
            </div>

            {/* Note info */}
            <div className="flex items-start gap-2.5 text-[11px] text-slate-400 bg-slate-900/60 border border-slate-800 rounded-xl p-3">
              <AlertCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <p className="leading-relaxed">
                Hệ thống đang mở trình duyệt Headless tự động cuộn trang và tải thumbnail cho từng video để tránh Douyin chặn spam. Quá trình này có thể mất 10 - 30 giây tùy theo số lượng video của kênh.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 6. MINIMIZED FLOATING BADGE (Bottom-Right) */}
      {scanState.active && scanState.minimized && (
        <div 
          onClick={() => setScanState(prev => ({ ...prev, minimized: false }))}
          className="fixed bottom-6 right-6 z-50 bg-[#111827] border-2 border-sky-500/60 hover:border-sky-400 rounded-2xl p-3.5 shadow-2xl flex items-center gap-3 cursor-pointer transition hover:scale-105 active:scale-95 group max-w-sm"
          title="Bấm để mở lại bảng tiến trình chi tiết"
        >
          <div className="relative w-8 h-8 rounded-xl bg-sky-500/20 text-sky-400 flex items-center justify-center shrink-0">
            <RefreshCw className="w-4 h-4 animate-spin text-sky-400" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] font-bold text-sky-400 uppercase">Đang quét</span>
              <span className="text-[10px] font-mono text-slate-400">
                ⏱️ {Math.floor(scanState.elapsed / 60)}:{(scanState.elapsed % 60).toString().padStart(2, '0')}s
              </span>
            </div>
            <p className="text-xs font-bold text-white truncate">{scanState.accountName}</p>
            <p className="text-[10px] text-slate-400 truncate">{scanState.statusText}</p>
          </div>
        </div>
      )}
    </div>
  );
}
