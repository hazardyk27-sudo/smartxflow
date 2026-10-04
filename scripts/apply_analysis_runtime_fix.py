#!/usr/bin/env python3
"""One-shot exact patch for scraper coordination and Analysis signal copy."""
from pathlib import Path


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 occurrence, got {count}")
    return text.replace(old, new, 1)


# --- scheduled scraper: keep Preview passive while production is healthy ---
p = Path("scheduled_scraper.py")
text = p.read_text(encoding="utf-8")
text = one(
    text,
    "SIGNAL_DEDUP_WINDOW_SECONDS = 120\n_SIGNAL_LOCK_PATH",
    "SIGNAL_DEDUP_WINDOW_SECONDS = 120\nEXTERNAL_MASTER_WINDOW_SECONDS = int(os.environ.get(\"SMARTXFLOW_EXTERNAL_MASTER_WINDOW_SECONDS\", \"720\"))\n_SIGNAL_LOCK_PATH",
    "external master window constant",
)
text = one(
    text,
    "        diff_minutes = (datetime.now(timezone.utc) - beat_time.astimezone(timezone.utc)).total_seconds() / 60\n        if 0 <= diff_minutes < 5:\n            return False, f\"{row.get('source', 'external')} recent scrape ({diff_minutes:.1f} min ago)\"\n        return True, f\"signal_fallback_stale ({diff_minutes:.1f} min ago)\"",
    "        diff_seconds = (datetime.now(timezone.utc) - beat_time.astimezone(timezone.utc)).total_seconds()\n        diff_minutes = diff_seconds / 60\n        if 0 <= diff_seconds < EXTERNAL_MASTER_WINDOW_SECONDS:\n            return False, f\"{row.get('source', 'external')} recent scrape ({diff_minutes:.1f} min ago)\"\n        return True, f\"signal_fallback_stale ({diff_minutes:.1f} min ago)\"",
    "external master freshness window",
)
text = one(
    text,
    '    """Aynı scrape sayılarıyla çok kısa sürede ikinci signal üretimini engelle."""',
    '    """Herhangi bir kaynaktan yeni scrape_complete varsa ikinci signal üretimini engelle."""',
    "dedupe docstring",
)
text = one(
    text,
    '            f"?source=eq.{SCRAPER_SOURCE}"\n            f"&signal_type=eq.scrape_complete"',
    '            f"?signal_type=eq.scrape_complete"',
    "cross-source dedupe query",
)
text = one(
    text,
    '        if int(row.get("match_count") or 0) != int(match_count):\n            return False\n        if int(row.get("snapshot_count") or 0) != int(snapshot_count):\n            return False\n',
    "",
    "remove count-dependent dedupe",
)
text = one(
    text,
    '    """Supabase\'den son başarılı replit scrape_complete sinyal zamanını al."""',
    '    """Supabase\'den herhangi bir kaynağın son başarılı scrape_complete zamanını al."""',
    "last signal docstring",
)
text = one(
    text,
    '            f"{supabase_url}/rest/v1/scraper_signal?source=eq.replit"\n            f"&signal_type=eq.scrape_complete&order=created_at.desc&limit=1&select=created_at"',
    '            f"{supabase_url}/rest/v1/scraper_signal?signal_type=eq.scrape_complete"\n            f"&order=created_at.desc&limit=1&select=created_at"',
    "last signal cross-source query",
)
p.write_text(text, encoding="utf-8")


# --- Sinyal Engine header documentation: mirror actual live constants ---
p = Path("sinyal_engine.py")
text = p.read_text(encoding="utf-8")
old_intro = """SmartXFlow Sinyal Engine v1.3
İki sinyal tipini aynı anda tarar:
  1. Underdog Pressure: odds >= 2.90, pct >= 50%, volume >= £2,000
  2. Confirmed Money: pct > 80%, oran >= %4 düşüş (10 saat), volume >= £2,000, stabilite onaylı
"""
new_intro = """SmartXFlow Sinyal Engine v1.3
Beş sinyal tipini aynı anda tarar:
  1. Underdog Pressure: odds >= 2.90; volume £800-£4,999 ise pct >= 55%, volume >= £5,000 ise pct >= 50%; sadece 1/2
  2. Confirmed Money: volume >= £5,000, pct > 80% son 3 snapshot, odds 1.35-2.20, ilk geçerli orana göre >= %5 düşüş
  3. Confirmed Money V2: volume >= £5,000, pct >= 88% son 3 snapshot, odds 1.55-2.20, >= %7 düşüş; sadece 1/2
  4. Fake Sharp: volume >= £5,000, pct > 75% son 3 snapshot, odds 1.35-2.20, ilk geçerli orana göre >= %5 yükseliş; sadece 1/2
  5. Early Money Lock: kickoff >= 24 saat, volume >= £5,000, aynı seçimde 5 ardışık snapshot pct >= 85%
"""
text = one(text, old_intro, new_intro, "signal engine header")
p.write_text(text, encoding="utf-8")


# --- Analysis detail pages: use the same i18n keys as the overview cards ---
TR = {
    "rv_underdog_desc": "Oran ≥2.90. Hacim £800–£4.999 ise para yüzdesi ≥%55; hacim ≥£5.000 ise ≥%50. Yalnız 1/2 seçimleri.",
    "rv_confirmed_desc": "Hacim ≥£5.000, para yüzdesi >%80 ve son 3 snapshot boyunca >%80; oran 1.35–2.20 ve ilk geçerli orana göre ≥%5 düşüş.",
    "rv_confirmed_v2_desc": "Hacim ≥£5.000, para yüzdesi ≥%88 ve son 3 snapshot boyunca ≥%88; oran 1.55–2.20 ve ilk geçerli orana göre ≥%7 düşüş. Yalnız 1/2 seçimleri.",
    "rv_early_desc": "Maça ≥24 saat kala, hacim ≥£5.000 ve aynı seçimde son 5 ardışık snapshot boyunca para yüzdesi ≥%85 olduğunda tetiklenir.",
    "rv_fake_desc": "Hacim ≥£5.000 ve para yüzdesi >%75 iken son 3 snapshot da >%75; oran 1.35–2.20 ve ilk geçerli orana göre ≥%5 yükseliyorsa tetiklenir. Yalnız 1/2 seçimleri.",
}
old_copy = {
    "rv_underdog_desc": "Oran ≥ 3.00 olan underdog tarafa para akışının ≥ %50 olduğu bugün/gelecek maçları tespit eder.",
    "rv_confirmed_desc": "Para akışı ≥%80, oran 16 saat içinde monoton düşen (≥%4), hacim ≥£2,000 olan maçları tespit eder.",
    "rv_confirmed_v2_desc": "Para akışı ≥%88, oran 1.55-2.20, ≥%7 düşüş — 3 günlük araştırmada sıfır kayıp. Sadece 1/2 seçimleri.",
    "rv_early_desc": "Para akışı erken kilitlenmiş ve birbirini izleyen anlık görüntülerde sabit kalan maçları tespit eder.",
    "rv_fake_desc": "Para akışına rağmen oran yükselen — yani sharp olmayan, halk parası olduğu anlaşılan maçları tespit eder.",
}
p = Path("static/js/inline.js.src")
text = p.read_text(encoding="utf-8")
for key, old in old_copy.items():
    expression = "' + _t('app.j.%s','%s') + '" % (key, TR[key])
    text = one(text, old, expression, f"detail copy {key}")
p.write_text(text, encoding="utf-8")


# --- Regression coverage ---
p = Path("tests/test_runtime_scraper_recovery.py")
text = p.read_text(encoding="utf-8")
marker = "def test_send_signal_skips_recent_duplicate(monkeypatch):\n"
new_test = '''def test_master_fallback_keeps_preview_standby_for_nine_minute_external_signal(monkeypatch):
    mod = _load_scheduled_scraper_with_stubs(monkeypatch)
    mod.SCRAPER_SOURCE = "replit-preview"
    mod._HEARTBEAT_TABLE_AVAILABLE = False
    created_at = (datetime.now(timezone.utc) - timedelta(minutes=9)).isoformat()

    response = Mock()
    response.status_code = 200
    response.json.return_value = [{"source": "replit", "created_at": created_at}]
    monkeypatch.setattr(mod.requests, "get", Mock(return_value=response))

    is_master, reason = mod.check_master_status("https://example.supabase.co", "key")
    assert is_master is False
    assert "recent scrape" in reason


'''
if new_test.strip() not in text:
    text = one(text, marker, new_test + marker, "nine-minute master test")
old_fixture = '''    monkeypatch.setattr(mod, "fcntl", None)

    response = Mock()
    response.status_code = 200
    response.json.return_value = [
        {
            "id": 101,
            "created_at": (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(),
            "match_count": 614,
            "snapshot_count": 1327,
        }
    ]'''
new_fixture = '''    monkeypatch.setattr(mod, "fcntl", None)
    mod.SCRAPER_SOURCE = "replit-preview"

    response = Mock()
    response.status_code = 200
    response.json.return_value = [
        {
            "id": 101,
            "source": "replit",
            "created_at": (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(),
            "match_count": 3186,
            "snapshot_count": 3186,
        }
    ]'''
text = one(text, old_fixture, new_fixture, "cross-source duplicate fixture")
p.write_text(text, encoding="utf-8")

copy_test = Path("tests/test_analysis_signal_copy.py")
copy_test.write_text('''from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXPECTED = {
    "rv_underdog_desc": "Oran ≥2.90. Hacim £800–£4.999 ise para yüzdesi ≥%55; hacim ≥£5.000 ise ≥%50. Yalnız 1/2 seçimleri.",
    "rv_confirmed_desc": "Hacim ≥£5.000, para yüzdesi >%80 ve son 3 snapshot boyunca >%80; oran 1.35–2.20 ve ilk geçerli orana göre ≥%5 düşüş.",
    "rv_confirmed_v2_desc": "Hacim ≥£5.000, para yüzdesi ≥%88 ve son 3 snapshot boyunca ≥%88; oran 1.55–2.20 ve ilk geçerli orana göre ≥%7 düşüş. Yalnız 1/2 seçimleri.",
    "rv_early_desc": "Maça ≥24 saat kala, hacim ≥£5.000 ve aynı seçimde son 5 ardışık snapshot boyunca para yüzdesi ≥%85 olduğunda tetiklenir.",
    "rv_fake_desc": "Hacim ≥£5.000 ve para yüzdesi >%75 iken son 3 snapshot da >%75; oran 1.35–2.20 ve ilk geçerli orana göre ≥%5 yükseliyorsa tetiklenir. Yalnız 1/2 seçimleri.",
}
RETIRED = (
    "Oran ≥ 3.00 olan underdog",
    "oran 16 saat içinde monoton düşen (≥%4), hacim ≥£2,000",
    "3 günlük araştırmada sıfır kayıp",
    "Para akışı erken kilitlenmiş ve birbirini izleyen",
    "sharp olmayan, halk parası olduğu anlaşılan",
)


def test_overview_rule_overrides_match_current_engine_rules():
    i18n = (ROOT / "static/js/i18n.js").read_text(encoding="utf-8")
    for key, value in EXPECTED.items():
        assert f"'app.j.{key}': '{value}'" in i18n


def test_detail_views_use_rule_keys_and_contain_no_retired_copy():
    src = (ROOT / "static/js/inline.js.src").read_text(encoding="utf-8")
    for key in EXPECTED:
        assert f"_t('app.j.{key}'" in src
    for retired in RETIRED:
        assert retired not in src
''', encoding="utf-8")

# Fold the new copy regression into existing Preview CI.
p = Path(".github/workflows/alarm-rule-tests.yml")
text = p.read_text(encoding="utf-8")
text = one(
    text,
    "      - 'tests/test_sinyal_engine_runtime.py'\n      - '.github/workflows/alarm-rule-tests.yml'",
    "      - 'tests/test_sinyal_engine_runtime.py'\n      - 'tests/test_analysis_signal_copy.py'\n      - 'static/js/inline.js.src'\n      - 'static/js/i18n.js'\n      - '.github/workflows/alarm-rule-tests.yml'",
    "alarm CI paths",
)
text = one(
    text,
    "          tests/test_runtime_scraper_recovery.py\n          tests/test_sinyal_engine_runtime.py\n",
    "          tests/test_runtime_scraper_recovery.py\n          tests/test_sinyal_engine_runtime.py\n          tests/test_analysis_signal_copy.py\n",
    "alarm CI tests",
)
p.write_text(text, encoding="utf-8")

print("analysis runtime patch applied")
