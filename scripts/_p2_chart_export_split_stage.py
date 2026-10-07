#!/usr/bin/env python3
from pathlib import Path
import re
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

src_start_marker = 'function generateExportFilename(extension) {'
src_end_marker = 'function toggleChartSeries(market, seriesKey, btn) {'
if source.count(src_start_marker) != 1 or source.count(src_end_marker) != 1:
    raise SystemExit('Expected exactly one chart export block boundary in app.js.src')
src_start = source.index(src_start_marker)
src_end = source.index(src_end_marker)
if src_end <= src_start:
    raise SystemExit('Invalid chart export source block ordering')

runtime_start = re.search(r'function\s+generateExportFilename\s*\(\s*extension\s*\)\s*\{', runtime)
runtime_end = re.search(r'function\s+toggleChartSeries\s*\(\s*market\s*,\s*seriesKey\s*,\s*btn\s*\)\s*\{', runtime)
if not runtime_start or not runtime_end or runtime_end.start() <= runtime_start.start():
    raise SystemExit('Could not safely locate chart export block in served app.js')

source_export = source[src_start:src_end].rstrip()
runtime_export = runtime[runtime_start.start():runtime_end.start()].rstrip()

# app.js intentionally has runtime-only formatting/repairs elsewhere. Preserve it.
# We only proceed if the specific export block has source/runtime behavior parity
# after normalization, then splice that block independently in both files.
if rjsmin.jsmin(source_export) != rjsmin.jsmin(runtime_export):
    raise SystemExit(
        'Refusing P2.14 transformation: chart export block differs behaviorally '
        'between app.js.src and served app.js.'
    )

deferred_source = """// Deferred chart export runtime. Loaded on first export action only.\n(function () {\n%s\n\nwindow.__sxfExportChartPNGImpl = exportChartPNG;\nwindow.__sxfExportChartCSVImpl = exportChartCSV;\nwindow.__sxfExportFullMatchTXTImpl = exportFullMatchTXT;\n})();\n""" % source_export

deferred_runtime = rjsmin.jsmin(deferred_source)

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

new_source = source[:src_start] + loader + source[src_end:]
loader_runtime = rjsmin.jsmin(loader)
new_runtime = runtime[:runtime_start.start()] + loader_runtime + runtime[runtime_end.start():]

APP_SRC.write_text(new_source, encoding='utf-8')
APP_RUNTIME.write_text(new_runtime, encoding='utf-8')
EXPORT_SRC.write_text(deferred_source, encoding='utf-8')
EXPORT_RUNTIME.write_text(deferred_runtime, encoding='utf-8')

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
    ci_text = ci_text.replace(anchor, anchor + "      - 'static/js/chart-export.js'\n      - 'static/js/chart-export.js.src'\n", 1)
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
  'generateExportFilename', 'isEXEEnvironment', 'showExportNotification',
  'savePNGViaAPI', 'showExportOverlay', 'removeExportOverlay',
  'exportChartPNGFallback',
];

for (const helper of movedHelpers) {
  test(`${helper} lives only in deferred chart export runtime`, () => {
    const signature = new RegExp(`(?:async\\s+)?function\\s+${helper}\\s*\\(`);
    assert.doesNotMatch(mainRuntime, signature);
    assert.doesNotMatch(mainSource, signature);
    assert.match(exportRuntime, signature);
    assert.match(exportSource, signature);
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

test('loader is single-flight and retryable after failure', () => {
  assert.match(mainSource, /if \(window\._sxfChartExportRuntimePromise\) return window\._sxfChartExportRuntimePromise;/);
  const resets = mainSource.match(/window\._sxfChartExportRuntimePromise = null;/g) || [];
  assert.ok(resets.length >= 2);
});

test('deferred runtime publishes implementations and full TXT exporter', () => {
  assert.match(exportSource, /window\.__sxfExportChartPNGImpl = exportChartPNG;/);
  assert.match(exportSource, /window\.__sxfExportChartCSVImpl = exportChartCSV;/);
  assert.match(exportSource, /window\.__sxfExportFullMatchTXTImpl = exportFullMatchTXT;/);
  assert.match(exportSource, /SmartXFlow - Full Match Data Export/);
  assert.doesNotMatch(mainSource, /SmartXFlow - Full Match Data Export/);
});

test('canonical minifier includes chart export runtime', () => {
  assert.match(minifySource, /static\/js\/chart-export\.js\.src/);
  assert.match(minifySource, /static\/js\/chart-export\.js/);
});
''', encoding='utf-8')

print('P2.14 staged successfully')
print(f'export behavior parity: yes')
print(f'app.js.src: {len(source.encode())} -> {len(new_source.encode())} bytes ({len(new_source.encode()) - len(source.encode()):+d})')
print(f'app.js: {len(runtime.encode())} -> {len(new_runtime.encode())} bytes ({len(new_runtime.encode()) - len(runtime.encode()):+d})')
print(f'chart-export.js.src: {len(deferred_source.encode())} bytes')
print(f'chart-export.js: {len(deferred_runtime.encode())} bytes')
