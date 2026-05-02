import React from "react";
import { ArrowUp, ArrowDown, ArrowUpRight } from "lucide-react";

type Sig = {
  home_team: string;
  away_team: string;
  league: string;
  selLabel: string;
  odds: string;
  pct: string;
  amt: string;
  curAmt?: string;
  pctAmt: string;
  curPctAmt?: string;
  vol: string;
  curVol?: string;
  isStale?: boolean;
  hoursBefore?: string;
  score?: string;
};

const palette = {
  underdog: { color: "#d29922", bg: "rgba(210,153,34,0.10)", border: "rgba(210,153,34,0.25)", cardBorder: "rgba(210,153,34,0.15)" },
  cmoney: { color: "#34d399", bg: "rgba(52,211,153,0.10)", border: "rgba(52,211,153,0.25)", cardBorder: "rgba(52,211,153,0.15)" },
  cmoneyV2: { color: "#6366f1", bg: "rgba(99,102,241,0.10)", border: "rgba(99,102,241,0.25)", cardBorder: "rgba(99,102,241,0.15)" },
  early: { color: "#58a6ff", bg: "rgba(88,166,255,0.10)", border: "rgba(88,166,255,0.25)", cardBorder: "rgba(88,166,255,0.15)" },
  fake: { color: "#f85149", bg: "rgba(248,81,73,0.10)", border: "rgba(248,81,73,0.25)", cardBorder: "rgba(248,81,73,0.15)" },
};

function StatCell({ label, orig, cur }: { label: string; orig: string; cur?: string }) {
  if (!orig) return null;
  const oNum = parseFloat(String(orig).replace(/[^0-9.]/g, ""));
  const cNum = cur ? parseFloat(String(cur).replace(/[^0-9.]/g, "")) : NaN;
  
  let arrow = null;
  let valColor = "text-zinc-300";
  
  if (cur && cur !== orig && !isNaN(oNum) && !isNaN(cNum)) {
    if (cNum > oNum) { 
      arrow = <ArrowUp className="w-3 h-3 text-emerald-400" strokeWidth={3} />; 
      valColor = "text-zinc-100";
    }
    else if (cNum < oNum) { 
      arrow = <ArrowDown className="w-3 h-3 text-rose-400" strokeWidth={3} />; 
      valColor = "text-zinc-100";
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="text-[10px] uppercase tracking-wider text-zinc-500 font-medium">{label}</div>
      <div className="flex items-center gap-2 font-['JetBrains_Mono'] text-xs">
        <span className="text-zinc-400 line-through decoration-zinc-600 decoration-1">{orig}</span>
        {cur && cur !== orig && (
          <div className="flex items-center gap-1 bg-zinc-800/50 px-1.5 py-0.5 rounded">
            {arrow}
            <span className={`font-semibold ${valColor}`}>{cur}</span>
          </div>
        )}
      </div>
    </div>
  );
}

function EditorialCard({ sig, kind }: { sig: Sig; kind: keyof typeof palette }) {
  const p = palette[kind];
  const isStale = !!sig.isStale;

  return (
    <div className={`relative bg-[#13151a] rounded-xl overflow-hidden mb-6 transition-all duration-300 hover:shadow-xl hover:shadow-black/50 ${isStale ? 'opacity-60' : 'opacity-100'}`}>
      {/* Accent Top Bar */}
      <div className="absolute top-0 left-0 right-0 h-1" style={{ backgroundColor: p.color }} />
      
      <div className="p-5">
        {/* Header: League & Badges */}
        <div className="flex justify-between items-start mb-4">
          <div className="flex items-center gap-3">
            <span className="text-[11px] font-['Space_Grotesk'] font-medium uppercase tracking-[0.1em] text-zinc-400">
              {sig.league}
            </span>
            {sig.hoursBefore && (
              <span className="text-[10px] font-['Space_Grotesk'] px-2 py-0.5 bg-zinc-800 text-zinc-300 rounded-sm">
                {sig.hoursBefore}
              </span>
            )}
            {isStale && (
              <span className="text-[10px] font-['Space_Grotesk'] px-2 py-0.5 bg-rose-900/30 text-rose-400 border border-rose-500/20 rounded-sm font-semibold tracking-wider">
                ↓ ZAYIFLADI
              </span>
            )}
          </div>
          
          <button className="group flex items-center gap-1 text-[10px] font-bold tracking-wider text-zinc-400 hover:text-white transition-colors uppercase bg-zinc-800/50 hover:bg-zinc-700 px-2.5 py-1 rounded-sm border border-zinc-700/50">
            İNCELE <ArrowUpRight className="w-3 h-3 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
          </button>
        </div>

        {/* Main Content: Teams & Pick */}
        <div className="flex justify-between items-end mb-6">
          <div className="flex-1">
            <h2 className="font-['Playfair_Display'] text-2xl font-bold text-zinc-100 leading-tight">
              <span className="block">{sig.home_team}</span>
              <span className="block text-zinc-500 italic font-normal text-xl mt-1">vs <span className="text-zinc-100 font-bold not-italic text-2xl">{sig.away_team}</span></span>
            </h2>
          </div>
          
          <div className="flex flex-col items-end gap-2 shrink-0 ml-4">
            <div className="flex gap-2">
              {sig.score && (
                <div className="flex flex-col items-center justify-center bg-zinc-800/50 border border-zinc-700/50 px-3 py-1.5 rounded-md min-w-[3rem]">
                  <span className="text-[9px] uppercase tracking-wider text-zinc-500 font-medium mb-0.5">Skor</span>
                  <span className="font-['JetBrains_Mono'] text-sm font-bold text-zinc-300">{sig.score}</span>
                </div>
              )}
              <div 
                className="flex flex-col items-center justify-center border px-3 py-1.5 rounded-md min-w-[3.5rem]"
                style={{ backgroundColor: p.bg, borderColor: p.border }}
              >
                <span className="text-[9px] uppercase tracking-wider font-medium mb-0.5" style={{ color: p.color, opacity: 0.8 }}>Seçim</span>
                <span className="font-['Space_Grotesk'] text-lg font-bold" style={{ color: p.color }}>{sig.selLabel}</span>
              </div>
            </div>
            
            <div className="flex gap-2">
              <div className="flex items-center gap-1.5 px-2 py-1 bg-zinc-800/40 rounded border border-zinc-700/30">
                <span className="text-[10px] text-zinc-500 font-medium">Oran</span>
                <span className="font-['JetBrains_Mono'] text-xs font-bold text-zinc-200">{sig.odds}</span>
              </div>
              <div className="flex items-center gap-1.5 px-2 py-1 bg-zinc-800/40 rounded border border-zinc-700/30">
                <span className="text-[10px] text-zinc-500 font-medium">Güven</span>
                <span className="font-['JetBrains_Mono'] text-xs font-bold text-zinc-200">{sig.pct}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-3 gap-4 pt-4 border-t border-zinc-800/80">
          <StatCell label="Para" orig={sig.amt} cur={sig.curAmt} />
          <StatCell label="% Para" orig={sig.pctAmt} cur={sig.curPctAmt} />
          <StatCell label="Hacim" orig={sig.vol} cur={sig.curVol} />
        </div>
      </div>
    </div>
  );
}

const samples: { kind: keyof typeof palette; label: string; sig: Sig }[] = [
  {
    kind: "underdog",
    label: "Underdog Pressure",
    sig: { home_team: "Cheltenham", away_team: "Colchester", league: "England League Two", selLabel: "1", odds: "2.45", pct: "38.2%", amt: "£ 4,210", curAmt: "£ 5,890", pctAmt: "32.1%", curPctAmt: "38.2%", vol: "£ 13,120", curVol: "£ 15,402", hoursBefore: "2s 14d kala" },
  },
  {
    kind: "cmoney",
    label: "Confirmed Money",
    sig: { home_team: "Villarreal", away_team: "Levante", league: "Spain La Liga", selLabel: "X", odds: "3.30", pct: "62.4%", amt: "£ 8,910", curAmt: "£ 12,450", pctAmt: "55.0%", curPctAmt: "62.4%", vol: "£ 18,720", curVol: "£ 19,950" },
  },
  {
    kind: "cmoneyV2",
    label: "Confirmed Money V2",
    sig: { home_team: "Inter", away_team: "Lazio", league: "Italy Serie A", selLabel: "2", odds: "4.10", pct: "71.0%", amt: "£ 11,400", curAmt: "£ 14,920", pctAmt: "65.5%", curPctAmt: "71.0%", vol: "£ 22,100", curVol: "£ 23,650", isStale: true },
  },
  {
    kind: "early",
    label: "Early Money Lock",
    sig: { home_team: "Arsenal", away_team: "Brighton", league: "England Premier League", selLabel: "1", odds: "1.65", pct: "84.2%", amt: "£ 18,300", curAmt: "£ 21,750", pctAmt: "78.9%", curPctAmt: "84.2%", vol: "£ 28,900", curVol: "£ 31,210", hoursBefore: "1s 3d kala" },
  },
  {
    kind: "fake",
    label: "Fake Sharp",
    sig: { home_team: "Paris St-G", away_team: "Lorient", league: "France Ligue 1", selLabel: "1", odds: "1.95 → 2.20", pct: "+12%", amt: "£ 6,420", curAmt: "£ 4,980", pctAmt: "48.0%", curPctAmt: "39.5%", vol: "£ 14,800", curVol: "£ 13,210" },
  },
];

export function Editorial() {
  return (
    <div className="min-h-screen bg-[#0d1117] p-6 font-sans">
      <div className="max-w-[480px] mx-auto">
        <div className="text-[11px] text-zinc-500 uppercase tracking-[0.15em] mb-8 font-semibold flex items-center gap-3">
          <span className="w-8 h-[1px] bg-zinc-700"></span>
          Editorial Sport Varyantı
          <span className="flex-1 h-[1px] bg-zinc-800"></span>
        </div>
        {samples.map((s) => (
          <div key={s.label}>
            <div className="flex items-center gap-2 mb-3 ml-1">
              <div className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: palette[s.kind].color }} />
              <div className="text-xs text-zinc-400 font-['Space_Grotesk'] font-medium uppercase tracking-wider">
                {s.label}
              </div>
            </div>
            <EditorialCard sig={s.sig} kind={s.kind} />
          </div>
        ))}
      </div>
    </div>
  );
}
