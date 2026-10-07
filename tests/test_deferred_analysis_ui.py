from pathlib import Path


def _index():
    return Path('templates/index.html').read_text()


def test_analysis_ui_is_not_eagerly_loaded():
    text = _index()
    assert '<script defer src="/static/js/ui.js' not in text
    assert "var analysisUiUrl = '/static/js/ui.js?v={{ asset_v(\"js/ui.js\") }}';" in text


def test_analysis_buttons_use_lazy_entrypoint():
    text = _index()
    assert 'onclick="openTrendsModal(' not in text
    assert text.count('onclick="openDeferredTrendsModal(') >= 2


def test_lazy_loader_is_single_flight_and_retryable():
    text = _index()
    assert 'if (analysisUiPromise) return analysisUiPromise;' in text
    assert 'analysisUiPromise = null;' in text
    assert "document.createElement('script')" in text
    assert 'document.head.appendChild(script);' in text


def test_lazy_entrypoint_calls_real_modal_after_bundle_loads():
    text = _index()
    start = text.index('window.openDeferredTrendsModal = function')
    end = text.index('})();', start)
    block = text[start:end]
    assert 'window.loadSxfAnalysisUi()' in block
    assert "typeof window.openTrendsModal !== 'function'" in block
    assert 'return window.openTrendsModal(tab);' in block
