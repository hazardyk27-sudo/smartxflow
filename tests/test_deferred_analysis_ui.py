from pathlib import Path


def _index():
    return Path('templates/index.html').read_text()


def test_guide_ui_is_removed_from_the_app():
    text = _index()
    assert 'onclick="openDeferredTrendsModal(\\'moves\\')' not in text
    assert 'id="trendsModalOverlay"' not in text
    assert 'data-i18n="idx.nav.kilavuz"' not in text
    assert 'Kılavuz' not in text
    assert 'var analysisUiUrl' not in text
    assert 'window.loadSxfAnalysisUi' not in text


def test_signal_engine_keeps_its_lazy_entrypoint():
    text = _index()
    assert 'window.loadSxfBaseSignalsUi = function ()' in text
    assert 'window.openDeferredTrendsModal = function ()' in text
    assert 'return window.openBaseSignalsPanel();' in text
    assert 'onclick="_testGuardAnalysis(this)"' in text
