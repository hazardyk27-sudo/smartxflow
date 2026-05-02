import React from "react";
import { ArrowUp, ArrowDown, ArrowUpRight, ArrowRight } from "lucide-react";

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
  underdog: { dot: "#d29922" },
  cmoney: { dot: "#34d399" },
  cmoneyV2: { dot: "#6366f1" },
  early: { dot: "#58a6ff" },
  fake: { dot: "#f85149" },
};

function MonoCell({ label, orig, cur }: { label: string; orig: string; cur?: string }) {
  if (!orig) return null;
  const oNum = parseFloat(String(orig).replace(/[^0-9.]/g, ""));
  const cNum = cur ? parseFloat(String(cur).replace(/[^0-9.]/g, "")) : NaN;
  
  let arrow = null;
  if (cur && cur !== orig && !isNaN(oNum) && !isNaN(cNum)) {
    if (cNum > oNum) arrow = <ArrowUp className="w-3 h-3 text-[#34d399] inline -mt-0.5" />;
    else if (cNum < oNum) arrow = <ArrowDown className="w-3 h-3 text-[#f85149] inline -mt-0.5" />;
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="text-[10px] text-zinc-500 font-medium uppercase tracking-wider">{label}</div>
      <div className="font-['JetBrains_Mono'] text-[11px] flex items-center gap-1.5 whitespace-nowrap">
        <span className="text-zinc-400">{orig}</span>
        {cur && cur !== orig && (
          <div className="flex items-center gap-0.5 text-zinc-200">
            {arrow}
            <span>{cur}</span>
          </div>
        )}
      </div>
    </div>
  );
}

function SignalCard({ sig, kind }: { sig: Sig; kind: keyof typeof palette }) {
  const p = palette[kind];
  const isStale = !!sig.isStale;

  return (
    <div className={`relative group border-b border-zinc-800/50 hover:border-zinc-700 transition-colors duration-300 ${isStale ? "opacity-60 grayscale-[0.3]" : ""}`}>
      {/* Accent Line indicator */}
      <div 
        className="absolute left-0 top-0 bottom-0 w-[2px] transition-all duration-300 opacity-0 group-hover:opacity-100" 
        style={{ backgroundColor: p.dot }} 
      />
      
      <div className="p-5 pl-6 pr-5">
        <div className="flex items-start justify-between mb-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <div 
                className="w-1.5 h-1.5 rounded-full" 
                style={{ backgroundColor: p.dot }} 
              />
              <span className="text-[10px] font-medium text-zinc-400 uppercase tracking-widest">{sig.league}</span>
              {sig.hoursBefore && (
                <>
                  <span className="text-zinc-700 text-[10px]">•</span>
                  <span className="font-['JetBrains_Mono'] text-[10px] text-zinc-500">{sig.hoursBefore}</span>
                </>
              )}
            </div>
            
            <div className="flex items-center gap-3">
              <h3 className="font-['Space_Grotesk'] text-lg font-semibold text-zinc-100 tracking-tight flex items-center gap-2">
                {sig.home_team} <span className="text-zinc-600 font-normal">—</span> {sig.away_team}
              </h3>
              <button className="flex items-center gap-1 text-[10px] font-bold text-zinc-500 hover:text-zinc-300 transition-colors uppercase tracking-wider">
                İNCELE <ArrowUpRight className="w-3 h-3" />
              </button>
              {isStale && (
                <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest line-through decoration-zinc-500/50">
                  ZAYIFLADI
                </span>
              )}
            </div>
          </div>

          <div className="flex flex-col items-end gap-1">
            <div className="flex items-center gap-2 font-['JetBrains_Mono']">
              <span className="text-zinc-400 text-xs">Seçim:</span>
              <span className="text-zinc-100 font-bold text-sm">{sig.selLabel}</span>
            </div>
            <div className="flex items-center gap-2 font-['JetBrains_Mono']">
              <span className="text-zinc-400 text-xs">Oran:</span>
              <span className="text-zinc-100 text-sm">{sig.odds}</span>
            </div>
            <div className="flex items-center gap-2 font-['JetBrains_Mono']">
              <span className="text-zinc-400 text-xs">%:</span>
              <span className="text-zinc-100 text-sm">{sig.pct}</span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-8 pt-4 border-t border-zinc-800/30">
          <MonoCell label="Para" orig={sig.amt} cur={sig.curAmt} />
          <MonoCell label="% Para" orig={sig.pctAmt} cur={sig.curPctAmt} />
          <MonoCell label="Hacim" orig={sig.vol} cur={sig.curVol} />
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

export function Minimal() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] font-['Inter'] text-zinc-300 py-12 px-6 sm:px-12 selection:bg-zinc-800">
      <div className="max-w-[520px] mx-auto">
        <header className="mb-10 px-6">
          <h1 className="text-zinc-500 font-['Space_Grotesk'] tracking-tight mb-2 flex items-center gap-2">
            <div className="w-4 h-[1px] bg-zinc-700" /> 
            Minimal Mono Variant
          </h1>
          <p className="text-zinc-400 text-sm">Quietly confident, terminal-inspired.</p>
        </header>

        <div className="flex flex-col gap-10">
          {samples.map((s) => (
            <div key={s.label}>
              <div className="px-6 mb-2">
                <h2 className="text-[10px] font-bold text-zinc-500 uppercase tracking-[0.2em]">
                  {s.label}
                </h2>
              </div>
              <SignalCard sig={s.sig} kind={s.kind} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
