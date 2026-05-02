import React from "react";
import { ArrowUp, ArrowDown, ArrowUpRight, Clock, AlertTriangle } from "lucide-react";

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
  underdog: {
    base: "#d29922",
    gradient: "from-[#d29922] to-[#eab308]",
  },
  cmoney: {
    base: "#34d399",
    gradient: "from-[#34d399] to-[#10b981]",
  },
  cmoneyV2: {
    base: "#6366f1",
    gradient: "from-[#6366f1] to-[#818cf8]",
  },
  early: {
    base: "#58a6ff",
    gradient: "from-[#58a6ff] to-[#3b82f6]",
  },
  fake: {
    base: "#f85149",
    gradient: "from-[#f85149] to-[#ef4444]",
  },
};

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

function MetricCell({ label, orig, cur }: { label: string; orig: string; cur?: string }) {
  if (!orig) return null;
  const oNum = parseFloat(String(orig).replace(/[^0-9.-]/g, ""));
  const cNum = cur ? parseFloat(String(cur).replace(/[^0-9.-]/g, "")) : NaN;
  
  let arrow = null;
  let arrowColor = "text-neutral-500";
  
  if (cur && cur !== orig && !isNaN(oNum) && !isNaN(cNum)) {
    if (cNum > oNum) {
      arrow = <ArrowUp className="w-3 h-3 text-emerald-400" strokeWidth={3} />;
    } else if (cNum < oNum) {
      arrow = <ArrowDown className="w-3 h-3 text-rose-400" strokeWidth={3} />;
    }
  }

  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] font-medium tracking-wide text-white/40 uppercase">{label}</span>
      <div className="flex items-center gap-1.5 font-['Space_Grotesk'] text-xs tracking-tight">
        <span className="text-white/60 line-through decoration-white/20">{orig}</span>
        {cur && cur !== orig && (
          <div className="flex items-center gap-0.5">
            {arrow}
            <span className="text-white/90 font-medium">{cur}</span>
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
    <div className={`relative group transition-all duration-300 ${isStale ? "opacity-60 grayscale-[0.3]" : "hover:-translate-y-0.5"}`}>
      {/* Background with glass effect */}
      <div className="absolute inset-0 rounded-xl bg-white/[0.02] backdrop-blur-xl border border-white/[0.05] group-hover:bg-white/[0.04] transition-colors duration-300 overflow-hidden">
        {/* Subtle inner glow */}
        <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-white/[0.08] to-transparent" />
      </div>

      {/* Vertical left accent edge */}
      <div className={`absolute top-0 bottom-0 left-0 w-[3px] rounded-l-xl bg-gradient-to-b ${p.gradient} opacity-80 group-hover:opacity-100 transition-opacity`} />
      {/* Ambient shadow from left edge */}
      <div className={`absolute top-0 bottom-0 left-0 w-8 bg-gradient-to-r ${p.gradient} blur-xl opacity-[0.03] group-hover:opacity-[0.06] transition-opacity pointer-events-none`} />

      <div className="relative p-4 flex flex-col gap-4 pl-5">
        
        {/* Header section */}
        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="font-['Space_Grotesk'] text-sm font-semibold text-white/90 tracking-tight">
                {sig.home_team} <span className="text-white/30 font-normal mx-0.5">—</span> {sig.away_team}
              </h3>
              
              <button className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-bold tracking-widest text-white/50 hover:text-white/90 bg-white/5 hover:bg-white/10 transition-colors uppercase cursor-pointer">
                İNCELE <ArrowUpRight className="w-2.5 h-2.5" />
              </button>

              {isStale && (
                <div className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-400 text-[9px] font-bold tracking-widest uppercase border border-rose-500/20">
                  <AlertTriangle className="w-2.5 h-2.5" />
                  ZAYIFLADI
                </div>
              )}

              {sig.hoursBefore && (
                <div className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-white/5 text-white/50 text-[10px] font-medium border border-white/5">
                  <Clock className="w-2.5 h-2.5" />
                  {sig.hoursBefore}
                </div>
              )}
            </div>
            
            <p className="text-[11px] text-white/40 font-medium tracking-wide">
              {sig.league}
            </p>
          </div>

          <div className="flex flex-col items-end gap-1.5 shrink-0">
            {/* Main Selection Badge */}
            <div 
              className="flex items-center justify-center min-w-[32px] px-2 h-7 rounded-lg font-['Space_Grotesk'] font-bold text-sm shadow-sm"
              style={{ backgroundColor: p.base, color: '#000' }}
            >
              {sig.selLabel}
            </div>
            
            {/* Odds & Pct */}
            <div className="flex items-center gap-1">
              <span className="px-1.5 py-0.5 rounded-md bg-white/5 border border-white/10 text-[11px] font-['Space_Grotesk'] font-semibold text-white/80">
                {sig.odds}
              </span>
              <span className="px-1.5 py-0.5 rounded-md bg-white/5 border border-white/10 text-[11px] font-['Space_Grotesk'] font-semibold text-white/80">
                {sig.pct}
              </span>
              {sig.score && (
                <span className="px-1.5 py-0.5 rounded-md bg-white/5 border border-white/10 text-[11px] font-['Space_Grotesk'] font-semibold text-white/60">
                  {sig.score}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Divider */}
        <div className="w-full h-px bg-gradient-to-r from-white/[0.08] via-white/[0.03] to-transparent" />

        {/* Metrics Grid */}
        <div className="grid grid-cols-3 gap-2">
          <MetricCell label="Para:" orig={sig.amt} cur={sig.curAmt} />
          <MetricCell label="% Para:" orig={sig.pctAmt} cur={sig.curPctAmt} />
          <MetricCell label="Hacim:" orig={sig.vol} cur={sig.curVol} />
        </div>

      </div>
    </div>
  );
}

export function Glass() {
  return (
    <div className="min-h-screen bg-[#090a0c] p-6 font-['Manrope'] selection:bg-white/10 text-white flex justify-center">
      <div className="w-full max-w-[480px] flex flex-col gap-6">
        
        <header className="flex flex-col gap-1 mb-2 px-1">
          <h2 className="text-[10px] font-bold tracking-[0.2em] text-white/30 uppercase">
            Sinyal Kartları — Glass Premium
          </h2>
          <p className="text-xs font-medium text-white/50">
            Fintech-grade signal exploration.
          </p>
        </header>

        <div className="flex flex-col gap-6">
          {samples.map((s) => (
            <div key={s.label} className="flex flex-col gap-2.5">
              <div className="flex items-center gap-2 px-1">
                <div 
                  className="w-1.5 h-1.5 rounded-full" 
                  style={{ backgroundColor: palette[s.kind].base }} 
                />
                <h4 className="text-[11px] font-bold uppercase tracking-widest text-white/60">
                  {s.label}
                </h4>
              </div>
              <SignalCard sig={s.sig} kind={s.kind} />
            </div>
          ))}
        </div>
        
      </div>
    </div>
  );
}
