import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import IngestionScreen from './components/IngestionScreen';
import StudioScreen from './components/StudioScreen';
import PublishingScreen from './components/PublishingScreen';
import Toast from './components/Toast';
import * as api from './services/api';

export default function App() {
  const [activeScreen, setActiveScreen] = useState('ingestion');
  const [workflowMode, setWorkflowMode] = useState('translate');
  const [selectedVideo, setSelectedVideo] = useState(null);
  const [cudaReady, setCudaReady] = useState(false);
  const [toasts, setToasts] = useState([]);

  useEffect(() => {
    // Kiểm tra health check backend lúc mở app
    api.getHealth().then(res => {
      if (res) {
        setCudaReady(res.cuda_ready);
        showToast('✓ Đã kết nối FastAPI Backend thành công (NVENC GPU Ready)', 'success');
      }
    });

    // Tự động nạp video đầu tiên nếu có để Studio sẵn sàng ngay lập tức
    api.getVideos('all', 'all').then(vids => {
      if (vids && vids.length > 0 && !selectedVideo) {
        setSelectedVideo(vids[0]);
      }
    });
  }, []);

  const showToast = (message, type = 'info') => {
    const id = Date.now() + Math.random();
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => {
      removeToast(id);
    }, 4500);
  };

  const removeToast = (id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  const handleSelectVideo = (video, mode) => {
    setSelectedVideo(video);
    setWorkflowMode(mode);
    setActiveScreen('studio');
    showToast(`✓ Đã nạp video <b>${video.filename}</b> vào Studio [Chế độ: ${mode === 'translate' ? 'Dịch Sub' : 'Chỉ Lách BQ'}]`, 'success');
  };

  return (
    <div className="h-screen w-screen flex flex-col bg-[#0b0f17] text-slate-100 overflow-hidden font-sans">
      <Header 
        activeScreen={activeScreen} 
        setActiveScreen={setActiveScreen} 
        cudaReady={cudaReady} 
      />

      <main className="flex-1 flex overflow-hidden">
        {activeScreen === 'ingestion' && (
          <IngestionScreen 
            onSelectVideo={handleSelectVideo} 
            showToast={showToast} 
          />
        )}

        {activeScreen === 'studio' && (
          <StudioScreen 
            selectedVideo={selectedVideo} 
            workflowMode={workflowMode} 
            setWorkflowMode={setWorkflowMode} 
            onGoToPublishing={() => setActiveScreen('publishing')} 
            showToast={showToast} 
          />
        )}

        {activeScreen === 'publishing' && (
          <PublishingScreen 
            showToast={showToast} 
          />
        )}
      </main>

      <Toast toasts={toasts} removeToast={removeToast} />
    </div>
  );
}
