import React, { useState } from 'react';
import { X, BarChart3, Clock, CheckCircle2 } from 'lucide-react';

const SIGNALS = [
  {
    id: 'underdog',
    title: 'Underdog Pressure',
    color: '#d29922',
    icon: '⚡',
    activeCount: 12,
    description: 'Beklenmedik hacim artışları ve oran düşüşleriyle desteklenen sürpriz takımları tespit eder. Piyasanın gözden kaçırdığı potansiyel değerleri bulur.',
    lastMatch: 'Aston Villa vs Twente, 8 dk önce',
    accuracy: '%74'
  },
  {
    id: 'confirmed',
    title: 'Confirmed Money',
    color: '#34d399',
    icon: '💰',
    activeCount: 28,
    description: 'Büyük bahis sendikalarının ve akıllı paranın girdiği maçları doğrular. Asya handikap ve taraf bahislerindeki hacim yoğunlaşmalarını gösterir.',
    lastMatch: 'Ajax vs Feyenoord, 15 dk önce',
    accuracy: '%78'
  },
  {
    id: 'confirmed-v2',
    title: 'Confirmed Money V2',
    color: '#6366f1',
    icon: '💎',
    activeCount: 7,
    description: 'Geliştirilmiş algoritmasıyla profesyonel oyuncuların son dakika bahislerini yakalar. Daha az fakat daha yüksek güvenilirliğe sahip sinyaller üretir.',
    lastMatch: 'Arsenal vs Chelsea, 42 dk önce',
    accuracy: '%82'
  },
  {
    id: 'early',
    title: 'Early Money Lock',
    color: '#58a6ff',
    icon: '🔒',
    activeCount: 19,
    description: 'Piyasa açılışından hemen sonra oluşan erken pozisyonları kilitler. Oranlar düşmeden önce değerli bahisleri yakalamanızı sağlar.',
    lastMatch: 'Bologna vs Roma, 1 sa önce',
    accuracy: '%71'
  },
  {
    id: 'fake',
    title: 'Fake Sharp',
    color: '#f85149',
    icon: '⚠️',
    activeCount: 4,
    description: 'Suni hacim yaratılarak bahisçileri yanıltmaya çalışan hareketleri deşifre eder. Tuzak oranlara düşmenizi engeller.',
    lastMatch: 'Lazio vs Napoli, 2 sa önce',
    accuracy: '%86'
  }
];

export function Magazine() {
  const [selected, setSelected] = useState<string | null>(null);

  const renderCard = (signal: typeof SIGNALS[0]) => {
    const isSelected = selected === signal.id;
    return (
      <div 
        key={signal.id}
        onClick={() => setSelected(isSelected ? null : signal.id)}
        className="group relative flex flex-col sm:flex-row gap-4 p-4 sm:p-5 rounded-2xl cursor-pointer transition-all duration-300 overflow-hidden"
        style={{
          background: isSelected ? 'rgba(28, 31, 35, 0.8)' : 'rgba(20, 23, 25, 0.4)',
          border: `1px solid ${isSelected ? signal.color : 'rgba(46, 50, 56, 0.5)'}`,
          boxShadow: isSelected ? `0 8px 24px -8px ${signal.color}33` : 'none',
          transform: isSelected ? 'translateY(-2px)' : 'none'
        }}
      >
        {/* Glow effect on hover */}
        <div 
          className="absolute inset-0 opacity-0 group-hover:opacity-10 transition-opacity duration-500 pointer-events-none"
          style={{ background: `radial-gradient(circle at 50% 0%, ${signal.color}, transparent 70%)` }}
        />

        {/* Huge Icon Block */}
        <div 
          className="w-full sm:w-32 h-24 sm:h-auto rounded-xl flex items-center justify-center text-4xl shrink-0"
          style={{ 
            background: `linear-gradient(135deg, ${signal.color}22, ${signal.color}05)`,
            border: `1px solid ${signal.color}33`
          }}
        >
          <span style={{ filter: `drop-shadow(0 4px 12px ${signal.color}44)` }}>{signal.icon}</span>
        </div>

        {/* Content */}
        <div className="flex-1 flex flex-col justify-between min-w-0">
          <div>
            <div className="flex items-start justify-between gap-3 mb-2">
              <h3 className="text-xl sm:text-2xl font-bold tracking-tight text-[#e0e4e8] truncate">
                {signal.title}
              </h3>
              <span 
                className="shrink-0 text-[10px] font-bold px-2 py-0.5 rounded-full tracking-wider"
                style={{ 
                  color: signal.color, 
                  backgroundColor: `${signal.color}15`,
                  border: `1px solid ${signal.color}33`
                }}
              >
                AUTO
              </span>
            </div>
            <p className="text-sm text-[#7d848c] leading-relaxed mb-4 line-clamp-2">
              {signal.description}
            </p>
          </div>

          {/* Meta Row */}
          <div className="flex flex-wrap items-center gap-3 sm:gap-5 pt-3 border-t border-[#2e3238] mt-auto">
            <div className="flex items-center gap-1.5 text-xs font-medium" style={{ color: signal.color }}>
              <div className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ backgroundColor: signal.color }} />
              {signal.activeCount} aktif sinyal
            </div>
            <div className="w-1 h-1 rounded-full bg-[#2e3238] hidden sm:block" />
            <div className="flex items-center gap-1.5 text-xs text-[#7d848c]">
              <Clock className="w-3.5 h-3.5" />
              <span className="truncate max-w-[120px] sm:max-w-none">{signal.lastMatch}</span>
            </div>
            <div className="w-1 h-1 rounded-full bg-[#2e3238] hidden sm:block" />
            <div className="flex items-center gap-1.5 text-xs text-[#7d848c]">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Doğruluk: <span className="text-[#e0e4e8] font-medium">{signal.accuracy}</span>
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen w-full bg-black/60 flex items-center justify-center p-4 font-sans">
      <div className="w-full max-w-[800px] bg-[#0d1117] border border-[#2e3238] rounded-2xl shadow-2xl flex flex-col max-h-[90vh]">
        
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-[#2e3238] shrink-0">
          <div>
            <h2 className="text-xl font-semibold text-[#e0e4e8] flex items-center gap-2">
              Analizler
              <span className="text-xs font-medium text-[#7d848c] bg-[#1c1f23] px-2 py-1 rounded-md border border-[#2e3238]">
                EDİTÖRYAL
              </span>
            </h2>
            <p className="text-sm text-[#7d848c] mt-1">Profesyonel piyasa analizleri</p>
          </div>
          <button className="p-2 text-[#7d848c] hover:text-[#e0e4e8] hover:bg-[#1c1f23] rounded-lg transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Filter Pill Row */}
        <div className="px-5 py-4 border-b border-[#2e3238] shrink-0 overflow-x-auto scrollbar-none">
          <div className="flex items-center gap-2 min-w-max">
            <button
              onClick={() => setSelected(null)}
              className={`px-4 py-1.5 rounded-full text-sm font-medium transition-all ${
                selected === null 
                  ? 'bg-[#e0e4e8] text-[#0d1117]' 
                  : 'bg-[#1c1f23] text-[#7d848c] border border-[#2e3238] hover:text-[#e0e4e8]'
              }`}
            >
              Tümü
            </button>
            {SIGNALS.map(s => (
              <button
                key={`filter-${s.id}`}
                onClick={() => setSelected(s.id)}
                className={`px-4 py-1.5 rounded-full text-sm font-medium transition-all border`}
                style={{
                  backgroundColor: selected === s.id ? `${s.color}22` : '#1c1f23',
                  borderColor: selected === s.id ? s.color : '#2e3238',
                  color: selected === s.id ? s.color : '#7d848c'
                }}
              >
                {s.title}
              </button>
            ))}
          </div>
        </div>

        {/* Article List */}
        <div className="p-5 overflow-y-auto flex-1">
          <div className="flex flex-col gap-4 pb-6">
            {SIGNALS.filter(s => selected === null || selected === s.id).map(renderCard)}
            
            {/* Empty State placeholder */}
            <div className="mt-8 flex flex-col items-center justify-center p-8 text-center border border-dashed border-[#2e3238] rounded-2xl bg-[#141719]/30">
              <div className="w-12 h-12 bg-[#1c1f23] rounded-full flex items-center justify-center mb-3">
                <BarChart3 className="w-6 h-6 text-[#484f58]" />
              </div>
              <p className="text-sm font-medium text-[#7d848c]">Yukarıdan bir sinyal türü seçin ve detayları görüntüleyin</p>
              <p className="text-xs text-[#484f58] mt-1">Son güncelleme: 2 dk önce</p>
            </div>
          </div>
        </div>
        
      </div>
    </div>
  );
}
