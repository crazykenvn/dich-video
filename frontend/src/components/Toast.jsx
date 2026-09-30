import React from 'react';
import { CheckCircle2, AlertCircle, Info, X } from 'lucide-react';

export default function Toast({ toasts, removeToast }) {
  if (!toasts || toasts.length === 0) return null;

  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 pointer-events-none max-w-sm">
      {toasts.map(t => {
        const isSuccess = t.type === 'success';
        const isWarning = t.type === 'warning';
        const isError = t.type === 'error';

        return (
          <div
            key={t.id}
            className={`pointer-events-auto p-3 rounded-xl border shadow-xl flex items-start gap-2.5 text-xs transition-all animate-in slide-in-from-bottom-2 ${
              isSuccess
                ? 'bg-slate-900 border-emerald-500/50 text-emerald-200'
                : isWarning
                ? 'bg-slate-900 border-amber-500/50 text-amber-200'
                : isError
                ? 'bg-slate-900 border-rose-500/50 text-rose-200'
                : 'bg-slate-900 border-sky-500/50 text-sky-200'
            }`}
          >
            <div className="shrink-0 mt-0.5">
              {isSuccess && <CheckCircle2 className="w-4 h-4 text-emerald-400" />}
              {isWarning && <AlertCircle className="w-4 h-4 text-amber-400" />}
              {isError && <AlertCircle className="w-4 h-4 text-rose-400" />}
              {!isSuccess && !isWarning && !isError && <Info className="w-4 h-4 text-sky-400" />}
            </div>
            <div
              className="flex-1 leading-relaxed"
              dangerouslySetInnerHTML={{ __html: t.message }}
            />
            <button
              onClick={() => removeToast(t.id)}
              className="text-slate-400 hover:text-white shrink-0 p-0.5"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
