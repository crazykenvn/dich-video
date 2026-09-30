import React from 'react';
import { Film, FolderGit2, Share2, Cpu, CheckCircle2 } from 'lucide-react';

export default function Header({ activeScreen, setActiveScreen, cudaReady }) {
  const screens = [
    { id: 'ingestion', label: '1. Dữ Liệu Nguồn', icon: FolderGit2 },
    { id: 'studio', label: '2. Studio Biên Tập', icon: Film },
    { id: 'publishing', label: '3. Quản Lý Phân Phối', icon: Share2 },
  ];

  return (
    <header className="h-14 bg-slate-950/90 border-b border-slate-800/80 px-4 flex items-center justify-between z-30 shrink-0 backdrop-blur-md">
      {/* Brand & Hardware specs */}
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-sky-400 to-indigo-600 flex items-center justify-center shadow-lg shadow-sky-500/20">
          <Film className="w-4 h-4 text-slate-950 stroke-[2.5]" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="font-extrabold text-sm tracking-wide text-white font-display">
              CREATOR STUDIO <span className="bg-gradient-to-r from-sky-400 to-cyan-300 bg-clip-text text-transparent">PRO</span>
            </h1>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-sky-500/10 text-sky-400 border border-sky-500/30">
              v2.0
            </span>
          </div>
          <div className="flex items-center gap-1.5 text-[10px] text-slate-400 font-mono">
            <Cpu className="w-3 h-3 text-emerald-400" />
            <span>RTX 3060 12GB NVENC</span>
            <span className="text-slate-600">•</span>
            <span className="text-emerald-400 flex items-center gap-0.5">
              <CheckCircle2 className="w-2.5 h-2.5" /> 60fps Real-time
            </span>
          </div>
        </div>
      </div>

      {/* Navigation tabs */}
      <nav className="flex items-center gap-1 bg-slate-900/90 p-1 rounded-xl border border-slate-800">
        {screens.map(tab => {
          const Icon = tab.icon;
          const isActive = activeScreen === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveScreen(tab.id)}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                isActive
                  ? 'bg-gradient-to-r from-sky-500 to-blue-600 text-white shadow-md shadow-sky-500/20'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </nav>

      {/* Status indicator */}
      <div className="flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
        <span className="text-xs font-mono text-emerald-400 font-semibold">FastAPI Connected</span>
      </div>
    </header>
  );
}
