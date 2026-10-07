#!/usr/bin/env python3
from pathlib import Path
import rjsmin

ROOT = Path(__file__).resolve().parents[1]
APP_SRC = ROOT / 'static/js/app.js.src'
APP_RUNTIME = ROOT / 'static/js/app.js'
EXPORT_SRC = ROOT / 'static/js/chart-export.js.src'
EXPORT_RUNTIME = ROOT / 'static/js/chart-export.js'
MINIFY = ROOT / 'minify.py'
FRONTEND_CI = ROOT / '.github/workflows/frontend-performance-tests.yml'
TEST_FILE = ROOT / 'tests/test_chart_export_code_split.js'

source = APP_SRC.read_text(encoding='utf-8')
runtime = APP_RUNTIME.read_text(encoding='utf-8')

# Fail closed: app.js may contain runtime-only repairs in this repository.
# Never regenerate it unless the current served bundle is exactly the current
# source minified by the canonical rjsmin pipeline.
current_generated = rjsmin.jsmin(source)
if current_generated != runtime:
    raise SystemExit(
        'Refusing P2.14 transformation: static/js/app.js differs from '
        'rjsmin(static/js/app.js.src). Reconcile source/runtime first.'
    )

start_marker = 'function generateExportFilename(extension) {'
end_marker = 'function toggleChartSeries(market, seriesKey, btn) {'
if source.count(start_marker) != 1 or source.count(end_marker) != 1:
    raise SystemExit('Expected exactly one chart export block boundary in app.js.src')

start = source.index(start_marker)
end = source.index(end_marker)
if end <= start:
    raise SystemExit('Invalid chart export block ordering')

export_block = source[start:end].rstrip()

deferred_source = """// Deferred chart export runtime. Loaded on first export action only.\n(function () {\n%s\n\nwindow.__sxfExportChartPNGImpl = exportChartPNG;\nwindow.__sxfExportChartCSVImpl = exportChartCSV;\nwindow.__sxfExportFullMatchTXTImpl = exportFullMatchTXT;\n})();\n""" % export_block

loader = r"""window._sxfChartExportRuntimePromise = window._sxfChartExportRuntimePromise || null;
function _getChartExportRuntimeUrl() {
    try {
        const scripts = document.getElementsByTagName('script');
        for (let i = scripts.length - 1; i >= 0; i--) {
            const src = scripts[i].src || '';
            if (src.indexOf('/static/js/app.js') !== -1) {
                const queryIndex = src.indexOf('?');
                const query = queryIndex >= 0 ? src.slice(queryIndex) : '';
                return '/static/js/chart-export.js' + query;
            }
        }
    } catch (e) {}
    return '/static/js/chart-export.js';
}

function loadChartExportRuntime() {
    const ready = typeof window.__sxfExportChartPNGImpl === 'function' &&
        typeof window.__sxfExportChartCSVImpl === 'function' &&
        typeof window.__sxfExportFullMatchTXTImpl === 'function';
    if (ready) return Promise.resolve();
    if (window._sxfChartExportRuntimePromise) return window._sxfChartExportRuntimePromise;

    window._sxfChartExportRuntimePromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = _getChartExportRuntimeUrl();
        script.async = true;
        script.onload = () => {
            const loaded = typeof window.__sxfExportChartPNGImpl === 'function' &&
                typeof window.__sxfExportChartCSVImpl === 'function' &&
                typeof window.__sxfExportFullMatchTXTImpl === 'function';
            if (loaded) {
                resolve();
                return;
            }
            window._sxfChartExportRuntimePromise = null;
            reject(new Error('Chart export runtime loaded without implementations'));
        };
        script.onerror = () => {
            window._sxfChartExportRuntimePromise = null;
            reject(new Error('Chart export runtime failed to load'));
        };
        document.head.appendChild(script);
    });
    return window._sxfChartExportRuntimePromise;
}

async function exportChartPNG(...args) {
    await loadChartExportRuntime();
    return window.__sxfExportChartPNGImpl(...args);
}

async function exportChartCSV(...args) {
    await loadChartExportRuntime();
    return window.__sxfExportChartCSVImpl(...args);
}

async function exportFullMatchTXT(...args) {
    await loadChartExportRuntime();
    return window.__sxfExportFullMatchTXTImpl(...args);
}

"""

new_source = source[:start] + loader + source[end:]
APP_SRC.write_text(new_source, encoding='utf-8')
EXPORT_SRC.write_text(deferred_source, encoding='utf-8')
APP_RUNTIME.write_text(rjsmin.jsmin(new_source), encoding='utf-8')
EXPORT_RUNTIME.write_text(rjsmin.jsmin(deferred_source), encoding='utf-8')

minify_text = MINIFY.read_text(encoding='utf-8')
chart_pair = "    ('static/js/chart-export.js.src', 'static/js/chart-export.js'),\n"
if chart_pair not in minify_text:
    anchor = "    ('static/js/app.js.src', 'static/js/app.js'),\n"
    if minify_text.count(anchor) != 1:
        raise SystemExit('Could not safely update minify.py chart-export pair')
    minify_text = minify_text.replace(anchor, anchor + chart_pair, 1)
    MINIFY.write_text(minify_text, encoding='utf-8')

ci_text = FRONTEND_CI.read_text(encoding='utf-8')
if "      - 'static/js/chart-export.js'\n" not in ci_text:
    anchor = "      - 'static/js/app.js.src'\n"
    if ci_text.count(anchor) != 1:
        raise SystemExit('Could not safely update frontend CI paths')
    ci_text = ci_text.replace(
        anchor,
        anchor + "      - 'static/js/chart-export.js'\n      - 'static/js/chart-export.js.src'\n",
        1,
    )
if "      - 'tests/test_chart_export_code_split.js'\n" not in ci_text:
    anchor = "      - 'tests/test_modal_chart_helper_split.js'\n"
    if ci_text.count(anchor) != 1:
        raise SystemExit('Could not safely update frontend CI test path')
    ci_text = ci_text.replace(anchor, anchor + "      - 'tests/test_chart_export_code_split.js'\n", 1)
if "          node --test tests/test_chart_export_code_split.js\n" not in ci_text:
    anchor = "          node --test tests/test_modal_chart_helper_split.js\n"
    if ci_text.count(anchor) != 1:
        raise SystemExit('Could not safely update frontend CI test command')
    ci_text = ci_text.replace(anchor, anchor + "          node --test tests/test_chart_export_code_split.js\n", 1)
FRONTEND_CI.write_text(ci_text, encoding='utf-8')

TEST_FILE.write_text(r'''const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.join(__dirname, '..');
const mainRuntime = fs.readFileSync(path.join(root, 'static/js/app.js'), 'utf8');
const mainSource = fs.readFileSync(path.join(root, 'static/js/app.js.src'), 'utf8');
const exportRuntime = fs.readFileSync(path.join(root, 'static/js/chart-export.js'), 'utf8');
const exportSource = fs.readFileSync(path.join(root, 'static/js/chart-export.js.src'), 'utf8');
const minifySource = fs.readFileSync(path.join(root, 'minify.py'), 'utf8');

const movedHelpers = [
  'generateExportFilename',
  'isEXEEnvironment',
  'showExportNotification',
  'savePNGViaAPI',
  'showExportOverlay',
  'removeExportOverlay',
  'exportChartPNGFallback',
];

for (const helper of movedHelpers) {
  test(`${helper} lives only in deferred chart export runtime`, () => {
    const signature = new RegExp(`(?:async\\s+)?function\\s+${helper}\\s*\\(`);
    assert.doesNotMatch(mainRuntime, signature, `${helper} must leave app.js`);
    assert.doesNotMatch(mainSource, signature, `${helper} must leave app.js.src`);
    assert.match(exportRuntime, signature, `${helper} must exist in chart-export.js`);
    assert.match(exportSource, signature, `${helper} must exist in chart-export.js.src`);
  });
}

test('eager bundle keeps lazy public export entrypoints', () => {
  assert.match(mainSource, /function _getChartExportRuntimeUrl\s*\(/);
  assert.match(mainSource, /function loadChartExportRuntime\s*\(/);
  assert.match(mainSource, /return '\/static\/js\/chart-export\.js' \+ query;/);
  assert.match(mainSource, /async function exportChartPNG\s*\(\.\.\.args\)/);
  assert.match(mainSource, /async function exportChartCSV\s*\(\.\.\.args\)/);
  assert.match(mainSource, /async function exportFullMatchTXT\s*\(\.\.\.args\)/);
  assert.match(mainSource, /window\.__sxfExportChartPNGImpl\(\.\.\.args\)/);
  assert.match(mainSource, /window\.__sxfExportChartCSVImpl\(\.\.\.args\)/);
  assert.match(mainSource, /window\.__sxfExportFullMatchTXTImpl\(\.\.\.args\)/);
});

test('chart export loader is single-flight and retryable after load failure', () => {
  assert.match(mainSource, /if \(window\._sxfChartExportRuntimePromise\) return window\._sxfChartExportRuntimePromise;/);
  const resets = mainSource.match(/window\._sxfChartExportRuntimePromise = null;/g) || [];
  assert.ok(resets.length >= 2, 'loader should reset the promise on invalid load and network error');
});

test('deferred runtime publishes all export implementations', () => {
  assert.match(exportSource, /window\.__sxfExportChartPNGImpl = exportChartPNG;/);
  assert.match(exportSource, /window\.__sxfExportChartCSVImpl = exportChartCSV;/);
  assert.match(exportSource, /window\.__sxfExportFullMatchTXTImpl = exportFullMatchTXT;/);
  assert.match(exportSource, /SmartXFlow - Full Match Data Export/);
  assert.doesNotMatch(mainSource, /SmartXFlow - Full Match Data Export/);
});

test('canonical minifier knows about chart export runtime', () => {
  assert.match(minifySource, /static\/js\/chart-export\.js\.src/);
  assert.match(minifySource, /static\/js\/chart-export\.js/);
});
''', encoding='utf-8')

print('P2.14 staged successfully')
print(f'app.js.src: {len(source)} -> {len(new_source)} bytes ({len(new_source) - len(source):+d})')
print(f'app.js: {len(runtime)} -> {len(rjsmin.jsmin(new_source))} bytes ({len(rjsmin.jsmin(new_source)) - len(runtime):+d})')
print(f'chart-export.js.src: {len(deferred_source)} bytes')
print(f'chart-export.js: {len(rjsmin.jsmin(deferred_source))} bytes')
