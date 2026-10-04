from pathlib import Path

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
