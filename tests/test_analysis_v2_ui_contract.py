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


def test_renderer_uses_read_only_v2_feed_and_exact_detail():
    js = read("static/js/analysis_v2.js")
    assert "/api/analysis-v2/signals?" in js
    assert "/api/analysis-v2/signals/${encodeURIComponent(signalId)}" in js
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


def test_history_scope_and_detail_drawer_are_exposed():
    html = read("templates/analysis_v2.html")
    assert 'data-scope="active"' in html
    assert 'data-scope="history"' in html
    assert 'data-scope="all"' in html
    assert 'id="signalSearch"' in html
    assert 'id="marketFilter"' in html
    assert 'id="signalDetailDrawer"' in html
    assert 'id="loadMoreBtn"' in html


def test_app_detail_endpoint_is_exact_signal_id_read_only():
    app = read("app.py")
    assert "@app.route('/api/analysis-v2/signals/<signal_id>', methods=['GET'])" in app
    assert "r'sig_[0-9a-f]{32}'" in app
    assert "analysis_v2_signal_state_events" in app
    assert "analysis_v2_signal_settlements" in app
    assert "present_signal_detail" in app


def test_feed_endpoint_supports_safe_scope_market_and_offset():
    app = read("app.py")
    assert "scope not in {'active', 'history', 'all'}" in app
    assert "requested_market not in {'1X2', 'DNB', 'DC', 'OU25', 'BTTS'}" in app
    assert "requested_offset" in app
    assert "payload['has_more']" in app



def test_runtime_hook_is_disabled_by_default_and_isolated_from_v1():
    env = read(".env.example")
    scraper = read("betwatch_prematch.py")
    assert "ANALYSIS_V2_RUNTIME_ENABLED=0" in env
    assert 'os.environ.get("ANALYSIS_V2_RUNTIME_ENABLED", "0")' in scraper
    assert "Analysis V2 runtime isolated error" in scraper
    assert "run_runtime_batch(" in scraper
