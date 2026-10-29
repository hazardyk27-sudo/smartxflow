"""The old /app Analizler modal is bypassed by an isolated V3 signal panel."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_analizler_keeps_signal_engine_and_removes_guide_entrypoints():
    html=(ROOT/"templates/index.html").read_text()
    assert "window.loadSxfBaseSignalsUi = function ()" in html
    assert "window.openDeferredTrendsModal = function ()" in html
    assert "return window.openBaseSignalsPanel();" in html
    assert "openDeferredTrendsModal('moves')" not in html
    assert "trendsModalOverlay" not in html
    assert "Kılavuz" not in html
    assert 'onclick="_testGuardAnalysis(this)"' in html
    assert 'id="sxfBaseSignalOverlay"' in html
    assert 'id="sxfSignalDateRail"' in html
    assert 'id="sxfSignalEngineRail"' not in html
    assert 'id="sxfSearchWrap"' in html
    assert 'id="sxfSignalContent"' in html
    assert "js/base-signals.js" in html and "css/base-signals.css" in html


def test_new_analizler_cards_are_not_mocks_or_old_analysts():
    ui=(ROOT/"static/js/base-signals.js").read_text()
    assert "fetch('/api/base-signals/feed?start='" in ui
    assert 'window.openBaseSignalsPanel = open' in ui
    assert "Europe/Istanbul" in ui
    assert "source_checkpoint" in ui and "sxf-signal-row" in ui
    assert "SHADOW" in ui
    assert "renderDates()" in ui and "renderHome()" in ui and "renderDetail()" in ui
    assert "engineCard(name)" in ui and "fixtureRow(rows)" in ui
    assert "data-motor" in ui and "current.engine = btn.dataset.motor" in ui
    assert "current.engine = null" in ui and "sxfSignalBack" in ui
    for legacy in ("analyst-card","/api/analyses","dummyMatch","MOCK_SIGNAL"):
        assert legacy not in ui
    css=(ROOT/"static/css/base-signals.css").read_text()
    assert ".sxf-signal-grid" in css and ".sxf-engine-grid" in css
    assert "var(--bg-main" in css and "var(--bg-card" in css
    assert ".sxf-engine-box" not in css
    assert "grid-template-columns:repeat(3,minmax(0,1fr))" in css
    assert "@media(max-width:600px)" in css
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
    assert "data-ruleset-mode" not in ui
    assert "archive" not in ui.split("function load()", 1)[1].split("function switchWindow", 1)[0]

def test_v4_app_native_responsive_design_contract():
    css=(ROOT/"static/css/base-signals.css").read_text()
    html=(ROOT/"templates/index.html").read_text()
    # Every color/base spacing treatment comes from /app's live variables.
    for token in ("--bg-main", "--bg-card", "--bg-card-soft", "--bg-section",
                  "--border-subtle", "--text-primary", "--text-secondary",
                  "--accent-green", "--accent-yellow", "--radius-md"):
        assert "var(" + token in css
    assert "grid-template-columns:repeat(3,minmax(0,1fr))" in css
    assert "@media(max-width:900px)" in css
    assert "grid-template-columns:repeat(2,minmax(0,1fr))" in css
    assert "@media(max-width:600px)" in css
    assert "grid-template-columns:1fr" in css
    assert "safe-area-inset-bottom" in css and "safe-area-inset-top" in css
    assert "height:100%" in css and "overflow-y:auto" in css
    assert "@media(max-height:560px)" in css
    assert "prefers-reduced-motion:reduce" in css
    assert "sxf-signal-date-rail" in css and "sxf-engine-grid" in css
    assert 'id="sxfBaseSignalTitle" data-i18n="app.v4.title">Sinyal Motoru</h2>' in html
    assert 'placeholder="Takım, lig veya tercih ara"' in html
    assert 'placeholder:app.v4.search_placeholder' in html
