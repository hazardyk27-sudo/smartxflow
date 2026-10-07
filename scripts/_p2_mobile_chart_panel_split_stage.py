#!/usr/bin/env python3
from pathlib import Path
import re
import rjsmin

ROOT = Path(__file__).resolve().parents[1]
APP_SRC = ROOT / 'static/js/app.js.src'
APP_RUN = ROOT / 'static/js/app.js'
MOBILE_SRC = ROOT / 'static/js/mobile-chart-panel.js.src'
MOBILE_RUN = ROOT / 'static/js/mobile-chart-panel.js'
MINIFY = ROOT / 'minify.py'
FRONTEND_CI = ROOT / '.github/workflows/frontend-performance-tests.yml'
TEST = ROOT / 'tests/test_mobile_chart_panel_split.js'


def find_balanced_end(text: str, brace_pos: int) -> int:
    depth = 0
    i = brace_pos
    quote = None
    escaped = False
    line_comment = False
    block_comment = False
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ''
        if line_comment:
            if ch == '\n':
                line_comment = False
            i += 1
            continue
        if block_comment:
            if ch == '*' and nxt == '/':
                block_comment = False
                i += 2
                continue
            i += 1
            continue
        if quote:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == quote:
                quote = None
            i += 1
            continue
        if ch == '/' and nxt == '/':
            line_comment = True
            i += 2
            continue
        if ch == '/' and nxt == '*':
            block_comment = True
            i += 2
            continue
        if ch in ('\'', '"', '`'):
            quote = ch
            i += 1
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise RuntimeError('unbalanced JavaScript block')


def extract_region(text: str) -> tuple[int, int, str]:
    start_marker = 'const mobileBigValueTween'
    end_marker = 'function updateMobileSelectionButtons'
    start = text.find(start_marker)
    if start < 0:
        raise RuntimeError(f'missing start marker: {start_marker}')
    fn = text.find(end_marker, start)
    if fn < 0:
        raise RuntimeError(f'missing end marker: {end_marker}')
    brace = text.find('{', fn)
    if brace < 0:
        raise RuntimeError('missing updateMobileSelectionButtons body')
    end = find_balanced_end(text, brace)
    while end < len(text) and text[end] in ' \t':
        end += 1
    if end < len(text) and text[end] == ';':
        end += 1
    return start, end, text[start:end]


source = APP_SRC.read_text()
runtime = APP_RUN.read_text()
s0, s1, source_region = extract_region(source)
r0, r1, runtime_region = extract_region(runtime)

# Fail closed: this target must still be exact canonical minification even though the
# full served app bundle intentionally is not regenerated wholesale.
if rjsmin.jsmin(source_region).strip() != runtime_region.strip():
    raise SystemExit('P2.16 target source/runtime parity mismatch; refusing to stage')

# The moved region must really contain only the mobile panel implementation surface.
required = [
    'const mobileBigValueTween',
    'function updateMobileValueHeader',
    'function updateMobileValuePanel',
    'function updateMobileSelectionButtons',
]
for marker in required:
    if marker not in source_region:
        raise SystemExit(f'P2.16 target missing expected marker: {marker}')

mobile_source = """(function() {\n""" + source_region + """\nwindow.__sxfUpdateMobileValuePanelImpl = updateMobileValuePanel;\nwindow.__sxfUpdateMobileSelectionButtonsImpl = updateMobileSelectionButtons;\n})();\n"""
mobile_runtime = rjsmin.jsmin(mobile_source)

loader_source = r'''window._sxfMobileChartPanelRuntimePromise = window._sxfMobileChartPanelRuntimePromise || null;
function _getMobileChartPanelRuntimeUrl() {
    try {
        const scripts = document.getElementsByTagName('script');
        for (let i = scripts.length - 1; i >= 0; i--) {
            const src = scripts[i].src || '';
            if (src.indexOf('/static/js/app.js') !== -1) {
                const queryIndex = src.indexOf('?');
                const query = queryIndex >= 0 ? src.slice(queryIndex) : '';
                return '/static/js/mobile-chart-panel.js' + query;
            }
        }
    } catch (e) {}
    return '/static/js/mobile-chart-panel.js';
}

function loadMobileChartPanelRuntime() {
    const ready = typeof window.__sxfUpdateMobileValuePanelImpl === 'function' &&
        typeof window.__sxfUpdateMobileSelectionButtonsImpl === 'function';
    if (ready) return Promise.resolve();
    if (window._sxfMobileChartPanelRuntimePromise) return window._sxfMobileChartPanelRuntimePromise;

    window._sxfMobileChartPanelRuntimePromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = _getMobileChartPanelRuntimeUrl();
        script.async = true;
        script.onload = () => {
            const loaded = typeof window.__sxfUpdateMobileValuePanelImpl === 'function' &&
                typeof window.__sxfUpdateMobileSelectionButtonsImpl === 'function';
            if (loaded) {
                resolve();
                return;
            }
            window._sxfMobileChartPanelRuntimePromise = null;
            reject(new Error('Mobile chart panel runtime loaded without implementations'));
        };
        script.onerror = () => {
            window._sxfMobileChartPanelRuntimePromise = null;
            reject(new Error('Mobile chart panel runtime failed to load'));
        };
        document.head.appendChild(script);
    });
    return window._sxfMobileChartPanelRuntimePromise;
}

function updateMobileValuePanel(...args) {
    if (typeof window.__sxfUpdateMobileValuePanelImpl !== 'function') return;
    return window.__sxfUpdateMobileValuePanelImpl(...args);
}

function updateMobileSelectionButtons(...args) {
    if (typeof window.__sxfUpdateMobileSelectionButtonsImpl !== 'function') return;
    return window.__sxfUpdateMobileSelectionButtonsImpl(...args);
}
'''
loader_runtime = rjsmin.jsmin(loader_source)

source = source[:s0] + loader_source + source[s1:]
runtime = runtime[:r0] + loader_runtime + runtime[r1:]

old_src_load = """async function loadChart(...args) {\n    await loadModalChartRuntime();\n    return window.__sxfLoadChartImpl(...args);\n}"""
new_src_load = """async function loadChart(...args) {\n    await loadModalChartRuntime();\n    if (isMobile()) await loadMobileChartPanelRuntime();\n    return window.__sxfLoadChartImpl(...args);\n}"""
if source.count(old_src_load) != 1:
    raise SystemExit(f'expected one source loadChart stub, found {source.count(old_src_load)}')
source = source.replace(old_src_load, new_src_load, 1)

old_run_load = rjsmin.jsmin(old_src_load)
new_run_load = rjsmin.jsmin(new_src_load)
if runtime.count(old_run_load) != 1:
    raise SystemExit(f'expected one runtime loadChart stub, found {runtime.count(old_run_load)}')
runtime = runtime.replace(old_run_load, new_run_load, 1)

APP_SRC.write_text(source)
APP_RUN.write_text(runtime)
MOBILE_SRC.write_text(mobile_source)
MOBILE_RUN.write_text(mobile_runtime)

minify = MINIFY.read_text()
pair = "    ('static/js/mobile-chart-panel.js.src', 'static/js/mobile-chart-panel.js'),\n"
if pair not in minify:
    anchor = "    ('static/js/modal-info.js.src', 'static/js/modal-info.js'),\n"
    if anchor not in minify:
        raise SystemExit('minify.py modal-info anchor missing')
    minify = minify.replace(anchor, anchor + pair, 1)
    MINIFY.write_text(minify)

ci = FRONTEND_CI.read_text()
path_anchor = "      - 'static/js/modal-info.js.src'\n"
if "static/js/mobile-chart-panel.js" not in ci:
    if path_anchor not in ci:
        # P2.15 workflow may not yet list modal-info paths; anchor after app source instead.
        path_anchor = "      - 'static/js/app.js.src'\n"
    insert = "      - 'static/js/mobile-chart-panel.js'\n      - 'static/js/mobile-chart-panel.js.src'\n"
    ci = ci.replace(path_anchor, path_anchor + insert, 1)
run_anchor = "          node --test tests/test_modal_info_code_split.js\n"
if "test_mobile_chart_panel_split.js" not in ci:
    if run_anchor not in ci:
        run_anchor = "          node --test tests/test_modal_chart_helper_split.js\n"
    ci = ci.replace(run_anchor, run_anchor + "          node --test tests/test_mobile_chart_panel_split.js\n", 1)
# Ensure the new test itself triggers the workflow.
test_path = "      - 'tests/test_mobile_chart_panel_split.js'\n"
if test_path not in ci:
    trigger_anchor = "      - 'tests/test_modal_info_code_split.js'\n"
    if trigger_anchor not in ci:
        trigger_anchor = "      - 'tests/test_modal_chart_helper_split.js'\n"
    ci = ci.replace(trigger_anchor, trigger_anchor + test_path, 1)
FRONTEND_CI.write_text(ci)

TEST.write_text(r'''const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.join(__dirname, '..');
const mainRuntime = fs.readFileSync(path.join(root, 'static/js/app.js'), 'utf8');
const mainSource = fs.readFileSync(path.join(root, 'static/js/app.js.src'), 'utf8');
const mobileRuntime = fs.readFileSync(path.join(root, 'static/js/mobile-chart-panel.js'), 'utf8');
const mobileSource = fs.readFileSync(path.join(root, 'static/js/mobile-chart-panel.js.src'), 'utf8');
const minifySource = fs.readFileSync(path.join(root, 'minify.py'), 'utf8');

for (const [label, text] of [['runtime', mainRuntime], ['source', mainSource]]) {
  test(`main bundle keeps only mobile chart panel entrypoints (${label})`, () => {
    assert.match(text, /function\s+loadMobileChartPanelRuntime\s*\(/);
    assert.match(text, /function\s+updateMobileValuePanel\s*\(\.\.\.args\)/);
    assert.match(text, /function\s+updateMobileSelectionButtons\s*\(\.\.\.args\)/);
    assert.doesNotMatch(text, /const\s+mobileBigValueTween\s*=/);
    assert.doesNotMatch(text, /function\s+updateMobileValueHeader\s*\(/);
  });
}

test('deferred mobile chart panel runtime owns panel implementations', () => {
  assert.match(mobileSource, /const\s+mobileBigValueTween\s*=/);
  assert.match(mobileSource, /function\s+updateMobileValueHeader\s*\(/);
  assert.match(mobileSource, /function\s+updateMobileValuePanel\s*\(/);
  assert.match(mobileSource, /function\s+updateMobileSelectionButtons\s*\(/);
  assert.match(mobileSource, /window\.__sxfUpdateMobileValuePanelImpl = updateMobileValuePanel;/);
  assert.match(mobileSource, /window\.__sxfUpdateMobileSelectionButtonsImpl = updateMobileSelectionButtons;/);
  assert.match(mobileRuntime, /__sxfUpdateMobileValuePanelImpl/);
});

test('mobile panel loader inherits app asset version and is single-flight/retryable', () => {
  assert.match(mainSource, /return '\/static\/js\/mobile-chart-panel\.js' \+ query;/);
  assert.match(mainSource, /if \(window\._sxfMobileChartPanelRuntimePromise\) return window\._sxfMobileChartPanelRuntimePromise;/);
  const resets = mainSource.match(/window\._sxfMobileChartPanelRuntimePromise = null;/g) || [];
  assert.ok(resets.length >= 2);
});

test('loadChart awaits mobile panel runtime only on mobile', () => {
  assert.match(mainSource, /await loadModalChartRuntime\(\);\s*if \(isMobile\(\)\) await loadMobileChartPanelRuntime\(\);\s*return window\.__sxfLoadChartImpl/);
  assert.match(mainRuntime, /await loadModalChartRuntime\(\);if\(isMobile\(\)\)await loadMobileChartPanelRuntime\(\);return window\.__sxfLoadChartImpl/);
});

test('chart plugins and mobile detection remain eager', () => {
  assert.match(mainSource, /function\s+isMobile\s*\(\)/);
  assert.match(mainSource, /const\s+mobileBackgroundGridPlugin\s*=/);
  assert.match(mainSource, /const\s+mobileCrosshairPlugin\s*=/);
  assert.match(mainSource, /function\s+registerChartPlugins\s*\(/);
  assert.doesNotMatch(mobileSource, /mobileBackgroundGridPlugin/);
});

test('canonical minifier includes mobile chart panel runtime', () => {
  assert.match(minifySource, /static\/js\/mobile-chart-panel\.js\.src/);
  assert.match(minifySource, /static\/js\/mobile-chart-panel\.js/);
});
''')

print('P2.16 staged')
print('app.js.src', APP_SRC.stat().st_size)
print('app.js', APP_RUN.stat().st_size)
print('mobile-chart-panel.js.src', MOBILE_SRC.stat().st_size)
print('mobile-chart-panel.js', MOBILE_RUN.stat().st_size)
