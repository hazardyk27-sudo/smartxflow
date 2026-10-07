#!/usr/bin/env python3
from pathlib import Path
import re
import rjsmin

ROOT = Path(__file__).resolve().parents[1]
APP_SRC = ROOT / 'static/js/app.js.src'
APP_RUNTIME = ROOT / 'static/js/app.js'
INFO_SRC = ROOT / 'static/js/modal-info.js.src'
INFO_RUNTIME = ROOT / 'static/js/modal-info.js'
MINIFY = ROOT / 'minify.py'
TEST_FILE = ROOT / 'tests/test_modal_info_code_split.js'

source = APP_SRC.read_text(encoding='utf-8')
runtime = APP_RUNTIME.read_text(encoding='utf-8')

src_start_marker = 'function updateMatchInfoCard() {'
src_end_marker = 'function getTrendArrow(current, previous) {'
if source.count(src_start_marker) != 1 or source.count(src_end_marker) != 1:
    raise SystemExit('Expected exactly one modal info block boundary in app.js.src')
src_start = source.index(src_start_marker)
src_end = source.index(src_end_marker)
if src_end <= src_start:
    raise SystemExit('Invalid modal info source block ordering')

runtime_start = re.search(r'function\s+updateMatchInfoCard\s*\(\s*\)\s*\{', runtime)
runtime_end = re.search(r'function\s+getTrendArrow\s*\(\s*current\s*,\s*previous\s*\)\s*\{', runtime)
if not runtime_start or not runtime_end or runtime_end.start() <= runtime_start.start():
    raise SystemExit('Could not safely locate modal info block in served app.js')

source_block = source[src_start:src_end].rstrip()
runtime_block = runtime[runtime_start.start():runtime_end.start()].rstrip()
if rjsmin.jsmin(source_block) != rjsmin.jsmin(runtime_block):
    raise SystemExit('Refusing P2.15: modal info block differs behaviorally between source and served runtime')

impl_source = source_block.replace(
    'function updateMatchInfoCard() {',
    'function _updateMatchInfoCardImpl() {',
    1,
)
deferred_source = """// Deferred modal match-info renderer. Loaded on first modal data render only.\n(function () {\n%s\n\nwindow.__sxfUpdateMatchInfoCardImpl = _updateMatchInfoCardImpl;\n})();\n""" % impl_source

deferred_runtime = rjsmin.jsmin(deferred_source)

loader = r"""window._sxfModalInfoRuntimePromise = window._sxfModalInfoRuntimePromise || null;
function _getModalInfoRuntimeUrl() {
    try {
        const scripts = document.getElementsByTagName('script');
        for (let i = scripts.length - 1; i >= 0; i--) {
            const src = scripts[i].src || '';
            if (src.indexOf('/static/js/app.js') !== -1) {
                const queryIndex = src.indexOf('?');
                const query = queryIndex >= 0 ? src.slice(queryIndex) : '';
                return '/static/js/modal-info.js' + query;
            }
        }
    } catch (e) {}
    return '/static/js/modal-info.js';
}

function loadModalInfoRuntime() {
    if (typeof window.__sxfUpdateMatchInfoCardImpl === 'function') return Promise.resolve();
    if (window._sxfModalInfoRuntimePromise) return window._sxfModalInfoRuntimePromise;

    window._sxfModalInfoRuntimePromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = _getModalInfoRuntimeUrl();
        script.async = true;
        script.onload = () => {
            if (typeof window.__sxfUpdateMatchInfoCardImpl === 'function') {
                resolve();
                return;
            }
            window._sxfModalInfoRuntimePromise = null;
            reject(new Error('Modal info runtime loaded without implementation'));
        };
        script.onerror = () => {
            window._sxfModalInfoRuntimePromise = null;
            reject(new Error('Modal info runtime failed to load'));
        };
        document.head.appendChild(script);
    });
    return window._sxfModalInfoRuntimePromise;
}

async function updateMatchInfoCard(...args) {
    await loadModalInfoRuntime();
    return window.__sxfUpdateMatchInfoCardImpl(...args);
}

"""

new_source = source[:src_start] + loader + source[src_end:]
source_call = '        updateMatchInfoCard();\n        \n        await loadChart(home, away, market, league);'
source_call_new = '        await updateMatchInfoCard();\n        \n        await loadChart(home, away, market, league);'
if new_source.count(source_call) != 1:
    raise SystemExit('Could not safely await modal info renderer in app.js.src')
new_source = new_source.replace(source_call, source_call_new, 1)

loader_runtime = rjsmin.jsmin(loader)
new_runtime = runtime[:runtime_start.start()] + loader_runtime + runtime[runtime_end.start():]
runtime_call = 'updateMatchInfoCard();await loadChart(home,away,market,league)'
runtime_call_new = 'await updateMatchInfoCard();await loadChart(home,away,market,league)'
if new_runtime.count(runtime_call) != 1:
    raise SystemExit('Could not safely await modal info renderer in served app.js')
new_runtime = new_runtime.replace(runtime_call, runtime_call_new, 1)

APP_SRC.write_text(new_source, encoding='utf-8')
APP_RUNTIME.write_text(new_runtime, encoding='utf-8')
INFO_SRC.write_text(deferred_source, encoding='utf-8')
INFO_RUNTIME.write_text(deferred_runtime, encoding='utf-8')

minify_text = MINIFY.read_text(encoding='utf-8')
pair = "    ('static/js/modal-info.js.src', 'static/js/modal-info.js'),\n"
if pair not in minify_text:
    anchor = "    ('static/js/modal-live.js.src', 'static/js/modal-live.js'),\n"
    if minify_text.count(anchor) != 1:
        anchor = "    ('static/js/app.js.src', 'static/js/app.js'),\n"
    if minify_text.count(anchor) != 1:
        raise SystemExit('Could not safely update minify.py modal-info pair')
    minify_text = minify_text.replace(anchor, anchor + pair, 1)
    MINIFY.write_text(minify_text, encoding='utf-8')

TEST_FILE.write_text(r'''const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.join(__dirname, '..');
const mainRuntime = fs.readFileSync(path.join(root, 'static/js/app.js'), 'utf8');
const mainSource = fs.readFileSync(path.join(root, 'static/js/app.js.src'), 'utf8');
const infoRuntime = fs.readFileSync(path.join(root, 'static/js/modal-info.js'), 'utf8');
const infoSource = fs.readFileSync(path.join(root, 'static/js/modal-info.js.src'), 'utf8');
const minifySource = fs.readFileSync(path.join(root, 'minify.py'), 'utf8');

for (const [label, text] of [['runtime', mainRuntime], ['source', mainSource]]) {
  test(`main bundle keeps only lazy modal info entrypoint (${label})`, () => {
    assert.match(text, /function\s+loadModalInfoRuntime\s*\(/);
    assert.match(text, /async\s+function\s+updateMatchInfoCard\s*\(\.\.\.args\)/);
    assert.doesNotMatch(text, /function\s+_updateMatchInfoCardImpl\s*\(/);
    assert.doesNotMatch(text, /info-columns info-columns-3/);
  });
}

test('deferred modal info runtime owns the renderer implementation', () => {
  assert.match(infoSource, /function\s+_updateMatchInfoCardImpl\s*\(/);
  assert.match(infoRuntime, /function\s+_updateMatchInfoCardImpl\s*\(/);
  assert.match(infoSource, /info-columns info-columns-3/);
  assert.match(infoSource, /window\.__sxfUpdateMatchInfoCardImpl = _updateMatchInfoCardImpl;/);
});

test('modal info loader inherits app asset version and is single-flight/retryable', () => {
  assert.match(mainSource, /return '\/static\/js\/modal-info\.js' \+ query;/);
  assert.match(mainSource, /if \(window\._sxfModalInfoRuntimePromise\) return window\._sxfModalInfoRuntimePromise;/);
  const resets = mainSource.match(/window\._sxfModalInfoRuntimePromise = null;/g) || [];
  assert.ok(resets.length >= 2);
});

test('chart/history pipeline awaits modal info render before chart continuation', () => {
  assert.match(mainSource, /await updateMatchInfoCard\(\);[\s\S]{0,120}await loadChart\(home, away, market, league\);/);
  assert.match(mainRuntime, /await updateMatchInfoCard\(\);await loadChart\(home,away,market,league\)/);
});

test('shared trend helper remains eager', () => {
  assert.match(mainSource, /function\s+getTrendArrow\s*\(current, previous\)/);
  assert.doesNotMatch(infoSource, /function\s+getTrendArrow\s*\(/);
});

test('canonical minifier includes modal info runtime', () => {
  assert.match(minifySource, /static\/js\/modal-info\.js\.src/);
  assert.match(minifySource, /static\/js\/modal-info\.js/);
});
''', encoding='utf-8')

print('P2.15 staged successfully')
print('modal info behavior parity: yes')
print(f'app.js.src: {len(source.encode())} -> {len(new_source.encode())} bytes ({len(new_source.encode()) - len(source.encode()):+d})')
print(f'app.js: {len(runtime.encode())} -> {len(new_runtime.encode())} bytes ({len(new_runtime.encode()) - len(runtime.encode()):+d})')
print(f'modal-info.js.src: {len(deferred_source.encode())} bytes')
print(f'modal-info.js: {len(deferred_runtime.encode())} bytes')
