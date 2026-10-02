from pathlib import Path

from analysis_v2.presenter import (
    COMPONENT_LABELS,
    STATE_META,
    UI_CONTRACT_VERSION,
)


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_ui_contract_has_three_user_states():
    assert set(STATE_META) >= {
        "FIRSAT",
        "IZLE",
        "UZAK_DUR",
    }


def test_ui_contract_has_six_explainable_components():
    assert list(COMPONENT_LABELS) == [
        "price_confirmation",
        "money_flow",
        "timing",
        "cross_market",
        "poly",
        "risk",
    ]


def test_v2_template_explains_core_price_money_rule():
    html = read("templates/analysis_v2.html")
    assert "Piyasa ne söylüyor?" in html
    assert "Para geldi → oran düştü → piyasa teyit etti." in html
    assert "Yüksek para yüzdesi tek başına güçlü sinyal değildir." in html


def test_v2_template_exposes_beginner_status_guide():
    html = read("templates/analysis_v2.html")
    assert "FIRSAT" in html
    assert "İZLE" in html
    assert "UZAK DUR" in html
    assert "NEDEN?" not in html  # card details are rendered from the real feed


def test_renderer_has_three_detail_surfaces_and_no_demo_signals():
    js = read("static/js/analysis_v2.js")
    assert "<summary>NEDEN?</summary>" in js
    assert "<summary>RİSKLER</summary>" in js
    assert "<summary>DETAYLAR</summary>" in js
    assert "Arayüz sahte/demo sinyal üretmez." in js
    assert "demoSignals" not in js
    assert "mockSignals" not in js


def test_renderer_uses_read_only_v2_feed():
    js = read("static/js/analysis_v2.js")
    assert "fetch('/api/analysis-v2/signals?limit=100'" in js
    assert "method: 'POST'" not in js
    assert 'method: "POST"' not in js
    assert "method: 'PATCH'" not in js
    assert "method: 'DELETE'" not in js


def test_app_exposes_separate_v2_page_and_read_only_api():
    app = read("app.py")
    assert "@app.route('/analysis-v2')" in app
    assert "@app.route('/api/analysis-v2/signals', methods=['GET'])" in app
    assert "present_signal_rows(rows)" in app
    assert "V2_LEDGER_NOT_DEPLOYED" in app


def test_existing_analysis_page_links_to_v2_without_replacing_v1():
    html = read("templates/analysis.html")
    assert 'href="/analysis-v2">Analizler V2</a>' in html
    assert 'href="/analysis" class="active"' in html


def test_contract_version_is_explicit():
    assert UI_CONTRACT_VERSION == "analysis-v2-ui-1.0.0"
