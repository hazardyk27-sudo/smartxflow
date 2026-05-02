import React, { useState, useEffect } from 'react';
import { X, BarChart2, Clock } from 'lucide-react';

export function Spectrum() {
  const [selectedChip, setSelectedChip] = useState<number | null>(null);
  
  // Rainbow spectrum colors
  const C_AMBER = '#d29922';
  const C_GREEN = '#34d399';
  const C_INDIGO = '#6366f1';
  const C_BLUE = '#58a6ff';
  const C_RED = '#f85149';
  
  const chips = [
    { id: 0, label: 'Tümü', icon: '', color: '#8b949e', count: 0, auto: false },
    { id: 1, label: 'Underdog Pressure', icon: '⚡', color: C_AMBER, count: 12, auto: true },
    { id: 2, label: 'Confirmed Money', icon: '💰', color: C_GREEN, count: 28, auto: true },
    { id: 3, label: 'Confirmed Money V2', icon: '💎', color: C_INDIGO, count: 7, auto: true },
    { id: 4, label: 'Early Money Lock', icon: '🔒', color: C_BLUE, count: 19, auto: true },
    { id: 5, label: 'Fake Sharp', icon: '⚠️', color: C_RED, count: 4, auto: true },
  ];

  const recentSignals = [
    { time: '14:32', match: 'Fenerbahçe - Galatasaray', type: 'Confirmed Money', color: C_GREEN },
    { time: '14:28', match: 'Arsenal - Chelsea', type: 'Early Money Lock', color: C_BLUE },
    { time: '14:15', match: 'Real Madrid - Barcelona', type: 'Fake Sharp', color: C_RED },
    { time: '14:05', match: 'Bayern Munich - Atletico', type: 'Underdog Pressure', color: C_AMBER },
    { time: '13:55', match: 'Juventus - Dortmund', type: 'Confirmed Money V2', color: C_INDIGO },
  ];

  return (
    <div className="min-h-screen w-full bg-black/60 flex items-center justify-center p-4 font-sans text-[#e0e4e8]">
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400..900;1,400..900&display=swap');
        
        .spectrum-bg {
          background: linear-gradient(90deg, 
            rgba(210,153,34,0.15) 0%, 
            rgba(52,211,153,0.15) 25%, 
            rgba(99,102,241,0.15) 50%, 
            rgba(88,166,255,0.15) 75%, 
            rgba(248,81,73,0.15) 100%
          );
        }
        
        .marquee-container {
          overflow: hidden;
          white-space: nowrap;
          position: relative;
        }
        .marquee-content {
          display: inline-block;
          animation: marquee 30s linear infinite;
        }
        @keyframes marquee {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        
        .scrollbar-hide::-webkit-scrollbar {
          display: none;
        }
        .scrollbar-hide {
          -ms-overflow-style: none;
          scrollbar-width: none;
        }
      `}</style>
      
      <div className="w-full max-w-[1040px] bg-[#0d1117] border border-[#2e3238] rounded-2xl overflow-hidden shadow-2xl flex flex-col max-h-[90vh]">
        
        {/* HERO SECTION */}
        <div className="relative pt-12 pb-8 px-6 sm:px-10 text-center border-b border-[#21262d] overflow-hidden">
          <div className="absolute inset-0 spectrum-bg blur-xl pointer-events-none" />
          
          <button className="absolute top-4 right-4 p-2 text-[#7d848c] hover:text-white hover:bg-white/10 rounded-full transition-colors z-10">
            <X size={20} />
          </button>
          
          <div className="relative z-10">
            <h1 className="text-5xl sm:text-6xl font-bold text-white mb-3" style={{ fontFamily: '"Playfair Display", serif' }}>
              Analizler
            </h1>
            <p className="text-[#7d848c] text-sm sm:text-base font-medium tracking-wide uppercase">
              Profesyonel piyasa analizleri
            </p>
          </div>
        </div>

        {/* MARQUEE TICKER */}
        <div className="bg-[#161b22] border-b border-[#2e3238] py-2 flex items-center">
          <div className="px-4 text-[#7d848c] border-r border-[#2e3238] flex items-center gap-2 text-xs font-semibold whitespace-nowrap shrink-0">
            <Clock size={14} className="text-[#58a6ff]" />
            CANLI AKIŞ
          </div>
          <div className="marquee-container flex-1 ml-4">
            <div className="marquee-content flex gap-6 items-center">
              {[...recentSignals, ...recentSignals].map((sig, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <span className="text-[#7d848c]">{sig.time}</span>
                  <span className="text-white font-medium">{sig.match}</span>
                  <span className="px-2 py-0.5 rounded-full bg-black/50 border border-white/10" style={{ color: sig.color }}>
                    {sig.type}
                  </span>
                  <span className="text-[#2e3238] mx-2">•</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="p-4 sm:p-6 bg-[#0d1117] flex-1 overflow-y-auto">
          
          {/* SEGMENTED CHIP STRIP */}
          <div className="mb-8">
            <div className="flex overflow-x-auto scrollbar-hide pb-4 sm:pb-0 -mx-4 px-4 sm:mx-0 sm:px-0">
              <div className="flex bg-[#161b22] border border-[#2e3238] rounded-xl sm:rounded-full p-1 mx-auto shadow-inner min-w-max">
                {chips.map((c) => {
                  const isSelected = selectedChip === c.id;
                  return (
                    <button
                      key={c.id}
                      onClick={() => setSelectedChip(c.id)}
                      className={`
                        relative flex items-center justify-center gap-2 px-4 py-2 sm:py-2.5 rounded-lg sm:rounded-full transition-all duration-300
                        ${isSelected ? 'bg-[#21262d] shadow-md' : 'hover:bg-[#21262d]/50'}
                      `}
                    >
                      {/* Color bar indicator */}
                      {isSelected && c.id !== 0 && (
                        <div 
                          className="absolute left-2 sm:left-3 top-1/2 -translate-y-1/2 w-1 h-4 sm:h-5 rounded-full" 
                          style={{ backgroundColor: c.color, boxShadow: `0 0 8px ${c.color}` }} 
                        />
                      )}
                      
                      <div className={`flex items-center gap-2 ${isSelected && c.id !== 0 ? 'pl-3' : ''}`}>
                        {c.icon && <span className="text-sm sm:text-base">{c.icon}</span>}
                        <span className={`text-xs sm:text-sm font-semibold whitespace-nowrap ${isSelected ? 'text-white' : 'text-[#7d848c]'}`}>
                          {c.label}
                        </span>
                        
                        {c.count > 0 && (
                          <span className="text-[10px] sm:text-xs font-bold px-1.5 py-0.5 rounded-full bg-white/5 text-white/70 ml-1">
                            {c.count}
                          </span>
                        )}
                        
                        {c.auto && (
                          <span 
                            className="absolute -top-1 -right-1 text-[8px] font-bold px-1.5 py-0.5 rounded border uppercase"
                            style={{ 
                              color: c.color, 
                              backgroundColor: `${c.color}15`,
                              borderColor: `${c.color}40`
                            }}
                          >
                            AUTO
                          </span>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="text-center mt-3 text-xs text-[#484f58] font-medium">
              Son güncelleme: 2 dk önce
            </div>
          </div>

          {/* EMPTY STATE */}
          <div className="flex flex-col items-center justify-center py-20 px-4 text-center rounded-2xl border border-dashed border-[#2e3238] bg-[#161b22]/30">
            <div className="w-16 h-16 mb-4 rounded-2xl bg-[#21262d] flex items-center justify-center border border-[#2e3238] shadow-lg">
              <BarChart2 size={32} className="text-[#5c636b]" />
            </div>
            <h3 className="text-lg font-semibold text-[#e0e4e8] mb-2">Sinyal Türü Seçin</h3>
            <p className="text-sm text-[#7d848c] max-w-sm">
              Detaylı analizleri, oran hareketlerini ve yapay zeka öngörülerini görüntülemek için yukarıdaki listeden bir sinyal türü seçin.
            </p>
          </div>
          
        </div>
      </div>
    </div>
  );
}
