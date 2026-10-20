"""Seven-locale admin static-text coverage and protected technical literals.

Covers author-visible static HTML only; dynamic admin JS is separately tracked.
The excluded phrases are codes, source names, maths or literal example data.
"""
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LANGS=("tr","en","de","fr","nl","it","es")
UNTRANSLATABLE={
  "SmartXFlow Admin Panel","SmartXFlow","Supabase","CORE","PRO","Sharp Money",
  "Moneyway 1X2","Moneyway O/U 2.5","Moneyway BTTS",
  "Dropping 1X2","Dropping O/U 2.5","Dropping BTTS",
  "SHARP SCORE = Volume_Contrib + Odds_Contrib + Share_Contrib",
  "(amt1 + amtx + amt2)","&nbsp;&nbsp;&nbsp;&nbsp;├──","&nbsp;&nbsp;&nbsp;&nbsp;└──",
  "amount_change = curr_amt - prev_amt",
  "shock_raw = amount_change / avg_prev_5",
  "shock_value = shock_raw × volume_multiplier",
  "volume_contrib = min(shock_value, 40)",
  "drop_pct = ((prev_odds - curr_odds) / prev_odds) × 100",
  "odds_value = drop_pct × odds_multiplier",
  "odds_contrib = min(odds_value, 35)",
  "share_diff = curr_share - prev_share",
  "share_value = share_diff × share_multiplier",
  "share_contrib = min(share_value, 25)",
  "= min_share (%5)","= min_drop_threshold","= min_sharp_score",
  "Arsenal vs Chelsea |","1 (Arsenal)",
  "Odds=1.85, Share=42%, Amount=£5000",
  "Odds=1.72, Share=48%, Amount=£8500",
  "min(0.7, 40) = 0.7","min(56.2, 35) = 35","min(6, 25) = 6",
  "&times;","Europe/Istanbul (TR)","Supabase (PostgreSQL)","arbworld.net",
}
def flatten(obj):
    for value in obj.values():
        if isinstance(value,dict):
            yield from flatten(value)
        elif isinstance(value,str):
            yield " ".join(value.split())
def test_admin_exact_source_ui_coverage():
    html=(ROOT/"templates/admin.html").read_text(encoding="utf-8")
    html=re.sub(r"<script\b[^>]*>[\s\S]*?</script>","",html,flags=re.I)
    html=re.sub(r"<style\b[^>]*>[\s\S]*?</style>","",html,flags=re.I)
    candidates={
        " ".join(match.group(1).split())
        for match in re.finditer(r">\s*([^<>\n]{2,200})\s*<",html)
        if re.search(r"[A-Za-zğüşöçİĞÜŞÖÇ]",match.group(1))
        and "{{" not in match.group(1) and "{%" not in match.group(1)
    }
    assert len(candidates)>=480, "Admin source inspection unexpectedly incomplete"
    admin=json.loads((ROOT/"static/i18n/admin.json").read_text(encoding="utf-8"))
    baseline=json.loads((ROOT/"static/i18n/tr.json").read_text(encoding="utf-8"))
    sources=set(flatten(baseline)) | set(admin["tr"].values())
    missing=candidates-sources-UNTRANSLATABLE
    assert not missing, f"New untranslated admin labels: {sorted(missing)}"
    for lang in LANGS:
        assert set(admin[lang])==set(admin["tr"]),f"{lang} missing admin keys"
        assert len(admin[lang])>=430
        assert all(isinstance(x,str) and x.strip() for x in admin[lang].values())
    # Keep the template's immutable numerical formulas, IDs and source labels
    # exactly as written: translating them could corrupt admin documentation.
    for token in ("volume_contrib = min(shock_value, 40)",
                  "SHARP SCORE = Volume_Contrib + Odds_Contrib + Share_Contrib",
                  "Europe/Istanbul (TR)"):
        assert token in html
