"""The old /app Analizler modal is bypassed by an isolated V3 signal panel."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_analizler_launches_new_modal_but_guide_keeps_its_entrypoint():
    html=(ROOT/"templates/index.html").read_text()
    assert "window.loadSxfBaseSignalsUi = function ()" in html
    assert "if (tab === 'analysis')" in html
    assert "return window.openBaseSignalsPanel();" in html
    assert "return window.openTrendsModal(tab);" in html  # Guide only
    assert html.index("if (tab === 'analysis')") < html.index("return window.loadSxfAnalysisUi()")
    assert html.count('onclick="openDeferredTrendsModal(\'moves\')') >= 1
    assert "id=\"sxfBaseSignalOverlay\"" in html
    assert "id=\"sxfSignalDateRail\"" in html
    assert "id=\"sxfSignalEngineRail\"" not in html
    assert "id=\"sxfSearchWrap\"" in html
    assert "id=\"sxfSignalContent\"" in html
    assert "js/base-signals.js" in html and "css/base-signals.css" in html


def test_new_analizler_cards_are_not_mocks_or_old_analysts():
    ui=(ROOT/"static/js/base-signals.js").read_text()
    assert "fetch('/api/base-signals/feed?start='" in ui
    assert 'window.openBaseSignalsPanel = open' in ui
    assert "Europe/Istanbul" in ui
    assert "source_checkpoint" in ui and "sxf-signal-card" in ui
    assert "SHADOW" in ui
    assert "renderDates()" in ui and "renderHome()" in ui and "renderDetail()" in ui
    assert "engineCard(name)" in ui and "fixtureCard(rows)" in ui
    assert "data-motor" in ui and "current.engine = btn.dataset.motor" in ui
    assert "current.engine = null" in ui and "sxfSignalBack" in ui
    for legacy in ("analyst-card","/api/analyses","dummyMatch","MOCK_SIGNAL"):
        assert legacy not in ui
    css=(ROOT/"static/css/base-signals.css").read_text()
    assert ".sxf-signal-grid" in css and ".sxf-engine-grid" in css
    assert "var(--bg-main" in css and "var(--bg-card" in css
    assert ".sxf-engine-box" not in css
    assert "grid-template-columns:repeat(3,minmax(0,1fr))" in css
    assert "@media(max-width:700px)" in css
    assert "[hidden]" in css


def test_api_pro_gate_and_secrets_are_server_side():
    backend=(ROOT/"app.py").read_text()
    start=backend.index("@app.route('/api/base-signals/feed'")
    end=backend.index("_analyses_cache =",start)
    code=backend[start:end]
    assert "def base_signal_feed_api()" in code
    assert "PRO_REQUIRED" in code
    assert "resolve_account_session()" in code
    assert "_legacy_license_session_valid()" in code
    assert "SUPABASE_SERVICE_ROLE_KEY" in code
    assert "BaseSignalsFeed(" in code
    assert "/api/analyses?" not in code
    assert "return jsonify(result)" in code
    assert "SIGNAL_DATA_UNAVAILABLE" in code


def test_day_navigation_and_modal_accessibility():
    ui=(ROOT/"static/js/base-signals.js").read_text()
    html=(ROOT/"templates/index.html").read_text()
    for element in ("sxfSignalPrevious","sxfSignalNext","sxfSignalToday",
                    "sxfSignalRefresh","sxfSignalSearch","sxfSignalClose"):
        assert 'id="' + element + '"' in html
        assert "getElementById('" + element + "')" in ui
    assert 'aria-modal="true"' in html
    assert "role=\"tablist\"" in html
    assert "aria-selected" in ui
    assert "e.key === 'Escape'" in ui
    assert "encodeURIComponent(current.start)" in ui
