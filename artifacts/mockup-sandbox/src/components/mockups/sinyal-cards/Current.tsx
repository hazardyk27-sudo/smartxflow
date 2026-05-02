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

function CmpCell({ label, orig, cur }: { label: string; orig: string; cur?: string }) {
  if (!orig) return null;
  const oNum = parseFloat(String(orig).replace(/[^0-9.]/g, ""));
  const cNum = cur ? parseFloat(String(cur).replace(/[^0-9.]/g, "")) : NaN;
  let arrow = "", aColor = "#7d848c";
  if (cur && cur !== orig && !isNaN(oNum) && !isNaN(cNum)) {
    if (cNum > oNum) { arrow = "↑"; aColor = "#34d399"; }
    else if (cNum < oNum) { arrow = "↓"; aColor = "#f85149"; }
  }
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 9, color: "#7d848c", whiteSpace: "nowrap" }}>
      <span style={{ color: "#5b6168" }}>{label}</span>
      <span style={{ color: "#a0a8b0", fontWeight: 600 }}>{orig}</span>
      {cur && cur !== orig && (
        <>
          <span style={{ color: aColor, fontSize: 10 }}>{arrow}</span>
          <span style={{ color: aColor, fontWeight: 600 }}>{cur}</span>
        </>
      )}
    </div>
  );
}

function SignalCard({ sig, kind }: { sig: Sig; kind: keyof typeof palette }) {
  const p = palette[kind];
  const isStale = !!sig.isStale;
  const cardBorder = isStale ? "rgba(120,120,120,0.18)" : p.cardBorder;
  const cardOpacity = isStale ? 0.55 : 1;
  return (
    <div style={{ background: "#1c1f23", border: `1px solid ${cardBorder}`, borderRadius: 10, padding: "12px 16px", marginBottom: 8, opacity: cardOpacity }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", marginBottom: 2 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "#e0e4e8", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {sig.home_team} - {sig.away_team}{" "}
              <span style={{ display: "inline-block", fontSize: 9, background: "rgba(88,166,255,0.1)", color: "#58a6ff", border: "1px solid rgba(88,166,255,0.25)", borderRadius: 4, padding: "1px 5px", fontWeight: 700, letterSpacing: "0.3px", cursor: "pointer", verticalAlign: "middle" }}>
                İNCELE ↗
              </span>
            </div>
            {isStale && (
              <span style={{ background: "rgba(180,83,9,0.15)", color: "#f97316", border: "1px solid rgba(249,115,22,0.3)", borderRadius: 4, padding: "2px 6px", fontSize: 9, fontWeight: 700, letterSpacing: "0.3px" }}>
                ↓ ZAYIFLADI
              </span>
            )}
            {sig.hoursBefore && (
              <span style={{ background: "rgba(125,132,140,0.10)", color: "#7d848c", border: "1px solid rgba(125,132,140,0.20)", borderRadius: 4, padding: "1px 5px", fontSize: 9, fontWeight: 600 }}>
                {sig.hoursBefore}
              </span>
            )}
          </div>
          <div style={{ fontSize: 10, color: "#484f58", marginBottom: 5 }}>{sig.league}</div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <CmpCell label="Para:" orig={sig.amt} cur={sig.curAmt} />
            <CmpCell label="% Para:" orig={sig.pctAmt} cur={sig.curPctAmt} />
            <CmpCell label="Hacim:" orig={sig.vol} cur={sig.curVol} />
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 4, flexShrink: 0 }}>
          <div style={{ display: "flex", gap: 4 }}>
            <span style={{ background: p.bg, color: p.color, border: `1px solid ${p.border}`, borderRadius: 6, padding: "3px 8px", fontSize: 11, fontWeight: 700 }}>{sig.selLabel}</span>
            <span style={{ background: "rgba(88,166,255,0.06)", color: "#93c5fd", border: "1px solid rgba(88,166,255,0.12)", borderRadius: 6, padding: "3px 8px", fontSize: 11, fontWeight: 600 }}>{sig.odds}</span>
            <span style={{ background: "rgba(52,211,153,0.06)", color: "#34d399", border: "1px solid rgba(52,211,153,0.12)", borderRadius: 6, padding: "3px 8px", fontSize: 11, fontWeight: 600 }}>{sig.pct}</span>
            {sig.score && (
              <span style={{ background: "rgba(255,255,255,0.04)", color: "#7d848c", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 6, padding: "3px 8px", fontSize: 11, fontWeight: 600, letterSpacing: "0.5px" }}>
                {sig.score}
              </span>
            )}
          </div>
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

export function Current() {
  return (
    <div style={{ minHeight: "100vh", background: "#0d1117", padding: "24px 20px", fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' }}>
      <div style={{ maxWidth: 480, margin: "0 auto" }}>
        <div style={{ fontSize: 11, color: "#5b6168", textTransform: "uppercase", letterSpacing: "1.2px", marginBottom: 12, fontWeight: 600 }}>
          Mevcut Tasarım — Sinyal Kartları
        </div>
        {samples.map((s) => (
          <div key={s.label}>
            <div style={{ fontSize: 10, color: "#484f58", textTransform: "uppercase", letterSpacing: "0.8px", margin: "10px 0 4px 2px", fontWeight: 600 }}>
              {s.label}
            </div>
            <SignalCard sig={s.sig} kind={s.kind} />
          </div>
        ))}
      </div>
    </div>
  );
}
