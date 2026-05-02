import React, { useState } from "react";
import { X, Clock, TrendingDown, TrendingUp, AlertTriangle, ArrowRight } from "lucide-react";

const CHIPS = [
  { id: "all", label: "Tümü", icon: null, color: "#e0e4e8", isAuto: false, count: null },
  { id: "underdog", label: "Underdog Pressure", icon: "⚡", color: "#d29922", isAuto: true, count: 12 },
  { id: "confirmed-money", label: "Confirmed Money", icon: "💰", color: "#34d399", isAuto: true, count: 28 },
  { id: "confirmed-money-v2", label: "Confirmed Money V2", icon: "💎", color: "#6366f1", isAuto: true, count: 7 },
  { id: "early-money", label: "Early Money Lock", icon: "🔒", color: "#58a6ff", isAuto: true, count: 19 },
  { id: "fake-sharp", label: "Fake Sharp", icon: "⚠️", color: "#f85149", isAuto: true, count: 4 },
];

const FAKE_MATCHES = [
  {
    id: 1,
    league: "İngiltere Premier Lig",
    home: "Arsenal",
    away: "Manchester Utd",
    time: "2 saat önce",
    oddsDesc: "Ev Sahibi Kazanır",
    oldOdds: "2.40",
    newOdds: "1.95",
    drift: "-18.7%",
  },
  {
    id: 2,
    league: "İspanya La Liga",
    home: "Real Sociedad",
    away: "Sevilla",
    time: "4 saat önce",
    oddsDesc: "Alt 2.5 Gol",
    oldOdds: "1.90",
    newOdds: "1.65",
    drift: "-13.1%",
  },
  {
    id: 3,
    league: "İtalya La Liga",
    home: "Genoa",
    away: "Osasuna",
    time: "5 saat önce",
    oddsDesc: "Deplasman Kazanır",
    oldOdds: "3.20",
    newOdds: "2.75",
    drift: "-14.0%",
  },
];

export function PillRail() {
  const [selected, setSelected] = useState("confirmed-money");

  return (
    <div className="min-h-screen w-full bg-black/60 flex items-center justify-center p-4 sm:p-6 font-sans">
      <div className="w-full max-w-[1040px] bg-[#0d1117] rounded-2xl border border-[#2e3238] shadow-2xl flex flex-col max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-start justify-between p-6 pb-4 shrink-0">
          <div>
            <h2 className="text-[20px] font-semibold text-[#e0e4e8] tracking-tight leading-tight">Analizler</h2>
            <p className="text-[13px] text-[#7d848c] mt-1 font-medium">Profesyonel piyasa analizleri</p>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-[11px] font-medium text-[#484f58] flex items-center gap-1.5 bg-white/5 px-2.5 py-1 rounded-full border border-white/5">
              <span className="w-1.5 h-1.5 rounded-full bg-[#34d399] animate-pulse"></span>
              Son güncelleme: 2 dk önce
            </div>
            <button className="text-[#7d848c] hover:text-[#e0e4e8] transition-colors p-1 rounded-md hover:bg-white/5">
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Horizontal Rail */}
        <div className="border-b border-[#21262d] shrink-0">
          <div className="overflow-x-auto scrollbar-hide px-6">
            <div className="flex items-center gap-6 min-w-max pb-[1px]">
              {CHIPS.map((chip) => {
                const isSelected = selected === chip.id;
                
                // We use inline styles for the dynamic colors to tint the pill appropriately.
                // We'll compute hex to rgba approximations for the background and border
                // Let's rely on standard tailwind if possible, but the requirement is custom hex
                
                return (
                  <button
                    key={chip.id}
                    onClick={() => setSelected(chip.id)}
                    className={`relative py-3 flex items-center gap-2 group transition-all`}
                  >
                    <div className={`flex items-center gap-2 ${isSelected ? '' : 'opacity-60 group-hover:opacity-100'}`}>
                      {chip.icon && <span className="text-[15px]">{chip.icon}</span>}
                      <span 
                        className="text-[14px] font-medium whitespace-nowrap"
                        style={{ color: isSelected ? '#e0e4e8' : '#7d848c' }}
                      >
                        {chip.label}
                      </span>
                      {chip.isAuto && (
                        <span 
                          className="text-[9px] font-bold px-1.5 py-0.5 rounded ml-1"
                          style={{
                            color: chip.color,
                            backgroundColor: `${chip.color}15`, // ~8% opacity
                            border: `1px solid ${chip.color}30` // ~18% opacity
                          }}
                        >
                          AUTO
                        </span>
                      )}
                    </div>
                    {/* Selection underline */}
                    {isSelected && (
                      <div 
                        className="absolute bottom-[-1px] left-0 right-0 h-[2px] rounded-t-full"
                        style={{ backgroundColor: chip.color === '#e0e4e8' ? '#e0e4e8' : chip.color }}
                      ></div>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto p-6 md:p-8">
          {selected === "all" && (
            <div className="flex flex-col items-center justify-center h-full text-center py-20">
              <span className="text-4xl mb-4 opacity-50">📊</span>
              <p className="text-[#7d848c] text-[14px]">Yukarıdan bir sinyal türü seçin</p>
            </div>
          )}

          {selected === "confirmed-money" && (
            <div className="max-w-4xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
              {/* Hero Section */}
              <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
                <div>
                  <div className="flex items-center gap-3 mb-3">
                    <span className="text-2xl">💰</span>
                    <h3 className="text-2xl font-bold text-[#e0e4e8]">Confirmed Money</h3>
                  </div>
                  <p className="text-[#7d848c] text-[15px] max-w-xl leading-relaxed">
                    Piyasadaki büyük hacimli bahislerin oranları ciddi şekilde düşürdüğü maçları tespit eder. 
                    Genellikle profesyonel bahisçilerin girdiği ("smart money") pozisyonları yansıtır.
                  </p>
                </div>
                <div className="shrink-0 flex items-center gap-2 bg-[#34d399]/10 border border-[#34d399]/20 px-4 py-2.5 rounded-lg">
                  <span className="w-2 h-2 rounded-full bg-[#34d399] animate-pulse"></span>
                  <span className="text-[#34d399] font-semibold text-[14px]">28 aktif sinyal</span>
                </div>
              </div>

              {/* Match List */}
              <div className="space-y-4">
                <h4 className="text-[12px] font-semibold text-[#484f58] uppercase tracking-wider">Öne Çıkan Fırsatlar</h4>
                
                <div className="grid gap-3">
                  {FAKE_MATCHES.map((match) => (
                    <div 
                      key={match.id} 
                      className="group flex flex-col md:flex-row md:items-center justify-between p-5 rounded-xl border border-[#21262d] bg-[#0d1117] hover:bg-[#161b22] hover:border-[#2e3238] transition-all gap-4"
                    >
                      <div className="flex items-start gap-4">
                        <div className="w-10 h-10 rounded-full bg-[#21262d] flex items-center justify-center shrink-0 group-hover:bg-[#2e3238] transition-colors">
                          <TrendingDown className="w-5 h-5 text-[#34d399]" />
                        </div>
                        <div>
                          <div className="text-[12px] text-[#7d848c] mb-1 font-medium">{match.league}</div>
                          <div className="text-[#e0e4e8] font-semibold text-[15px]">
                            {match.home} <span className="text-[#484f58] mx-1">vs</span> {match.away}
                          </div>
                          <div className="flex items-center gap-2 mt-2">
                            <span className="text-[12px] font-medium text-[#c9d1d9] bg-white/5 px-2 py-0.5 rounded border border-white/5">
                              {match.oddsDesc}
                            </span>
                            <div className="flex items-center text-[12px] text-[#7d848c]">
                              <Clock className="w-3 h-3 mr-1" />
                              {match.time}
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-6 md:border-l border-[#21262d] md:pl-6 pt-4 md:pt-0 border-t md:border-t-0">
                        <div className="flex flex-col items-end">
                          <span className="text-[11px] text-[#7d848c] font-medium mb-1">Oran Düşüşü</span>
                          <div className="flex items-center gap-2">
                            <span className="text-[13px] text-[#7d848c] line-through">{match.oldOdds}</span>
                            <ArrowRight className="w-3 h-3 text-[#484f58]" />
                            <span className="text-[16px] font-bold text-[#e0e4e8]">{match.newOdds}</span>
                          </div>
                        </div>
                        
                        <div className="bg-[#34d399]/10 border border-[#34d399]/20 rounded-lg px-3 py-2 flex flex-col items-center justify-center min-w-[72px]">
                          <span className="text-[#34d399] font-bold text-[15px] leading-none">{match.drift}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Placeholder for other selected states */}
          {selected !== "all" && selected !== "confirmed-money" && (
            <div className="flex flex-col items-center justify-center h-full text-center py-20 opacity-50">
              <p className="text-[#7d848c] text-[14px]">Örnek olarak sadece "Confirmed Money" tasarımı uygulandı.</p>
            </div>
          )}
        </div>
      </div>
      
      <style>{`
        .scrollbar-hide::-webkit-scrollbar {
            display: none;
        }
        .scrollbar-hide {
            -ms-overflow-style: none;
            scrollbar-width: none;
        }
      `}</style>
    </div>
  );
}
