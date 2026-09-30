import React, { useState, useEffect, useRef } from 'react';
import { 
  Play, Pause, SkipBack, SkipForward, Scissors, Plus, Trash2, 
  Sparkles, Sliders, Type, Layers, Check, Download, Video, ArrowRight,
  Volume2, VolumeX, Magnet, Maximize2, Radio, Upload, Image as ImageIcon
} from 'lucide-react';
import * as api from '../services/api';

export default function StudioScreen({ 
  selectedVideo, 
  setSelectedVideo,
  workflowMode, 
  setWorkflowMode, 
  onGoToPublishing, 
  onGoToIngestion,
  showToast 
}) {
  // Video & Playhead state
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentSeconds, setCurrentSeconds] = useState(0);
  const [totalSeconds, setTotalSeconds] = useState(0);
  const [videoDims, setVideoDims] = useState('');
  const [aspectRatio, setAspectRatio] = useState('9:16');
  const [previewFrameUrl, setPreviewFrameUrl] = useState(null);

  // Subtitle Bounding Box state
  const [marginV, setMarginV] = useState(38); // px from bottom
  const [boxPadding, setBoxPadding] = useState(6); // px padding
  const [boxWidth, setBoxWidth] = useState(88); // % width
  const [maskStyle, setMaskStyle] = useState('solid_black'); // 'solid_black' | 'blur_box' | 'solid_white' | 'classic'
  const [fontFamily, setFontFamily] = useState('font-bevietnam');
  const [fontSize, setFontSize] = useState(13);
  const [fontColor, setFontColor] = useState('#ffffff');

  // Timeline Filmstrip Frames (16 distinct timestamps)
  const [timelineFrames, setTimelineFrames] = useState([]);

  // Subtitle Segments
  const [segments, setSegments] = useState([]);
  const [activeSegmentId, setActiveSegmentId] = useState(null);

  // Audio & Inspector state
  const [isOrigMuted, setIsOrigMuted] = useState(false);
  const [audioDucking, setAudioDucking] = useState(12);
  const [voiceSpeed, setVoiceSpeed] = useState(1.05);
  const [selectedVoice, setSelectedVoice] = useState('vi-VN-HoaiMyNeural');
  const [activeInspectorTab, setActiveInspectorTab] = useState('tab-style'); // 'tab-style' | 'tab-voice' | 'tab-anti'

  // Lab Anti-detect Combo & Branding Watermark
  const [activeCombo, setActiveCombo] = useState('stealth'); // 'stealth' | 'cinema' | 'crt' | 'fortress'
  const [pitchShift, setPitchShift] = useState(true);
  const [watermarkEnabled, setWatermarkEnabled] = useState(true);
  const [watermarkType, setWatermarkType] = useState('image'); // 'image' | 'text'
  const [watermarkLogoUrl, setWatermarkLogoUrl] = useState(null);
  const [watermarkFilename, setWatermarkFilename] = useState(null);
  const [watermarkText, setWatermarkText] = useState('KEN STUDIO');
  const logoInputRef = useRef(null);

  // Timeline UI state
  const [zoomLevel, setZoomLevel] = useState(100);
  const [magnetEnabled, setMagnetEnabled] = useState(true);
  const [isScrubbing, setIsScrubbing] = useState(false);

  // Auto-translate & Subtitle import state
  const [isTranslating, setIsTranslating] = useState(false);
  const [translateStep, setTranslateStep] = useState(1);
  const [translateProgress, setTranslateProgress] = useState(0);
  const [translateMessage, setTranslateMessage] = useState('');
  const [translateError, setTranslateError] = useState(null);
  const [translateSuccessData, setTranslateSuccessData] = useState(null);
  const srtInputRef = useRef(null);
  const translatePollTimerRef = useRef(null);

  // Export progress modal
  const [isExporting, setIsExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState(0);
  const [exportedResult, setExportedResult] = useState(null);
  const [exportError, setExportError] = useState(null);

  // Subtitle Bounding Box Drag & Resize state
  const [isDraggingBox, setIsDraggingBox] = useState(false);
  const [isResizingBox, setIsResizingBox] = useState(null);
  const dragStartRef = useRef({ y: 0, marginV: 38, x: 0, width: 88, padding: 6 });

  // References
  const tracksWrapperRef = useRef(null);
  const videoRef = useRef(null);

  // Load video info, preview frame & 16 timeline frames when selectedVideo changes
  useEffect(() => {
    if (selectedVideo?.path) {
      loadVideoDetails(selectedVideo.path);
      // Nạp phụ đề srt có sẵn đi kèm nếu có (hoặc để mảng rỗng)
      api.getSubtitles(selectedVideo.path).then(subs => {
        if (subs && Array.isArray(subs) && subs.length > 0) {
          setSegments(subs);
          setActiveSegmentId(subs[0].id);
        } else {
          setSegments([]);
          setActiveSegmentId(null);
        }
      });
      if (videoRef.current) {
        videoRef.current.currentTime = 0;
        videoRef.current.pause();
      }
      setIsPlaying(false);
      setCurrentSeconds(0);
    } else {
      // Khi không có video: đưa toàn bộ trạng thái về trắng/trống hoàn toàn
      setSegments([]);
      setActiveSegmentId(null);
      setTimelineFrames([]);
      setPreviewFrameUrl(null);
      setVideoDims('');
      setTotalSeconds(0);
      setCurrentSeconds(0);
      setIsPlaying(false);
    }
  }, [selectedVideo]);

  const handlePickVideoDirect = async () => {
    showToast('Đang mở hộp thoại Windows Explorer để chọn file video...', 'info');
    const res = await api.pickFiles();
    if (res && res.success && res.videos?.length > 0) {
      const v = res.videos[0];
      if (setSelectedVideo) setSelectedVideo(v);
      showToast(`✓ Đã nạp video <b>${v.filename}</b> vào Studio!`, 'success');
    }
  };

  const addCacheBuster = (url) => {
    if (!url) return null;
    return url.includes('?') ? `${url}&t=${Date.now()}` : `${url}?t=${Date.now()}`;
  };

  // Nạp thông tin logo thương hiệu đã lưu vĩnh viễn lúc mở Studio
  useEffect(() => {
    api.getLogoInfo().then(info => {
      if (info) {
        if (info.exists && info.url) {
          setWatermarkLogoUrl(addCacheBuster(info.url));
          setWatermarkFilename(info.filename);
          setWatermarkType('image');
        }
        if (info.watermark_enabled !== undefined) {
          setWatermarkEnabled(info.watermark_enabled);
        }
        if (info.watermark_text) {
          setWatermarkText(info.watermark_text);
        }
      }
    });
  }, []);

  const handleLogoFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    showToast('Đang tải lên và lưu logo thương hiệu...', 'info');
    const res = await api.uploadLogo(file);
    if (res && res.success) {
      setWatermarkLogoUrl(addCacheBuster(res.url));
      setWatermarkFilename(res.filename);
      setWatermarkType('image');
      setWatermarkEnabled(true);
      showToast('✓ Đã lưu logo thương hiệu vĩnh viễn cho mọi video!', 'success');
    } else {
      showToast('❌ Không thể tải file logo!', 'error');
    }
  };

  const handleRemoveLogo = async () => {
    await api.deleteLogo();
    setWatermarkLogoUrl(null);
    setWatermarkFilename(null);
    setWatermarkType('text');
    showToast('✓ Đã gỡ bỏ logo ảnh, chuyển về dùng chữ text', 'info');
  };

  const loadVideoDetails = async (vPath) => {
    const info = await api.getVideoInfo(vPath);
    if (info) {
      setVideoDims(`${info.width} × ${info.height} px (${info.aspect_ratio || '9:16'})`);
      if (info.duration_sec) setTotalSeconds(info.duration_sec);
    }

    // 1. Trích xuất frame fallback
    api.getPreviewFrame(vPath, 1.0).then(frameData => {
      if (frameData && frameData.data_url) {
        setPreviewFrameUrl(frameData.data_url);
      }
    });

    // 2. Trích xuất chuỗi 16 frames phân bổ theo thời lượng video cho dải filmstrip timeline
    api.getTimelineFrames(vPath, 16).then(data => {
      if (data && data.frames && data.frames.length > 0) {
        setTimelineFrames(data.frames);
      }
    });
  };

  // Video playback & seeking controls
  const togglePlayPause = () => {
    if (!videoRef.current) return;
    if (videoRef.current.paused) {
      videoRef.current.play().catch(err => console.warn("Video play error:", err));
    } else {
      videoRef.current.pause();
    }
  };

  const seekTo = (sec) => {
    const s = Math.max(0, Math.min(totalSeconds, sec));
    setCurrentSeconds(s);
    if (videoRef.current) {
      videoRef.current.currentTime = s;
    }
  };

  const toggleMute = () => {
    const nextMuted = !isOrigMuted;
    setIsOrigMuted(nextMuted);
    if (videoRef.current) {
      videoRef.current.muted = nextMuted;
    }
    showToast(nextMuted ? '🔇 Tiếng gốc: Đã Tắt (Mute)' : '🔊 Tiếng gốc: Đã Bật', 'info');
  };

  // Sync active segment when currentSeconds changes
  useEffect(() => {
    const seg = segments.find(s => currentSeconds >= s.start && currentSeconds < s.end);
    if (seg && seg.id !== activeSegmentId) {
      setActiveSegmentId(seg.id);
    }
  }, [currentSeconds, segments]);

  const activeSegment = segments.find(s => s.id === activeSegmentId) || (segments.length > 0 ? segments[0] : null);

  const updateActiveText = (text) => {
    if (!activeSegmentId) return;
    setSegments(prev => prev.map(s => s.id === activeSegmentId ? { ...s, text } : s));
  };

  // Timeline scrub handler
  const handleTimelineMouseDown = (e) => {
    setIsScrubbing(true);
    updatePlayheadPosition(e);
  };

  const updatePlayheadPosition = (e) => {
    if (!tracksWrapperRef.current) return;
    const rect = tracksWrapperRef.current.getBoundingClientRect();
    const clickX = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
    const pct = clickX / rect.width;
    const newSeconds = Math.max(0, Math.min(totalSeconds, pct * totalSeconds));
    setCurrentSeconds(newSeconds);
    if (videoRef.current) {
      videoRef.current.currentTime = newSeconds;
    }
  };

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (isScrubbing) {
        updatePlayheadPosition(e);
      }
    };
    const handleMouseUp = () => {
      if (isScrubbing) setIsScrubbing(false);
    };
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isScrubbing, totalSeconds]);

  // Handle drag & resize for Subtitle Bounding Box on canvas
  const handleHandleMouseDown = (e, handleType) => {
    e.stopPropagation();
    setIsResizingBox(handleType);
    dragStartRef.current = {
      y: e.clientY,
      marginV: marginV,
      x: e.clientX,
      width: boxWidth,
      padding: boxPadding,
    };
  };

  useEffect(() => {
    const handleBoxMouseMove = (e) => {
      if (isDraggingBox) {
        const deltaY = dragStartRef.current.y - e.clientY;
        const newMargin = Math.max(5, Math.min(350, Math.round(dragStartRef.current.marginV + deltaY)));
        setMarginV(newMargin);
      } else if (isResizingBox) {
        if (isResizingBox.includes('e') || isResizingBox.includes('w')) {
          const deltaX = (e.clientX - dragStartRef.current.x) * (isResizingBox.includes('w') ? -1 : 1);
          const widthDeltaPct = Math.round((deltaX / 260) * 100);
          const newWidth = Math.max(40, Math.min(98, dragStartRef.current.width + widthDeltaPct));
          setBoxWidth(newWidth);
        }
        if (isResizingBox.includes('n') || isResizingBox.includes('s')) {
          const deltaY = Math.abs(e.clientY - dragStartRef.current.y);
          const newPad = Math.max(2, Math.min(24, Math.round(dragStartRef.current.padding + (deltaY / 6))));
          setBoxPadding(newPad);
        }
      }
    };

    const handleBoxMouseUp = () => {
      if (isDraggingBox) setIsDraggingBox(false);
      if (isResizingBox) setIsResizingBox(null);
    };

    if (isDraggingBox || isResizingBox) {
      window.addEventListener('mousemove', handleBoxMouseMove);
      window.addEventListener('mouseup', handleBoxMouseUp);
    }
    return () => {
      window.removeEventListener('mousemove', handleBoxMouseMove);
      window.removeEventListener('mouseup', handleBoxMouseUp);
    };
  }, [isDraggingBox, isResizingBox]);

  // Keyboard shortcut Space to Play/Pause
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.code === 'Space' && e.target.tagName !== 'TEXTAREA' && e.target.tagName !== 'INPUT') {
        e.preventDefault();
        togglePlayPause();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const formatTimecode = (sec) => {
    const mins = Math.floor(sec / 60);
    const secs = Math.floor(sec % 60);
    const frames = Math.floor((sec % 1) * 30);
    const pad = (n) => String(n).padStart(2, '0');
    return `${pad(mins)}:${pad(secs)}:${pad(frames)}`;
  };

  const splitCurrentSegment = () => {
    const cur = activeSegment;
    if (!cur) return;
    const mid = +currentSeconds.toFixed(1);
    if (mid <= cur.start + 0.3 || mid >= cur.end - 0.3) {
      showToast('Kéo kim playhead vào giữa đoạn phụ đề để tách câu!', 'warning');
      return;
    }
    const newId = Date.now();
    const newSeg = {
      id: newId,
      start: mid,
      end: cur.end,
      text: 'Đoạn phụ đề tách mới'
    };
    setSegments(prev => [
      ...prev.map(s => s.id === cur.id ? { ...s, end: mid } : s),
      newSeg
    ].sort((a, b) => a.start - b.start));
    setActiveSegmentId(newId);
    showToast('✓ Đã tách câu phụ đề tại vị trí kim!', 'success');
  };

  const addNewSegment = () => {
    const newId = Date.now();
    const start = +currentSeconds.toFixed(1);
    const end = totalSeconds > 0 ? Math.min(totalSeconds, start + 3.0) : start + 3.0;
    const newSeg = {
      id: newId,
      start,
      end,
      text: 'Câu phụ đề mới vừa thêm'
    };
    setSegments(prev => [...prev, newSeg].sort((a, b) => a.start - b.start));
    setActiveSegmentId(newId);
    showToast('✓ Đã thêm một câu phụ đề mới!', 'success');
  };

  const deleteActiveSegment = () => {
    if (segments.length === 0) return;
    const nextSegments = segments.filter(s => s.id !== activeSegmentId);
    setSegments(nextSegments);
    if (nextSegments.length > 0) {
      setActiveSegmentId(nextSegments[0].id);
    } else {
      setActiveSegmentId(null);
    }
    showToast('✓ Đã xóa câu phụ đề!', 'info');
  };

  const clearAllSegments = () => {
    if (segments.length === 0) return;
    if (window.confirm('Bạn có chắc muốn xóa TOÀN BỘ phụ đề không?')) {
      setSegments([]);
      setActiveSegmentId(null);
      showToast('✓ Đã xóa sạch toàn bộ phụ đề!', 'info');
    }
  };

  // Dọn dẹp timer polling khi unmount
  useEffect(() => {
    return () => {
      if (translatePollTimerRef.current) clearInterval(translatePollTimerRef.current);
    };
  }, []);

  const handleStartAutoTranslate = async () => {
    if (!selectedVideo?.path) {
      showToast('Chưa chọn video nào để dịch!', 'warning');
      return;
    }

    setIsTranslating(true);
    setTranslateStep(1);
    setTranslateProgress(10);
    setTranslateMessage('Đang trích xuất luồng âm thanh WAV từ video...');
    setTranslateError(null);
    setTranslateSuccessData(null);

    // Bắt đầu vòng lặp polling tiến độ từ server
    if (translatePollTimerRef.current) clearInterval(translatePollTimerRef.current);
    translatePollTimerRef.current = setInterval(async () => {
      const prog = await api.getTranslateProgress(selectedVideo.path);
      if (prog && prog.status === 'running') {
        if (prog.step) setTranslateStep(prog.step);
        if (prog.progress) setTranslateProgress(prog.progress);
        if (prog.message) setTranslateMessage(prog.message);
      }
    }, 500);

    try {
      showToast('🚀 Khởi chạy chu trình Dịch AI (Whisper + Gemini)...', 'info');
      const res = await api.autoTranslate({
        video_path: selectedVideo.path,
        source_lang: 'zh-CN',
        target_lang: 'vi',
      });

      if (translatePollTimerRef.current) {
        clearInterval(translatePollTimerRef.current);
        translatePollTimerRef.current = null;
      }

      if (res && res.success) {
        setTranslateProgress(100);
        setTranslateStep(3);
        setTranslateMessage(res.message || 'Dịch thuật hoàn tất!');
        setTranslateSuccessData(res);

        if (res.segments && res.segments.length > 0) {
          setSegments(res.segments);
          setActiveSegmentId(res.segments[0].id);
          showToast(`✓ Đã nhận diện & dịch thành công ${res.segments.length} câu! Phụ đề đã nạp vào Studio.`, 'success');
        } else {
          showToast('ℹ️ Không phát hiện giọng nói nào trong video.', 'info');
        }
      } else {
        throw new Error(res?.detail || 'Không thể hoàn thành dịch thuật AI');
      }
    } catch (err) {
      if (translatePollTimerRef.current) {
        clearInterval(translatePollTimerRef.current);
        translatePollTimerRef.current = null;
      }
      setTranslateError(err.message || 'Lỗi xử lý dịch thuật');
      showToast(`❌ Lỗi dịch AI: ${err.message}`, 'error');
    }
  };

  const handleImportSrt = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!selectedVideo?.path) {
      showToast('Vui lòng chọn video trước khi nạp file phụ đề!', 'warning');
      return;
    }

    showToast(`Đang nạp file phụ đề: ${file.name}...`, 'info');
    const res = await api.importSrt(file, selectedVideo.path);
    if (res && res.success && res.segments) {
      setSegments(res.segments);
      if (res.segments.length > 0) {
        setActiveSegmentId(res.segments[0].id);
      }
      showToast(`✓ Đã nạp thành công ${res.segments.length} câu phụ đề từ file ${file.name}!`, 'success');
    } else {
      showToast('❌ Không thể nạp file phụ đề SRT!', 'error');
    }
    e.target.value = '';
  };

  const startExportNVENC = async () => {
    if (!selectedVideo?.path) {
      showToast('Chưa chọn video nào để xuất!', 'warning');
      return;
    }

    setIsExporting(true);
    setExportProgress(15);
    setExportError(null);
    setExportedResult(null);

    const progressTimer = setInterval(() => {
      setExportProgress(prev => (prev < 85 ? prev + 10 : prev));
    }, 400);

    try {
      showToast(`🚀 Đang xuất video NVENC [${workflowMode === 'remix' ? 'Chỉ Lách BQ' : 'Dịch & Đè Sub'}]...`, 'info');

      const res = await api.exportVideo({
        video_path: selectedVideo.path,
        mode: workflowMode,
        subfolder: selectedVideo.subfolder || 'general_inbox',
        anti_combo: activeCombo,
        segments: segments,
        mask_style: maskStyle,
        box_opacity: 100,
        font_size: fontSize,
        box_padding: boxPadding,
        margin_v: marginV,
        voice: selectedVoice,
        pitch_shift: pitchShift,
        watermark_enabled: watermarkEnabled,
        watermark_text: watermarkText,
      });

      clearInterval(progressTimer);

      if (res && res.success) {
        setExportProgress(100);
        setExportedResult(res);
        showToast(`🎉 Xuất video hoàn tất: ${res.filename}`, 'success');
      } else {
        throw new Error(res?.detail || 'Lỗi không xác định khi render video');
      }
    } catch (err) {
      clearInterval(progressTimer);
      setExportError(err.message);
      showToast(`❌ Lỗi render video: ${err.message}`, 'error');
    }
  };

  const playheadPercent = totalSeconds > 0 ? (currentSeconds / totalSeconds) * 100 : 0;

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-slate-950 select-none">
      
      {/* 1. TOP SUBHEADER BAR */}
      <div className="h-10 bg-slate-900 border-b border-slate-800 px-4 flex items-center justify-between text-xs shrink-0">
        <div className="flex items-center gap-3">
          <span className="font-bold text-white flex items-center gap-1.5 font-display truncate max-w-sm">
            <Video className={`w-3.5 h-3.5 shrink-0 ${selectedVideo ? 'text-sky-400' : 'text-slate-600'}`} />
            <span className="truncate">
              {selectedVideo ? selectedVideo.filename : <span className="text-slate-500 italic font-normal">Chưa chọn video nào</span>}
            </span>
          </span>
          <span className="font-mono text-[10px] bg-slate-950 text-slate-400 px-2 py-0.5 rounded border border-slate-800">
            {selectedVideo && videoDims ? videoDims : '-- × -- px'}
          </span>
          <span className="font-mono text-[10px] bg-emerald-500/10 text-emerald-300 px-2 py-0.5 rounded border border-emerald-500/20">
            ready_to_upload/{selectedVideo?.subfolder || '--'}/
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Workflow Toggle */}
          <div className="flex items-center bg-slate-950 p-0.5 rounded-lg border border-slate-800 text-[11px]">
            <button
              onClick={() => setWorkflowMode('translate')}
              className={`px-2.5 py-1 rounded font-bold transition flex items-center gap-1 ${
                workflowMode === 'translate'
                  ? 'bg-sky-500 text-slate-950'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              🌐 Dịch & Biên Tập
            </button>
            <button
              onClick={() => setWorkflowMode('remix')}
              className={`px-2.5 py-1 rounded font-bold transition flex items-center gap-1 ${
                workflowMode === 'remix'
                  ? 'bg-amber-400 text-slate-950'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              ⚡ Chỉ Lách BQ
            </button>
          </div>

          <button
            onClick={startExportNVENC}
            className="px-3.5 py-1.5 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-slate-950 font-extrabold rounded-lg shadow-md text-xs flex items-center gap-1.5 transition active:scale-95"
          >
            <Download className="w-3.5 h-3.5 stroke-[2.5]" /> Xuất Video (NVENC)
          </button>
        </div>
      </div>

      {/* 2. CENTER WORKSPACE: VIDEO CANVAS 9:16 + RIGHT INSPECTOR */}
      <div className="flex-1 flex overflow-hidden">
        
        {/* CENTER VIDEO CANVAS */}
        <div className="flex-1 bg-[#090d16] p-3 flex flex-col items-center justify-center relative overflow-hidden">
          
          {/* 9:16 Aspect Phone Canvas Container */}
          <div 
            style={{ 
              width: aspectRatio === '9:16' ? '260px' : '520px', 
              height: aspectRatio === '9:16' ? '462px' : '292px' 
            }}
            className="relative bg-black rounded-2xl shadow-2xl border-2 border-slate-800 overflow-hidden flex items-center justify-center select-none transition-all duration-300 group"
          >
            {/* Real Native HTML5 Video Stream */}
            {selectedVideo?.path ? (
              <video
                ref={videoRef}
                src={api.getVideoStreamUrl(selectedVideo.path)}
                className="w-full h-full object-cover"
                playsInline
                preload="auto"
                muted={isOrigMuted}
                onClick={togglePlayPause}
                onTimeUpdate={(e) => {
                  if (!isScrubbing) {
                    setCurrentSeconds(e.currentTarget.currentTime);
                  }
                }}
                onLoadedMetadata={(e) => {
                  const dur = e.currentTarget.duration;
                  if (dur && !isNaN(dur) && dur > 0) {
                    setTotalSeconds(dur);
                  }
                  const vw = e.currentTarget.videoWidth;
                  const vh = e.currentTarget.videoHeight;
                  if (vw && vh) {
                    const ratio = vw / vh;
                    const isPortrait = ratio < 0.85;
                    setAspectRatio(isPortrait ? '9:16' : '16:9');
                    setVideoDims(`${vw} × ${vh} px (${isPortrait ? '9:16 Dọc' : '16:9 Ngang'})`);
                  }
                }}
                onPlay={() => setIsPlaying(true)}
                onPause={() => setIsPlaying(false)}
                onEnded={() => setIsPlaying(false)}
              />
            ) : (
              /* Trạng thái trống khi chưa có video nào được chọn */
              <div className="absolute inset-0 flex flex-col items-center justify-center p-6 text-center text-slate-400 bg-slate-950/95 z-20 space-y-3">
                <div className="w-14 h-14 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-center text-slate-600 shadow-inner">
                  <Video className="w-7 h-7 text-slate-500" />
                </div>
                <div>
                  <h3 className="text-xs font-bold text-white mb-1">Chưa có video được chọn</h3>
                  <p className="text-[11px] text-slate-500 max-w-[200px] leading-relaxed">
                    Chọn video từ tab Nguồn hoặc mở trực tiếp từ máy tính.
                  </p>
                </div>
                <div className="space-y-1.5 w-full max-w-[200px] pt-1">
                  <button
                    onClick={handlePickVideoDirect}
                    className="w-full py-1.5 bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold text-[11px] rounded-lg shadow-md transition flex items-center justify-center gap-1 active:scale-95 pointer-events-auto"
                  >
                    <Upload className="w-3.5 h-3.5" /> Mở Video Máy Tính
                  </button>
                  {onGoToIngestion && (
                    <button
                      onClick={onGoToIngestion}
                      className="w-full py-1.5 bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-700 font-semibold text-[11px] rounded-lg transition flex items-center justify-center gap-1 active:scale-95 pointer-events-auto"
                    >
                      ← Tab Thu Thập Nguồn
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Center Play Button Overlay when paused */}
            {selectedVideo?.path && !isPlaying && (
              <div 
                className="absolute inset-0 flex items-center justify-center pointer-events-none z-10"
              >
                <button 
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    togglePlayPause();
                  }}
                  className="w-14 h-14 rounded-full bg-white/90 hover:bg-white text-slate-900 flex items-center justify-center pl-1 shadow-2xl backdrop-blur transition transform hover:scale-110 active:scale-95 pointer-events-auto border border-white/80"
                  title="Phát video (Phím Space)"
                >
                  <Play className="w-7 h-7 fill-slate-900" />
                </button>
              </div>
            )}

            {/* Simulated Anti-detect Filter Layers */}
            {selectedVideo?.path && activeCombo === 'stealth' && <div className="absolute inset-0 fx-grain pointer-events-none opacity-40"></div>}
            {selectedVideo?.path && activeCombo === 'cinema' && <div className="absolute inset-0 fx-vignette pointer-events-none"></div>}
            {selectedVideo?.path && activeCombo === 'crt' && <div className="absolute inset-0 fx-crt pointer-events-none"></div>}
            {selectedVideo?.path && activeCombo === 'fortress' && (
              <>
                <div className="absolute inset-0 fx-vignette pointer-events-none"></div>
                <div className="absolute inset-0 fx-mesh pointer-events-none opacity-60"></div>
              </>
            )}

            {/* Watermark overlay */}
            {selectedVideo?.path && watermarkEnabled && (
              <div className="absolute top-3 right-3 pointer-events-none select-none z-10 flex items-center justify-end">
                {watermarkType === 'image' && watermarkLogoUrl ? (
                  <img
                    src={watermarkLogoUrl}
                    alt="Brand Logo"
                    className="h-8 max-w-[100px] object-contain drop-shadow-md opacity-85"
                  />
                ) : (
                  <div className="px-2 py-0.5 bg-black/60 backdrop-blur rounded text-[10px] font-extrabold font-mono text-white tracking-widest border border-white/20">
                    {watermarkText}
                  </div>
                )}
              </div>
            )}

            {/* SUBTITLE BOUNDING BOX (KÉO THẢ & CO GIÃN 8 HANDLE) */}
            {selectedVideo?.path && workflowMode === 'translate' && activeSegment && (
              <div
                onMouseDown={(e) => {
                  if (e.target.classList.contains('handle')) return;
                  e.stopPropagation();
                  setIsDraggingBox(true);
                  dragStartRef.current = {
                    y: e.clientY,
                    marginV: marginV,
                    x: e.clientX,
                    width: boxWidth,
                    padding: boxPadding,
                  };
                }}
                style={{
                  bottom: `${marginV}px`,
                  width: `${boxWidth}%`,
                  padding: `${boxPadding}px ${Math.round(boxPadding * 1.5)}px`,
                  backgroundColor: 
                    maskStyle === 'solid_black' ? '#000000' :
                    maskStyle === 'blur_box' ? 'rgba(15, 23, 42, 0.65)' :
                    maskStyle === 'solid_white' ? '#ffffff' : 'transparent',
                  backdropFilter: maskStyle === 'blur_box' ? 'blur(12px)' : 'none',
                  border: maskStyle === 'classic' ? '2px dashed #00f2fe' : '2px solid #00f2fe',
                }}
                className={`absolute z-20 cursor-move rounded-lg flex items-center justify-center transition-all shadow-lg shadow-sky-500/20 group/box ${
                  isDraggingBox || isResizingBox ? 'ring-2 ring-[#00f2fe]' : ''
                }`}
                title="Kéo hộp để chỉnh vị trí viền dưới (MarginV), kéo 8 chấm để co giãn kích thước"
              >
                <p
                  style={{
                    fontSize: `${fontSize}px`,
                    color: maskStyle === 'solid_white' ? '#000000' : fontColor,
                    textShadow: maskStyle === 'classic' 
                      ? '-1px -1px 0 #000, 1px -1px 0 #000, -1px 1px 0 #000, 1px 1px 0 #000' 
                      : 'none',
                  }}
                  className={`${fontFamily} font-bold text-center leading-snug select-none px-1 pointer-events-none`}
                >
                  {activeSegment ? activeSegment.text : 'Nội dung phụ đề tiếng Việt'}
                </p>

                {/* 8 Resize Handles */}
                <div className="handle handle-nw" onMouseDown={(e) => handleHandleMouseDown(e, 'nw')} />
                <div className="handle handle-ne" onMouseDown={(e) => handleHandleMouseDown(e, 'ne')} />
                <div className="handle handle-sw" onMouseDown={(e) => handleHandleMouseDown(e, 'sw')} />
                <div className="handle handle-se" onMouseDown={(e) => handleHandleMouseDown(e, 'se')} />
                <div className="handle handle-n" onMouseDown={(e) => handleHandleMouseDown(e, 'n')} />
                <div className="handle handle-s" onMouseDown={(e) => handleHandleMouseDown(e, 's')} />
                <div className="handle handle-w" onMouseDown={(e) => handleHandleMouseDown(e, 'w')} />
                <div className="handle handle-e" onMouseDown={(e) => handleHandleMouseDown(e, 'e')} />

                {/* Live Position Badge when dragging */}
                {(isDraggingBox || isResizingBox) && (
                  <div className="absolute -top-6 bg-slate-900/90 text-[#00f2fe] border border-sky-500/50 px-2 py-0.5 rounded text-[9px] font-mono pointer-events-none shadow-md backdrop-blur">
                    MarginV: {marginV}px • Rộng: {boxWidth}% • Pad: {boxPadding}px
                  </div>
                )}
              </div>
            )}
          </div>

        </div>

        {/* RIGHT INSPECTOR (3 TABS: STYLE, VOICE, LAB LÁCH BQ) */}
        <aside className="w-80 bg-slate-900 border-l border-slate-800 flex flex-col shrink-0 overflow-y-auto">
          {/* Tab Headers */}
          <div className="flex border-b border-slate-800 text-xs font-bold text-slate-400 bg-slate-950/60">
            <button
              onClick={() => setActiveInspectorTab('tab-style')}
              className={`flex-1 py-3 transition ${
                activeInspectorTab === 'tab-style'
                  ? 'text-sky-400 border-b-2 border-sky-400 font-bold'
                  : 'hover:text-slate-200'
              }`}
            >
              🔤 Phụ Đề & Hộp
            </button>
            <button
              onClick={() => setActiveInspectorTab('tab-voice')}
              className={`flex-1 py-3 transition ${
                activeInspectorTab === 'tab-voice'
                  ? 'text-sky-400 border-b-2 border-sky-400 font-bold'
                  : 'hover:text-slate-200'
              }`}
            >
              🎙️ Giọng Đọc
            </button>
            <button
              onClick={() => setActiveInspectorTab('tab-anti')}
              className={`flex-1 py-3 transition flex items-center justify-center gap-1 ${
                activeInspectorTab === 'tab-anti'
                  ? 'text-amber-400 border-b-2 border-amber-400 font-bold'
                  : 'hover:text-slate-200'
              }`}
            >
              <span>🛡️ Lab Lách BQ</span>
              <span className="w-2 h-2 rounded-full bg-amber-400"></span>
            </button>
          </div>

          {/* TAB 1: SUBTITLE & BOX STYLE */}
          {activeInspectorTab === 'tab-style' && (
            <div className="p-4 space-y-4 text-xs">
              
              {/* AI Auto-Translation Banner / Status */}
              {segments.length === 0 ? (
                <div className="bg-gradient-to-br from-sky-950/70 via-slate-900 to-indigo-950/70 p-3.5 rounded-xl border border-sky-500/30 shadow-lg space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-sky-300 flex items-center gap-1.5">
                      <Sparkles className="w-4 h-4 text-amber-400" />
                      <span>DỊCH PHỤ ĐỀ TỰ ĐỘNG</span>
                    </span>
                    <span className="text-[9px] bg-sky-500/20 text-sky-300 px-1.5 py-0.5 rounded font-mono">Whisper + Gemini</span>
                  </div>
                  <p className="text-[11px] text-slate-300 leading-relaxed">
                    Video hiện tại chưa có phụ đề. Bấm để AI tự động bóc băng hội thoại tiếng Trung/gốc và dịch chuẩn sang tiếng Việt.
                  </p>
                  <div className="flex gap-2 pt-1">
                    <button
                      onClick={handleStartAutoTranslate}
                      disabled={!selectedVideo || isTranslating}
                      className="flex-1 py-2 bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white font-bold text-xs rounded-lg shadow-md shadow-sky-500/30 flex items-center justify-center gap-1.5 transition active:scale-95 disabled:opacity-40 cursor-pointer"
                    >
                      <Sparkles className="w-3.5 h-3.5" />
                      <span>Kích Hoạt Dịch AI</span>
                    </button>
                    <button
                      onClick={() => srtInputRef.current?.click()}
                      disabled={!selectedVideo}
                      className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-semibold rounded-lg border border-slate-700 transition cursor-pointer"
                      title="Nhập file SRT có sẵn từ máy"
                    >
                      📂 Nhập SRT
                    </button>
                  </div>
                </div>
              ) : (
                <div className="bg-slate-950/80 p-2.5 rounded-xl border border-slate-800 flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-xs text-slate-300">
                    <span className="text-emerald-400 font-bold">✓</span>
                    <span>Đã có <b className="text-white font-mono">{segments.length}</b> câu phụ đề</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={handleStartAutoTranslate}
                      disabled={!selectedVideo || isTranslating}
                      className="px-2 py-1 bg-sky-500/10 hover:bg-sky-500/20 text-sky-400 hover:text-sky-300 rounded border border-sky-500/30 text-[10px] font-bold flex items-center gap-1 transition"
                      title="Dịch lại toàn bộ video bằng AI"
                    >
                      <Sparkles className="w-3 h-3" />
                      <span>Dịch lại</span>
                    </button>
                    <button
                      onClick={() => srtInputRef.current?.click()}
                      disabled={!selectedVideo}
                      className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-[10px] font-semibold border border-slate-700 transition"
                      title="Nạp đè file SRT khác"
                    >
                      📂 Nạp SRT
                    </button>
                  </div>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                  Nội dung câu phụ đề hiện tại:
                </label>
                <textarea
                  rows={2}
                  value={activeSegment ? activeSegment.text : ''}
                  disabled={!activeSegment}
                  placeholder={
                    !selectedVideo 
                      ? "Chưa có video được nạp..." 
                      : segments.length === 0 
                        ? "Chưa có câu phụ đề nào. Nhấn [+ Thêm câu] để tạo mới..." 
                        : "Chọn một câu trên timeline để chỉnh sửa..."
                  }
                  onChange={(e) => updateActiveText(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 focus:border-sky-500 rounded-lg p-2 text-xs text-slate-100 outline-none resize-none disabled:opacity-40 disabled:cursor-not-allowed"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                  Kiểu che phụ đề gốc (Masking):
                </label>
                <div className="grid grid-cols-2 gap-1.5">
                  {[
                    { id: 'solid_black', label: 'Hộp Đen Đặc', icon: 'bg-black border border-white' },
                    { id: 'blur_box', label: 'Kính Mờ (Blur)', icon: 'bg-slate-500/40 backdrop-blur' },
                    { id: 'solid_white', label: 'Hộp Trắng Sang', icon: 'bg-white' },
                    { id: 'classic', label: 'Viền Kinh Điển', icon: 'border-2 border-dashed border-sky-400' },
                  ].map(m => (
                    <button
                      key={m.id}
                      onClick={() => setMaskStyle(m.id)}
                      className={`px-2.5 py-2 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${
                        maskStyle === m.id
                          ? 'bg-slate-800 border-2 border-sky-400 text-white'
                          : 'bg-slate-950 text-slate-400 hover:text-white border border-slate-800'
                      }`}
                    >
                      <span className={`w-3 h-3 rounded ${m.icon}`}></span>
                      <span>{m.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">Font chữ phụ đề:</label>
                <select
                  value={fontFamily}
                  onChange={(e) => setFontFamily(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs text-slate-200 outline-none"
                >
                  <option value="font-bevietnam">Be Vietnam Pro (Chuẩn TikTok Việt)</option>
                  <option value="font-montserrat">Montserrat (Đậm nét sang trọng)</option>
                  <option value="font-oswald">Oswald (Chữ cao, đè sub kín)</option>
                </select>
              </div>

              <div>
                <div className="flex justify-between items-center text-xs mb-1">
                  <span className="font-semibold text-slate-300">Cỡ chữ (Font Size):</span>
                  <span className="font-mono text-sky-400 font-bold">{fontSize} px</span>
                </div>
                <input
                  type="range"
                  min="10"
                  max="32"
                  value={fontSize}
                  onChange={(e) => setFontSize(+e.target.value)}
                  className="w-full accent-sky-500"
                />
              </div>

              <div>
                <div className="flex justify-between items-center text-xs mb-1">
                  <span className="font-semibold text-slate-300">Độ dày viền hộp (Padding):</span>
                  <span className="font-mono text-amber-400 font-bold">{boxPadding} px</span>
                </div>
                <input
                  type="range"
                  min="1"
                  max="25"
                  value={boxPadding}
                  onChange={(e) => setBoxPadding(+e.target.value)}
                  className="w-full accent-amber-500"
                />
              </div>

              <div>
                <div className="flex justify-between items-center text-xs mb-1">
                  <span className="font-semibold text-slate-300">Chiều rộng hộp đè:</span>
                  <span className="font-mono text-purple-400 font-bold">{boxWidth} %</span>
                </div>
                <input
                  type="range"
                  min="50"
                  max="98"
                  value={boxWidth}
                  onChange={(e) => setBoxWidth(+e.target.value)}
                  className="w-full accent-purple-500"
                />
              </div>

              <div>
                <div className="flex justify-between items-center text-xs mb-1">
                  <span className="font-semibold text-slate-300">Vị trí cách đáy (MarginV):</span>
                  <span className="font-mono text-emerald-400 font-bold">{marginV} px</span>
                </div>
                <input
                  type="range"
                  min="5"
                  max="300"
                  value={marginV}
                  onChange={(e) => setMarginV(+e.target.value)}
                  className="w-full accent-emerald-500"
                />
              </div>
            </div>
          )}

          {/* TAB 2: AI VOICE */}
          {activeInspectorTab === 'tab-voice' && (
            <div className="p-4 space-y-4 text-xs">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">Giọng đọc lồng tiếng:</label>
                <select
                  value={selectedVoice}
                  onChange={(e) => setSelectedVoice(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs text-slate-200 outline-none"
                >
                  <option value="vi-VN-HoaiMyNeural">vi-VN-HoaiMyNeural (Nữ miền Bắc truyền cảm)</option>
                  <option value="vi-VN-NamMinhNeural">vi-VN-NamMinhNeural (Nam miền Bắc ấm áp)</option>
                  <option value="VieNeu-TTS">VieNeu-TTS (Giọng AI tự nhiên nhất)</option>
                </select>
              </div>

              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="font-semibold text-slate-300">Tốc độ đọc (Speed):</span>
                  <span className="font-mono text-sky-400">{voiceSpeed}x</span>
                </div>
                <input
                  type="range"
                  min="0.8"
                  max="1.5"
                  step="0.05"
                  value={voiceSpeed}
                  onChange={(e) => setVoiceSpeed(+e.target.value)}
                  className="w-full accent-sky-500"
                />
              </div>

              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="font-semibold text-slate-300">Hòa âm tiếng gốc (Audio Ducking):</span>
                  <span className="font-mono text-emerald-400">{audioDucking}%</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="50"
                  value={audioDucking}
                  onChange={(e) => setAudioDucking(+e.target.value)}
                  className="w-full accent-emerald-500"
                />
              </div>

              <button
                onClick={() => showToast('🔊 Đang phát thử giọng đọc AI câu hiện tại...', 'info')}
                className="w-full py-2 bg-slate-800 hover:bg-slate-700 text-sky-400 border border-sky-500/30 rounded-lg font-bold text-xs flex items-center justify-center gap-1.5 transition active:scale-95"
              >
                <span>🔊</span> Nghe thử giọng câu này
              </button>
            </div>
          )}

          {/* TAB 3: PHÒNG LAB LÁCH BẢN QUYỀN A/B */}
          {activeInspectorTab === 'tab-anti' && (
            <div className="p-4 space-y-4 text-xs">
              <div className="bg-slate-950 p-2.5 rounded-xl border border-slate-800">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-bold text-white flex items-center gap-1.5">
                    <span>💎</span> CÔNG THỨC HOÀNG KIM (A/B)
                  </span>
                  <span className="text-[10px] text-amber-400 font-mono">Tự động Apply</span>
                </div>
                <p className="text-[11px] text-slate-400">Click chọn combo để xem live preview mô phỏng trên video:</p>
              </div>

              <div className="space-y-2">
                {[
                  {
                    id: 'stealth',
                    name: '💎 Combo 1: Tàng Hình Tinh Tế',
                    tag: 'Khuyên Dùng',
                    tagBg: 'bg-emerald-500/20 text-emerald-300',
                    desc: 'Cắt vi mô 1.5% + Lanczos + Mesh Grid 7% + Film Grain mịn (Luma 6) + Bão hòa +4%.',
                    suit: 'Phù hợp: Gái xinh, Dance, Mỹ phẩm (Mặt vẫn mịn đẹp)'
                  },
                  {
                    id: 'cinema',
                    name: '🎬 Combo 2: Điện Ảnh Cổ Điển',
                    tag: 'Tone Ấm',
                    tagBg: 'bg-amber-500/20 text-amber-300',
                    desc: 'Quầng tối Vignette 4 góc + Tone ấm điện ảnh + Hạt Film Grain 35mm + Gai nét viền Unsharp.',
                    suit: 'Phù hợp: Review phim, Podcast, Phỏng vấn, Đời sống'
                  },
                  {
                    id: 'crt',
                    name: '📺 Combo 3: Màn Hình TV CRT',
                    tag: 'Sọc Ngang',
                    tagBg: 'bg-purple-500/20 text-purple-300',
                    desc: 'Lưới sọc ngang CRT 3px (mờ 14%) + Lệch quang sai màu RGB 2px + Hạt nhiễu Luma 9.',
                    suit: 'Phù hợp: Tin tức, Hài hước, Meme, Tech review'
                  },
                  {
                    id: 'fortress',
                    name: '🏰 Combo 4: Pháo Đài Cực Hạn',
                    tag: 'Cực Hạn',
                    tagBg: 'bg-rose-500/20 text-rose-300',
                    desc: 'Crop 1.5% + Lanczos + Mesh + Lệch RGB + Grain + Tăng tốc vi mô 1.025x + Pitch âm thanh.',
                    suit: 'Phù hợp: Show truyền hình, VTV, Game show bản quyền mạnh'
                  }
                ].map(c => (
                  <div
                    key={c.id}
                    onClick={() => setActiveCombo(c.id)}
                    className={`p-2.5 rounded-xl cursor-pointer transition ${
                      activeCombo === c.id
                        ? 'border-2 border-sky-400 bg-sky-500/15 shadow-md'
                        : 'border border-slate-700 bg-slate-950/80 hover:border-slate-500'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-xs text-white">{c.name}</span>
                      <span className={`text-[10px] px-1.5 py-0.2 rounded font-semibold ${c.tagBg}`}>{c.tag}</span>
                    </div>
                    <p className="text-[11px] text-slate-300 mt-1">{c.desc}</p>
                    <div className="text-[10px] text-sky-400 font-mono mt-1">{c.suit}</div>
                  </div>
                ))}
              </div>

              <div className="border-t border-slate-800 pt-3 space-y-2">
                <span className="block text-xs font-semibold text-slate-300">Tùy biến lớp phủ (Custom Layering):</span>
                <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={pitchShift}
                    onChange={(e) => setPitchShift(e.target.checked)}
                    className="rounded bg-slate-800 text-sky-500"
                  />
                  <span>Acoustic Pitch Shift (+2.5% âm thanh gốc)</span>
                </label>

                <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={watermarkEnabled}
                    onChange={(e) => setWatermarkEnabled(e.target.checked)}
                    className="rounded bg-slate-800 text-sky-500"
                  />
                  <span>Đóng dấu Watermark Logo thương hiệu</span>
                </label>

                {watermarkEnabled && (
                  <div className="space-y-2 pt-1">
                    <input
                      type="file"
                      ref={logoInputRef}
                      accept="image/png,image/jpeg,image/webp"
                      onChange={handleLogoFileChange}
                      className="hidden"
                    />

                    {watermarkLogoUrl ? (
                      <div className="bg-slate-950/80 border border-emerald-500/30 rounded-lg p-2.5 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[11px] font-semibold text-emerald-400 flex items-center gap-1">
                            <Check className="w-3.5 h-3.5 text-emerald-400" />
                            Đã lưu Logo thương hiệu vĩnh viễn
                          </span>
                          <span className="text-[9px] bg-emerald-500/10 text-emerald-300 px-1.5 py-0.5 rounded border border-emerald-500/20 font-mono">
                            Tự động cho mọi video
                          </span>
                        </div>

                        <div className="flex items-center gap-3 bg-slate-900/90 p-2 rounded border border-slate-800">
                          <div className="w-12 h-12 bg-slate-950 rounded flex items-center justify-center border border-slate-700 overflow-hidden shrink-0 p-1">
                            <img src={watermarkLogoUrl} alt="Logo" className="max-w-full max-h-full object-contain" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="text-xs text-slate-200 font-mono truncate">{watermarkFilename || 'watermark_logo.png'}</div>
                            <div className="text-[10px] text-slate-400">Góc trên phải (Top-Right) Canvas</div>
                          </div>
                        </div>

                        <div className="flex items-center gap-2 pt-1">
                          <button
                            type="button"
                            onClick={() => logoInputRef.current?.click()}
                            className="flex-1 py-1.5 px-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-[11px] font-medium rounded border border-slate-700 transition flex items-center justify-center gap-1.5"
                          >
                            <Upload className="w-3 h-3 text-sky-400" />
                            <span>Đổi file khác</span>
                          </button>
                          <button
                            type="button"
                            onClick={handleRemoveLogo}
                            className="py-1.5 px-2.5 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-[11px] font-medium rounded border border-rose-500/30 transition flex items-center justify-center gap-1"
                            title="Gỡ bỏ logo ảnh"
                          >
                            <Trash2 className="w-3 h-3" />
                            <span>Gỡ</span>
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        <button
                          type="button"
                          onClick={() => logoInputRef.current?.click()}
                          className="w-full py-3 px-3 bg-sky-500/10 hover:bg-sky-500/20 border-2 border-dashed border-sky-500/40 hover:border-sky-400 rounded-lg text-left transition group flex items-center gap-3 cursor-pointer"
                        >
                          <div className="w-10 h-10 rounded-lg bg-sky-500/20 text-sky-400 flex items-center justify-center shrink-0 group-hover:scale-105 transition">
                            <Upload className="w-5 h-5" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="text-xs font-bold text-sky-300 group-hover:text-sky-200 flex items-center gap-1">
                              <span>Chọn file ảnh Logo (PNG / JPG)</span>
                            </div>
                            <div className="text-[10px] text-slate-400">
                              Chọn 1 lần duy nhất • Hệ thống tự lưu vĩnh viễn cho tất cả video
                            </div>
                          </div>
                        </button>

                        <div className="pt-1">
                          <span className="text-[10px] text-slate-400 block mb-1">Hoặc dùng Watermark dạng chữ (Text):</span>
                          <input
                            type="text"
                            value={watermarkText}
                            onChange={(e) => {
                              setWatermarkText(e.target.value);
                              setWatermarkType('text');
                            }}
                            placeholder="Nhập tên kênh / text..."
                            className="w-full bg-slate-950 border border-slate-800 rounded p-1.5 text-xs text-slate-200 outline-none font-mono"
                          />
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Bottom Export Button */}
          <div className="p-4 border-t border-slate-800 mt-auto bg-slate-950/90 space-y-2">
            <div className="text-[11px] text-slate-400 flex items-center justify-between">
              <span>Xuất vào subfolder:</span>
              <span className="font-mono text-emerald-400 font-bold">ready_to_upload/{selectedVideo?.subfolder || '--'}/</span>
            </div>
            <button
              onClick={startExportNVENC}
              className="w-full py-3 bg-gradient-to-r from-sky-500 via-indigo-600 to-emerald-500 hover:opacity-95 text-white font-extrabold text-sm rounded-xl shadow-lg shadow-sky-500/25 transition active:scale-95 flex items-center justify-center gap-2"
            >
              <span>🚀</span>
              <span>XUẤT VIDEO DỊCH & SUB (3S NVENC)</span>
            </button>
            <p className="text-[10px] text-center text-slate-400 font-mono">Lưu đúng subfolder kênh • RTX 3060 NVENC</p>
          </div>
        </aside>

      </div>

      {/* 3. CAPCUT-STYLE TIMELINE & CONTROLS (EXACT MOCKUP) */}
      <div className="h-56 bg-[#0f1422] border-t border-slate-800/90 flex flex-col shrink-0 select-none">
        
        {/* TOOLBAR ROW */}
        <div className="h-10 bg-[#141b2d] px-4 flex items-center justify-between border-b border-slate-800 text-xs">
          
          {/* Subtitle Tools */}
          <div className="flex items-center gap-1.5">
            {/* AI Auto-Translate & SRT Import */}
            <button
              onClick={handleStartAutoTranslate}
              disabled={!selectedVideo || isTranslating}
              className="flex items-center gap-1.5 px-3 py-1 bg-gradient-to-r from-sky-600 via-indigo-600 to-purple-600 hover:from-sky-500 hover:to-indigo-500 text-white font-bold rounded-md shadow-sm shadow-sky-500/30 transition active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              title="Tự động bóc băng Whisper CUDA và dịch Gemini sang tiếng Việt"
            >
              <Sparkles className="w-3.5 h-3.5 text-amber-300 animate-pulse" />
              <span className="font-extrabold text-[11px]">Dịch AI</span>
            </button>

            <button
              onClick={() => srtInputRef.current?.click()}
              disabled={!selectedVideo}
              className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-800/90 hover:bg-slate-700 text-slate-300 hover:text-white rounded-md border border-slate-700 transition active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
              title="Nhập file .SRT từ máy tính"
            >
              <span>📂</span>
              <span className="font-medium text-[11px]">Nhập SRT</span>
            </button>

            <div className="w-px h-4 bg-slate-800 mx-0.5"></div>

            <button
              onClick={splitCurrentSegment}
              disabled={!activeSegment}
              className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-800/90 hover:bg-slate-700 text-slate-200 hover:text-[#00f2fe] rounded-md border border-slate-700 transition active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <span>✂️</span>
              <span className="font-medium text-[11px]">Tách câu</span>
            </button>

            <button
              onClick={addNewSegment}
              disabled={!selectedVideo}
              className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-800/90 hover:bg-slate-700 text-slate-200 hover:text-emerald-400 rounded-md border border-slate-700 transition active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <span>➕</span>
              <span className="font-medium text-[11px]">Thêm câu</span>
            </button>

            <button
              onClick={deleteActiveSegment}
              disabled={!activeSegment}
              className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-800/90 hover:bg-slate-700 text-slate-200 hover:text-rose-400 rounded-md border border-slate-700 transition active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed"
              title="Xóa câu phụ đề đang chọn"
            >
              <span>🗑️</span>
              <span className="font-medium text-[11px]">Xóa câu</span>
            </button>

            <button
              onClick={clearAllSegments}
              disabled={segments.length === 0}
              className="flex items-center gap-1.5 px-2 py-1 bg-slate-800/90 hover:bg-rose-950/60 text-slate-400 hover:text-rose-300 rounded-md border border-slate-700 transition active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed"
              title="Xóa sạch toàn bộ phụ đề"
            >
              <span>🧹</span>
              <span className="font-medium text-[11px]">Xóa tất cả</span>
            </button>

            <div className="w-px h-4 bg-slate-800 mx-1"></div>

            {/* Audio Mute Toggle */}
            <button
              onClick={toggleMute}
              className={`flex items-center gap-1.5 px-2 py-1 rounded-md border text-[11px] transition ${
                isOrigMuted
                  ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                  : 'bg-slate-800/50 hover:bg-slate-800 text-slate-300 border-slate-700/80'
              }`}
            >
              <span>{isOrigMuted ? '🔇' : '🔊'}</span>
              <span>{isOrigMuted ? 'Tiếng gốc: Tắt' : 'Tiếng gốc: Bật'}</span>
            </button>
          </div>

          {/* CENTER PLAYBACK CONTROLS */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => seekTo(0)}
              className="text-slate-400 hover:text-white text-xs p-1"
              title="Về đầu video"
            >
              ⏮
            </button>
            <button
              onClick={togglePlayPause}
              className="w-7 h-7 rounded-full bg-white hover:bg-slate-200 text-slate-950 font-black flex items-center justify-center shadow-lg transition active:scale-95"
              title={isPlaying ? 'Tạm dừng (Space)' : 'Phát (Space)'}
            >
              {isPlaying ? '⏸' : '▶'}
            </button>
            <button
              onClick={() => seekTo(totalSeconds)}
              className="text-slate-400 hover:text-white text-xs p-1"
              title="Đến cuối video"
            >
              ⏭
            </button>
            
            <div className="font-mono text-xs flex items-center gap-1 bg-slate-950 px-2 py-1 rounded border border-slate-800">
              <span className="text-[#00f2fe] font-bold">{formatTimecode(currentSeconds)}</span>
              <span className="text-slate-600">/</span>
              <span className="text-slate-400">{formatTimecode(totalSeconds)}</span>
            </div>
          </div>

          {/* RIGHT ZOOM & MAGNET */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setMagnetEnabled(!magnetEnabled)}
              className={`flex items-center gap-1 px-2 py-1 rounded border text-[11px] ${
                magnetEnabled
                  ? 'bg-sky-500/20 text-[#00f2fe] border-sky-500/30'
                  : 'bg-slate-800 text-slate-500 border-slate-700'
              }`}
            >
              <span>🧲</span>
              <span className="hidden sm:inline">Từ tính</span>
            </button>
            
            <div className="flex items-center gap-1 bg-slate-900 px-2 py-1 rounded-lg border border-slate-800">
              <button
                onClick={() => setZoomLevel(Math.max(100, zoomLevel - 20))}
                className="text-slate-400 hover:text-white font-bold text-xs px-1"
              >
                −
              </button>
              <input
                type="range"
                min="100"
                max="250"
                value={zoomLevel}
                onChange={(e) => setZoomLevel(+e.target.value)}
                className="w-16 accent-sky-400"
              />
              <button
                onClick={() => setZoomLevel(Math.min(250, zoomLevel + 20))}
                className="text-slate-400 hover:text-white font-bold text-xs px-1"
              >
                +
              </button>
              <span className="font-mono text-[10px] text-slate-400 w-8 text-right">{zoomLevel}%</span>
            </div>

            <button
              onClick={() => setZoomLevel(100)}
              className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-white text-xs"
            >
              ⛶ Fit
            </button>
          </div>

        </div>

        {/* TIMELINE TRACKS AREA */}
        <div className="flex-1 overflow-x-auto overflow-y-hidden relative flex">
          
          {/* Left Column Track Headers (Fixed width 96px) */}
          <div className="w-24 bg-[#111827] border-r border-slate-800 shrink-0 flex flex-col z-30 shadow-lg">
            <div className="h-6 border-b border-slate-800 flex items-center px-2 text-[10px] text-slate-400 font-mono">
              THỜI GIAN
            </div>
            <div className="h-10 border-b border-slate-800/80 px-2 flex items-center justify-between text-[11px] text-slate-300 bg-slate-900/60">
              <span className="flex items-center gap-1 font-semibold text-sky-400">💬 Sub AI</span>
              <span className="text-[9px] bg-sky-500/20 px-1 py-0.2 rounded text-sky-300">VI</span>
            </div>
            <div className="h-20 px-2 flex flex-col justify-center text-[11px] text-slate-400 gap-1 bg-slate-900/40">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1 font-semibold text-slate-300">🎬 Video</span>
                <span className="text-[9px] text-slate-500 font-mono">1080p</span>
              </div>
              <span className="text-[9px] text-emerald-400 font-mono flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span> 9:16 Dọc
              </span>
            </div>
          </div>

          {/* Right Scrollable Tracks Wrapper */}
          <div
            ref={tracksWrapperRef}
            onMouseDown={handleTimelineMouseDown}
            style={{ width: `${zoomLevel}%`, minWidth: '800px' }}
            className="relative flex-1 bg-[#090d16] flex flex-col cursor-pointer select-none"
          >
            
            {/* Time Ruler with Major & Minor ticks */}
            <div className="h-6 bg-[#0f1424] border-b border-slate-800 relative overflow-hidden pointer-events-none">
              <div className="ruler-tick-major" style={{ left: '0%' }}>
                <span className="absolute -top-3.5 -left-2 text-[9px] font-mono text-slate-400">00:00</span>
              </div>
              <div className="ruler-tick-minor" style={{ left: '6.66%' }}></div>
              <div className="ruler-tick-minor" style={{ left: '13.33%' }}></div>
              <div className="ruler-tick-major" style={{ left: '20%' }}>
                <span className="absolute -top-3.5 -left-2 text-[9px] font-mono text-slate-400">00:03</span>
              </div>
              <div className="ruler-tick-minor" style={{ left: '26.66%' }}></div>
              <div className="ruler-tick-minor" style={{ left: '33.33%' }}></div>
              <div className="ruler-tick-major" style={{ left: '40%' }}>
                <span className="absolute -top-3.5 -left-2 text-[9px] font-mono text-slate-400">00:06</span>
              </div>
              <div className="ruler-tick-minor" style={{ left: '46.66%' }}></div>
              <div className="ruler-tick-minor" style={{ left: '53.33%' }}></div>
              <div className="ruler-tick-major" style={{ left: '60%' }}>
                <span className="absolute -top-3.5 -left-2 text-[9px] font-mono text-slate-400">00:09</span>
              </div>
              <div className="ruler-tick-minor" style={{ left: '66.66%' }}></div>
              <div className="ruler-tick-minor" style={{ left: '73.33%' }}></div>
              <div className="ruler-tick-major" style={{ left: '80%' }}>
                <span className="absolute -top-3.5 -left-2 text-[9px] font-mono text-slate-400">00:12</span>
              </div>
              <div className="ruler-tick-minor" style={{ left: '86.66%' }}></div>
              <div className="ruler-tick-minor" style={{ left: '93.33%' }}></div>
              <div className="ruler-tick-major" style={{ left: '100%' }}>
                <span className="absolute -top-3.5 -left-4 text-[9px] font-mono text-slate-400">00:15</span>
              </div>
            </div>

            {/* CapCut Playhead Needle */}
            <div
              style={{ left: `${playheadPercent}%` }}
              className="absolute top-0 bottom-0 z-40 flex flex-col items-center pointer-events-none transition-all duration-75"
            >
              <div className="capcut-needle-head pointer-events-auto"></div>
              <div className="capcut-needle-line flex-1"></div>
            </div>

            {/* Subtitle Track */}
            <div className="h-10 border-b border-slate-800/80 bg-slate-950/40 relative px-1 py-1 flex items-center">
              {segments.length === 0 ? (
                selectedVideo ? (
                  <div className="absolute inset-0 flex items-center justify-between px-3 bg-gradient-to-r from-sky-950/80 via-slate-900/90 to-indigo-950/80 border border-dashed border-sky-500/40 rounded-lg z-20">
                    <div className="flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-amber-300 animate-pulse" />
                      <div className="text-left">
                        <span className="text-[11px] font-bold text-sky-200">Video này chưa có phụ đề tiếng Việt</span>
                        <span className="text-[10px] text-slate-400 ml-2 hidden md:inline">• Bấm để Whisper CUDA bóc băng & Gemini dịch chuẩn</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 pointer-events-auto">
                      <button
                        onClick={handleStartAutoTranslate}
                        disabled={isTranslating}
                        className="px-2.5 py-1 bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white font-bold text-[11px] rounded-md shadow-md flex items-center gap-1 transition active:scale-95 cursor-pointer"
                      >
                        <Sparkles className="w-3 h-3 text-amber-300" />
                        <span>Kích Hoạt Dịch AI</span>
                      </button>
                      <button
                        onClick={() => srtInputRef.current?.click()}
                        className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-[11px] font-medium rounded-md border border-slate-700 transition cursor-pointer"
                        title="Nạp file .SRT có sẵn từ máy"
                      >
                        📂 Nhập SRT
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="absolute inset-0 flex items-center justify-center text-[10px] text-slate-500 italic pointer-events-none">
                    Chưa có video được nạp • Vui lòng chọn video để bắt đầu dịch & biên tập
                  </div>
                )
              ) : (
                segments.map(seg => {
                  const isAct = seg.id === activeSegmentId;
                  const leftPct = totalSeconds > 0 ? (seg.start / totalSeconds) * 100 : 0;
                  const widthPct = totalSeconds > 0 ? ((seg.end - seg.start) / totalSeconds) * 100 : 10;

                  return (
                    <div
                      key={seg.id}
                      onClick={(e) => {
                        e.stopPropagation();
                        setActiveSegmentId(seg.id);
                        seekTo(seg.start);
                      }}
                      style={{ left: `${leftPct}%`, width: `${Math.max(widthPct, 6)}%` }}
                      className={`absolute h-8 rounded-lg cursor-pointer transition flex items-center justify-between px-2 text-[10px] truncate ${
                        isAct
                          ? 'bg-gradient-to-r from-sky-500 to-blue-600 text-white font-bold border-2 border-white shadow-md'
                          : 'bg-slate-800/90 text-slate-300 hover:bg-slate-700/90 border border-slate-700'
                      }`}
                    >
                      <span className="truncate">{seg.text}</span>
                    </div>
                  );
                })
              )}
            </div>

            {/* Video Clip Strip (16 Frame Filmstrip + Audio Waveform) */}
            <div className="h-20 bg-slate-950/80 relative px-1 py-1.5 flex items-center">
              {selectedVideo ? (
                <div className="w-full h-full rounded-lg overflow-hidden relative clip-active flex flex-col justify-between cursor-pointer select-none">
                  
                  {/* Clip Title */}
                  <div className="h-4 bg-slate-900/90 border-b border-sky-500/40 px-2 flex items-center justify-between text-[9px] text-slate-300 z-10 backdrop-blur">
                    <span className="font-semibold text-white flex items-center gap-1 truncate">
                      <span>🎬</span> {selectedVideo.filename}
                    </span>
                    <span className="font-mono text-[#00f2fe]">{formatTimecode(totalSeconds)}</span>
                  </div>

                  {/* 16 Consecutive Frame Thumbnails + Audio Waveform overlay */}
                  <div className="flex-1 flex overflow-hidden bg-slate-900 relative">
                    <div className="flex w-full h-full">
                      {timelineFrames.length > 0 ? (
                        timelineFrames.map((f, idx) => (
                          <div
                            key={idx}
                            style={{ backgroundImage: `url(${f.data_url || previewFrameUrl})` }}
                            className="h-full flex-1 shrink-0 border-r border-black/40 overflow-hidden film-frame opacity-85 hover:opacity-100 transition relative group/frame"
                            title={`Khung hình ${idx + 1}/${timelineFrames.length} (${f.timestamp}s)`}
                          >
                            <span className="absolute bottom-0.5 left-0.5 bg-black/80 text-[8px] font-mono text-slate-300 px-0.5 rounded opacity-0 group-hover/frame:opacity-100 transition">
                              {f.timestamp}s
                            </span>
                          </div>
                        ))
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-[10px] text-slate-500 italic bg-slate-950/60">
                          Đang tải khung hình filmstrip...
                        </div>
                      )}
                    </div>

                    {/* Audio Waveform SVG Overlay */}
                    <div className="absolute bottom-0 left-0 right-0 h-4 pointer-events-none opacity-60">
                      <svg className="w-full h-full stroke-cyan-400 fill-none opacity-80" viewBox="0 0 1000 100" preserveAspectRatio="none">
                        <path d="M0,50 Q25,20 50,50 T100,50 T150,10 T200,50 T250,90 T300,50 T350,30 T400,50 T450,80 T500,50 T550,20 T600,50 T650,70 T700,50 T750,15 T800,50 T850,85 T900,50 T950,30 T1000,50" strokeWidth="2.5" />
                      </svg>
                    </div>
                  </div>

                  {/* Left & Right Cyan Resize Handles */}
                  <div className="absolute top-0 bottom-0 left-0 w-2.5 bg-[#00f2fe] flex items-center justify-center cursor-ew-resize rounded-l z-20">
                    <div className="w-0.5 h-3 bg-slate-950 rounded"></div>
                  </div>
                  <div className="absolute top-0 bottom-0 right-0 w-2.5 bg-[#00f2fe] flex items-center justify-center cursor-ew-resize rounded-r z-20">
                    <div className="w-0.5 h-3 bg-slate-950 rounded"></div>
                  </div>
                </div>
              ) : (
                <div className="w-full h-full rounded-lg border border-dashed border-slate-800 flex items-center justify-center text-xs text-slate-600 italic">
                  Chưa có video được nạp vào dòng thời gian
                </div>
              )}
            </div>

          </div>

        </div>

      </div>

      {/* 4. EXPORT PROGRESS MODAL */}
      {isExporting && (
        <div className="fixed inset-0 bg-black/85 backdrop-blur-md z-50 flex items-center justify-center animate-in fade-in duration-200">
          <div className="w-[520px] bg-slate-900 border border-slate-700 rounded-2xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-extrabold text-base text-white flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-emerald-400" /> Tiến Trình Render NVENC
              </h3>
              <span className="font-mono text-sm font-bold text-emerald-400">{exportProgress}%</span>
            </div>

            {/* Progress bar */}
            <div className="w-full h-3 bg-slate-950 rounded-full overflow-hidden border border-slate-800">
              <div
                style={{ width: `${exportProgress}%` }}
                className="h-full bg-gradient-to-r from-emerald-500 to-sky-400 transition-all duration-300 rounded-full"
              />
            </div>

            {exportError ? (
              <div className="bg-rose-950/60 p-3 rounded-xl border border-rose-800/80 text-xs font-mono text-rose-300 space-y-1">
                <p className="font-bold">❌ Gặp sự cố khi render:</p>
                <p>{exportError}</p>
              </div>
            ) : (
              <div className="bg-slate-950 p-3 rounded-xl border border-slate-800 text-xs font-mono text-slate-300 space-y-1.5">
                <p>• GPU Target: NVIDIA RTX 3060 12GB (h264_nvenc)</p>
                <p>• Chế độ: <span className="text-sky-300">{workflowMode === 'remix' ? 'Chỉ Lách BQ (Siêu tốc ~2s)' : 'Dịch & Đè Sub tiếng Việt'}</span></p>
                <p>• Thư mục đích: <span className="text-emerald-300">output/ready_to_upload/{selectedVideo?.subfolder || 'general_inbox'}/</span></p>
                {exportedResult && (
                  <p className="text-emerald-400 font-bold pt-1">✓ File thành phẩm: {exportedResult.filename}</p>
                )}
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                onClick={() => setIsExporting(false)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl font-semibold text-xs transition"
              >
                Đóng
              </button>
              {exportedResult && (
                <>
                  <button
                    onClick={() => api.openFolder(exportedResult.output_dir)}
                    className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-sky-300 border border-sky-500/40 font-semibold rounded-xl text-xs flex items-center gap-1.5 transition active:scale-95"
                  >
                    <span>📁</span> Mở Thư Mục Chứa
                  </button>
                  <button
                    onClick={() => {
                      setIsExporting(false);
                      onGoToPublishing();
                    }}
                    className="px-5 py-2 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold rounded-xl shadow-lg shadow-emerald-500/20 text-xs flex items-center gap-1.5 transition active:scale-95"
                  >
                    <span>Chuyển Sang Màn Hình Phân Phối</span> <ArrowRight className="w-4 h-4" />
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 5. AI TRANSLATE PROGRESS MODAL */}
      {isTranslating && (
        <div className="fixed inset-0 bg-black/85 backdrop-blur-md z-50 flex items-center justify-center animate-in fade-in duration-200">
          <div className="w-[540px] bg-slate-900 border border-slate-700 rounded-2xl p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-extrabold text-base text-white flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-sky-400 animate-pulse" /> Chu Trình Dịch Thuật AI Tự Động
              </h3>
              <span className="font-mono text-sm font-bold text-sky-400">{translateProgress}%</span>
            </div>

            {/* 3-Step Visual Badges */}
            <div className="grid grid-cols-3 gap-2 py-1">
              <div className={`p-2.5 rounded-xl border text-center transition ${
                translateStep === 1 
                  ? 'bg-sky-500/20 border-sky-400 text-sky-300 ring-1 ring-sky-400' 
                  : translateStep > 1 
                    ? 'bg-slate-800/80 border-emerald-500/50 text-emerald-400' 
                    : 'bg-slate-950/60 border-slate-800 text-slate-500'
              }`}>
                <div className="text-base mb-1">{translateStep > 1 ? '✓' : '🎵'}</div>
                <div className="text-[11px] font-bold">1. Tách Audio</div>
                <div className="text-[9px] text-slate-400">WAV PCM 16kHz</div>
              </div>

              <div className={`p-2.5 rounded-xl border text-center transition ${
                translateStep === 2 
                  ? 'bg-sky-500/20 border-sky-400 text-sky-300 ring-1 ring-sky-400' 
                  : translateStep > 2 
                    ? 'bg-slate-800/80 border-emerald-500/50 text-emerald-400' 
                    : 'bg-slate-950/60 border-slate-800 text-slate-500'
              }`}>
                <div className="text-base mb-1">{translateStep > 2 ? '✓' : '🎙️'}</div>
                <div className="text-[11px] font-bold">2. Bóc Băng</div>
                <div className="text-[9px] text-slate-400">Whisper CUDA</div>
              </div>

              <div className={`p-2.5 rounded-xl border text-center transition ${
                translateStep === 3 && translateProgress < 100
                  ? 'bg-sky-500/20 border-sky-400 text-sky-300 ring-1 ring-sky-400' 
                  : translateProgress === 100 
                    ? 'bg-slate-800/80 border-emerald-500/50 text-emerald-400' 
                    : 'bg-slate-950/60 border-slate-800 text-slate-500'
              }`}>
                <div className="text-base mb-1">{translateProgress === 100 ? '✓' : '🌐'}</div>
                <div className="text-[11px] font-bold">3. Dịch Ngữ Nghĩa</div>
                <div className="text-[9px] text-slate-400">Gemini Flash</div>
              </div>
            </div>

            {/* Progress bar */}
            <div className="w-full h-3 bg-slate-950 rounded-full overflow-hidden border border-slate-800">
              <div
                style={{ width: `${translateProgress}%` }}
                className="h-full bg-gradient-to-r from-sky-500 via-indigo-500 to-emerald-400 transition-all duration-300 rounded-full"
              />
            </div>

            {translateError ? (
              <div className="bg-rose-950/60 p-3 rounded-xl border border-rose-800/80 text-xs font-mono text-rose-300 space-y-1">
                <p className="font-bold">❌ Gặp sự cố trong quá trình dịch AI:</p>
                <p>{translateError}</p>
              </div>
            ) : (
              <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-800 text-xs font-mono text-slate-300 space-y-1.5">
                <p className="text-sky-300 flex items-center gap-2">
                  <span className="inline-block w-2 h-2 rounded-full bg-sky-400 animate-ping"></span>
                  <span>{translateMessage || 'Đang thực thi chu trình dịch thuật...'}</span>
                </p>
                <p className="text-slate-400">• Video: <span className="text-white font-semibold">{selectedVideo?.filename}</span></p>
                <p className="text-slate-400">• Tệp phụ đề đầu ra: <span className="text-emerald-400 font-semibold">{selectedVideo?.filename?.replace(/\.[^/.]+$/, "")}_vi.srt</span></p>
                {translateSuccessData && (
                  <p className="text-emerald-400 font-bold pt-1 border-t border-slate-800/80 mt-1">
                    🎉 Hoàn tất: Đã dịch {translateSuccessData.count || 0} câu phụ đề chuẩn xác!
                  </p>
                )}
              </div>
            )}

            <div className="flex items-center justify-end gap-2 pt-2">
              {translateProgress < 100 && !translateError ? (
                <span className="text-xs text-slate-400 mr-auto flex items-center gap-1.5 font-mono">
                  <span className="animate-spin text-sky-400">⏳</span> Vui lòng chờ trong giây lát...
                </span>
              ) : null}

              {translateError && (
                <button
                  onClick={() => setIsTranslating(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl font-semibold text-xs transition"
                >
                  Đóng
                </button>
              )}

              {translateProgress === 100 && (
                <button
                  onClick={() => setIsTranslating(false)}
                  className="px-5 py-2.5 bg-gradient-to-r from-emerald-500 to-sky-500 hover:opacity-95 text-slate-950 font-extrabold rounded-xl shadow-lg shadow-emerald-500/20 text-xs flex items-center gap-1.5 transition active:scale-95"
                >
                  <span>✓</span> Bắt Đầu Biên Tập Ngay
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Hidden input for SRT import */}
      <input
        ref={srtInputRef}
        type="file"
        accept=".srt"
        onChange={handleImportSrt}
        className="hidden"
      />

    </div>
  );
}
