import React, { useState } from 'react';
import { X, Clock } from 'lucide-react';

export function Hub() {
  const [selectedSignal, setSelectedSignal] = useState<string | null>(null);

  const signals = [
    {
      id: 'all',
      title: 'Tümü',
      subtitle: 'Tüm Sinyaller',
      count: 70,
      color: '#8b949e',
      bg: 'rgba(139, 148, 158, 0.05)',
      border: 'rgba(139, 148, 158, 0.2)',
      icon: '📊',
      lastHit: 'Son 24 saatte 70 sinyal',
      trend: [40, 60, 45],
      isAuto: false
    },
    {
      id: 'underdog',
      title: 'Underdog',
      subtitle: 'Pressure',
      count: 12,
      color: '#d29922',
      bg: 'rgba(210, 153, 34, 0.05)',
      border: 'rgba(210, 153, 34, 0.2)',
      badgeBg: 'rgba(210, 153, 34, 0.1)',
      badgeBorder: 'rgba(210, 153, 34, 0.2)',
      icon: '⚡',
      lastHit: 'Sassuolo vs AC Milan • 9 dk',
      trend: [20, 50, 80],
      isAuto: true
    },
    {
      id: 'confirmed',
      title: 'Confirmed',
      subtitle: 'Money',
      count: 28,
      color: '#34d399',
      bg: 'rgba(52, 211, 153, 0.05)',
      border: 'rgba(52, 211, 153, 0.2)',
      badgeBg: 'rgba(52, 211, 153, 0.1)',
      badgeBorder: 'rgba(52, 211, 153, 0.2)',
      icon: '💰',
      lastHit: 'Arsenal vs Juventus • 14 dk',
      trend: [60, 90, 70],
      isAuto: true
    },
    {
      id: 'confirmed-v2',
      title: 'Confirmed',
      subtitle: 'Money V2',
      count: 7,
      color: '#6366f1',
      bg: 'rgba(99, 102, 241, 0.05)',
      border: 'rgba(99, 102, 241, 0.2)',
      badgeBg: 'rgba(99, 102, 241, 0.1)',
      badgeBorder: 'rgba(99, 102, 241, 0.2)',
      icon: '💎',
      lastHit: 'Porto vs Napoli • 21 dk',
      trend: [30, 40, 20],
      isAuto: true
    },
    {
      id: 'early-lock',
      title: 'Early Money',
      subtitle: 'Lock',
      count: 19,
      color: '#58a6ff',
      bg: 'rgba(88, 166, 255, 0.05)',
      border: 'rgba(88, 166, 255, 0.2)',
      badgeBg: 'rgba(88, 166, 255, 0.1)',
      badgeBorder: 'rgba(88, 166, 255, 0.2)',
      icon: '🔒',
      lastHit: 'Chelsea vs Bayern • 1 sa',
      trend: [50, 70, 90],
      isAuto: true
    },
    {
      id: 'fake-sharp',
      title: 'Fake',
      subtitle: 'Sharp',
      count: 4,
      color: '#f85149',
      bg: 'rgba(248, 81, 73, 0.05)',
      border: 'rgba(248, 81, 73, 0.2)',
      badgeBg: 'rgba(248, 81, 73, 0.1)',
      badgeBorder: 'rgba(248, 81, 73, 0.2)',
      icon: '⚠️',
      lastHit: 'Ajax vs Benfica • 2 sa',
      trend: [80, 40, 10],
      isAuto: true
    }
  ];

  return (
    <div className="min-h-screen w-full bg-black/60 flex items-center justify-center p-0 sm:p-4 font-sans text-[#e0e4e8]">
      
      {/* Scrollbar Styles for the dashboard tiles */}
      <style>{`
        .dash-scroll::-webkit-scrollbar {
          height: 6px;
        }
        .dash-scroll::-webkit-scrollbar-track {
          background: rgba(0,0,0,0.2);
          border-radius: 4px;
        }
        .dash-scroll::-webkit-scrollbar-thumb {
          background: rgba(255,255,255,0.1);
          border-radius: 4px;
        }
        .dash-scroll::-webkit-scrollbar-thumb:hover {
          background: rgba(255,255,255,0.2);
        }
      `}</style>

      <div className="w-full h-full sm:h-auto sm:max-w-[1040px] bg-[#0d1117] sm:border border-[#21262d] sm:rounded-xl shadow-2xl flex flex-col overflow-hidden">
        
        {/* Modal Chrome */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#21262d] shrink-0 bg-[#0d1117]">
          <div>
            <h2 className="text-[18px] font-semibold text-[#e0e4e8] leading-tight">Analizler</h2>
            <p className="text-[13px] text-[#7d848c] mt-0.5">Profesyonel piyasa analizleri</p>
          </div>
          <div className="flex items-center gap-4">
            <div className="hidden sm:flex items-center gap-1.5 text-xs text-[#7d848c] bg-[#161b22] px-3 py-1.5 rounded-md border border-[#30363d]">
              <Clock className="w-3.5 h-3.5" />
              <span className="font-mono">Son güncelleme: 2 dk önce</span>
            </div>
            <button className="p-1.5 hover:bg-[#21262d] rounded-md transition-colors text-[#7d848c] hover:text-[#e0e4e8]">
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto bg-[#090c10]">
          <div className="p-4 sm:p-5">
            
            {/* Dashboard Tiles Strip: 2 rows on mobile (horizontal scroll), 1 row on desktop */}
            <div className="grid grid-rows-2 grid-flow-col gap-3 overflow-x-auto pb-3 sm:pb-0 dash-scroll sm:flex sm:flex-row sm:overflow-visible">
              {signals.map((sig) => {
                const isSelected = selectedSignal === sig.id;
                
                return (
                  <button
                    key={sig.id}
                    onClick={() => setSelectedSignal(sig.id)}
                    className="relative text-left group shrink-0 w-[180px] sm:w-[155px] sm:flex-1 h-[110px] sm:h-[130px] rounded-xl transition-all duration-200 outline-none overflow-hidden"
                    style={{ 
                      backgroundColor: isSelected ? sig.bg : '#161b22',
                      border: `1px solid ${isSelected ? sig.color : '#30363d'}`,
                      boxShadow: isSelected ? `0 0 0 1px ${sig.color}40, inset 0 2px 10px rgba(0,0,0,0.2)` : 'inset 0 1px 0 rgba(255,255,255,0.02)'
                    }}
                  >
                    <div className="flex flex-col h-full p-3 relative z-10">
                      
                      {/* Top row: Icon & Badge */}
                      <div className="flex justify-between items-start mb-2">
                        <div className="text-xl sm:text-2xl leading-none filter drop-shadow-sm">{sig.icon}</div>
                        {sig.isAuto && (
                          <div 
                            className="text-[9px] font-bold px-1.5 py-0.5 rounded shadow-sm uppercase tracking-wider"
                            style={{ 
                              color: sig.color, 
                              backgroundColor: sig.badgeBg, 
                              border: `1px solid ${sig.badgeBorder}`
                            }}
                          >
                            AUTO
                          </div>
                        )}
                      </div>

                      {/* Name */}
                      <div className="text-[11px] sm:text-xs font-semibold leading-tight mb-auto" style={{ color: isSelected ? sig.color : '#c9d1d9' }}>
                        {sig.title} <span className="opacity-70">{sig.subtitle}</span>
                      </div>

                      {/* Bottom Row: Count & Sparkline */}
                      <div className="flex items-end justify-between mt-2">
                        <div className="flex items-baseline gap-1">
                          <span className="text-2xl sm:text-3xl font-bold text-white tracking-tight leading-none font-mono">
                            {sig.count}
                          </span>
                          <span className="text-[10px] text-[#7d848c] uppercase tracking-wide">snyl</span>
                        </div>
                        
                        <div className="flex items-end gap-1 h-4 w-6 opacity-80" title="Recent activity">
                          {sig.trend.map((h, i) => (
                            <div 
                              key={i} 
                              className="w-1.5 rounded-[1px]" 
                              style={{ height: `${h}%`, backgroundColor: sig.color }}
                            />
                          ))}
                        </div>
                      </div>
                      
                    </div>

                    {/* One-line preview (only visible on desktop or slightly taller cards if we wanted, but keeping it visible as a bottom bar) */}
                    <div className="absolute bottom-0 left-0 right-0 h-6 bg-black/40 border-t border-white/5 flex items-center px-3 opacity-0 sm:opacity-100">
                      <div className="text-[9px] text-[#7d848c] truncate w-full font-mono">
                        {sig.lastHit}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>

            {/* Empty State Placeholder */}
            <div className="mt-5 sm:mt-6 flex flex-col items-center justify-center p-16 sm:p-24 border border-dashed border-[#30363d] rounded-xl bg-[#161b22]/50 shadow-inner">
              <div className="text-5xl mb-4 opacity-50 grayscale">📊</div>
              <div className="text-[15px] text-[#8b949e] font-medium">
                {selectedSignal ? (
                  <span className="text-[#e0e4e8]">Loading {selectedSignal} data...</span>
                ) : (
                  "Yukarıdan bir sinyal türü seçin"
                )}
              </div>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}
