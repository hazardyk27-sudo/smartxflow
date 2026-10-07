#!/usr/bin/env python3
from pathlib import Path
import rjsmin

ROOT = Path(__file__).resolve().parents[1]
APP_SRC = ROOT / 'static/js/app.js.src'
APP_RUN = ROOT / 'static/js/app.js'
ENTRY_SRC = ROOT / 'static/js/modal-entry.js.src'
ENTRY_RUN = ROOT / 'static/js/modal-entry.js'
MINIFY = ROOT / 'minify.py'
DEFERRED_CHART_TEST = ROOT / 'tests/test_deferred_chart_libs.js'
ENTRY_TEST = ROOT / 'tests/test_modal_entry_code_split.js'


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
        if ch in ("'", '"', '`'):
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


def extract_function(text: str, marker: str) -> tuple[int, int, str]:
    start = text.find(marker)
    if start < 0:
        raise RuntimeError(f'missing function marker: {marker}')
    brace = text.find('{', start)
    if brace < 0:
        raise RuntimeError(f'missing function body: {marker}')
    end = find_balanced_end(text, brace)
    while end < len(text) and text[end] in ' \t':
        end += 1
    if end < len(text) and text[end] == ';':
        end += 1
    return start, end, text[start:end]


def extract_entry_region(text: str):
    markers = [
        'async function openMatchModalFromMatches(',
        'async function openMatchModalFromAPI(',
        'async function openMatchModal(',
    ]
    parts = [extract_function(text, marker) for marker in markers]
    if not (parts[0][0] < parts[1][0] < parts[2][0]):
        raise RuntimeError('modal entry functions are not in expected order')
    start = parts[0][0]
    end = parts[2][1]
    return start, end, text[start:end], [p[2] for p in parts]


def as_impl(block: str, name: str, impl: str) -> str:
    prefix = f'async function {name}'
    if not block.startswith(prefix):
        raise RuntimeError(f'unexpected block prefix for {name}')
    return block.replace(prefix, f'window.{impl} = async function {name}', 1) + ';'


source = APP_SRC.read_text()
runtime = APP_RUN.read_text()
s0, s1, source_region, source_parts = extract_entry_region(source)
r0, r1, runtime_region, runtime_parts = extract_entry_region(runtime)

if rjsmin.jsmin(source_region).strip() != runtime_region.strip():
    raise SystemExit('P2.17 modal-entry source/runtime parity mismatch; refusing to stage')

checks = [
    ('openMatchModalFromMatches', '__sxfOpenMatchModalFromMatchesImpl'),
    ('openMatchModalFromAPI', '__sxfOpenMatchModalFromAPIImpl'),
    ('openMatchModal', '__sxfOpenMatchModalImpl'),
]
for block, (name, _) in zip(source_parts, checks):
    if 'loadChartLibs' not in block or 'registerChartPlugins' not in block:
        raise SystemExit(f'P2.17 {name} lost chart on-demand contract before split')

entry_source = '(function() {\n' + '\n\n'.join(
    as_impl(block, name, impl)
    for block, (name, impl) in zip(source_parts, checks)
) + '\n})();\n'
entry_runtime = rjsmin.jsmin(entry_source)

loader_source = r'''window._sxfModalEntryRuntimePromise = window._sxfModalEntryRuntimePromise || null;
function _getModalEntryRuntimeUrl() {
    try {
        const scripts = document.getElementsByTagName('script');
        for (let i = scripts.length - 1; i >= 0; i--) {
            const src = scripts[i].src || '';
            if (src.indexOf('/static/js/app.js') !== -1) {
                const queryIndex = src.indexOf('?');
                const query = queryIndex >= 0 ? src.slice(queryIndex) : '';
                return '/static/js/modal-entry.js' + query;
            }
        }
    } catch (e) {}
    return '/static/js/modal-entry.js';
}

function loadModalEntryRuntime() {
    const ready = typeof window.__sxfOpenMatchModalFromMatchesImpl === 'function' &&
        typeof window.__sxfOpenMatchModalFromAPIImpl === 'function' &&
        typeof window.__sxfOpenMatchModalImpl === 'function';
    if (ready) return Promise.resolve();
    if (window._sxfModalEntryRuntimePromise) return window._sxfModalEntryRuntimePromise;

    window._sxfModalEntryRuntimePromise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = _getModalEntryRuntimeUrl();
        script.async = true;
        script.onload = () => {
            const loaded = typeof window.__sxfOpenMatchModalFromMatchesImpl === 'function' &&
                typeof window.__sxfOpenMatchModalFromAPIImpl === 'function' &&
                typeof window.__sxfOpenMatchModalImpl === 'function';
            if (loaded) {
                resolve();
                return;
            }
            window._sxfModalEntryRuntimePromise = null;
            reject(new Error('Modal entry runtime loaded without implementations'));
        };
        script.onerror = () => {
            window._sxfModalEntryRuntimePromise = null;
            reject(new Error('Modal entry runtime failed to load'));
        };
        document.head.appendChild(script);
    });
    return window._sxfModalEntryRuntimePromise;
}

async function openMatchModalFromMatches(...args) {
    await loadModalEntryRuntime();
    return window.__sxfOpenMatchModalFromMatchesImpl(...args);
}

async function openMatchModalFromAPI(...args) {
    await loadModalEntryRuntime();
    return window.__sxfOpenMatchModalFromAPIImpl(...args);
}

async function openMatchModal(...args) {
    await loadModalEntryRuntime();
    return window.__sxfOpenMatchModalImpl(...args);
}
'''
loader_runtime = rjsmin.jsmin(loader_source)

source = source[:s0] + loader_source + source[s1:]
runtime = runtime[:r0] + loader_runtime + runtime[r1:]

APP_SRC.write_text(source)
APP_RUN.write_text(runtime)
ENTRY_SRC.write_text(entry_source)
ENTRY_RUN.write_text(entry_runtime)

minify = MINIFY.read_text()
pair = "    ('static/js/modal-entry.js.src', 'static/js/modal-entry.js'),\n"
if pair not in minify:
    anchor = "    ('static/js/mobile-chart-panel.js.src', 'static/js/mobile-chart-panel.js'),\n"
    if anchor not in minify:
        anchor = "    ('static/js/modal-info.js.src', 'static/js/modal-info.js'),\n"
    if anchor not in minify:
        raise SystemExit('minify.py modal runtime anchor missing')
    minify = minify.replace(anchor, anchor + pair, 1)
    MINIFY.write_text(minify)

DEFERRED_CHART_TEST.write_text(r'''const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.join(__dirname, '..');
const mainBundles = [
  ['runtime', fs.readFileSync(path.join(root, 'static/js/app.js'), 'utf8')],
  ['source', fs.readFileSync(path.join(root, 'static/js/app.js.src'), 'utf8')],
];
const entryBundles = [
  ['runtime', fs.readFileSync(path.join(root, 'static/js/modal-entry.js'), 'utf8')],
  ['source', fs.readFileSync(path.join(root, 'static/js/modal-entry.js.src'), 'utf8')],
];

function extractFunction(source, signature) {
  const start = source.indexOf(signature);
  assert.ok(start >= 0, `${signature} should exist`);
  const bodyStart = source.indexOf('{', start);
  let depth = 0;
  for (let i = bodyStart; i < source.length; i += 1) {
    if (source[i] === '{') depth += 1;
    if (source[i] === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  assert.fail(`${signature} should have a closing brace`);
}

function extractBootstrap(source) {
  const startMatch = /document\.addEventListener\('DOMContentLoaded',\s*async\s*\(\)\s*=>\s*\{/.exec(source);
  assert.ok(startMatch, 'dashboard bootstrap should exist');
  const end = source.indexOf('function updateLastRefreshDisplay()', startMatch.index);
  assert.ok(end > startMatch.index, 'dashboard bootstrap should have an end');
  return source.slice(startMatch.index, end);
}

for (const [name, source] of mainBundles) {
  test(`chart libraries are absent from dashboard startup (${name})`, () => {
    const bootstrap = extractBootstrap(source);
    assert.doesNotMatch(bootstrap, /loadChartLibs/);
    assert.doesNotMatch(bootstrap, /chart libraries/);
  });

  for (const signature of [
    'async function openMatchModalFromMatches(',
    'async function openMatchModalFromAPI(',
    'async function openMatchModal(',
  ]) {
    test(`${signature} is a lazy modal-entry stub (${name})`, () => {
      const fn = extractFunction(source, signature);
      assert.match(fn, /loadModalEntryRuntime/);
      assert.doesNotMatch(fn, /loadChartLibs/);
      assert.doesNotMatch(fn, /registerChartPlugins/);
    });
  }
}

for (const [name, source] of entryBundles) {
  for (const signature of [
    'async function openMatchModalFromMatches(',
    'async function openMatchModalFromAPI(',
    'async function openMatchModal(',
  ]) {
    test(`${signature} keeps on-demand chart loading in modal-entry (${name})`, () => {
      const fn = extractFunction(source, signature);
      assert.match(fn, /loadChartLibs/);
      assert.match(fn, /registerChartPlugins/);
    });
  }
}
''')

ENTRY_TEST.write_text(r'''const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.join(__dirname, '..');
const mainRuntime = fs.readFileSync(path.join(root, 'static/js/app.js'), 'utf8');
const mainSource = fs.readFileSync(path.join(root, 'static/js/app.js.src'), 'utf8');
const entryRuntime = fs.readFileSync(path.join(root, 'static/js/modal-entry.js'), 'utf8');
const entrySource = fs.readFileSync(path.join(root, 'static/js/modal-entry.js.src'), 'utf8');
const minifySource = fs.readFileSync(path.join(root, 'minify.py'), 'utf8');
const template = fs.readFileSync(path.join(root, 'templates/index.html'), 'utf8');

for (const [label, text] of [['runtime', mainRuntime], ['source', mainSource]]) {
  test(`main bundle keeps only lazy modal-entry stubs (${label})`, () => {
    assert.match(text, /function\s+loadModalEntryRuntime\s*\(/);
    assert.match(text, /async function\s+openMatchModalFromMatches\s*\(\.\.\.args\)/);
    assert.match(text, /async function\s+openMatchModalFromAPI\s*\(\.\.\.args\)/);
    assert.match(text, /async function\s+openMatchModal\s*\(\.\.\.args\)/);
    assert.doesNotMatch(text, /async function\s+openMatchModalFromMatches\s*\(index\)/);
    assert.doesNotMatch(text, /async function\s+openMatchModalFromAPI\s*\(homeTeam, awayTeam/);
  });
}

test('deferred modal-entry runtime owns all three implementations', () => {
  assert.match(entrySource, /window\.__sxfOpenMatchModalFromMatchesImpl = async function openMatchModalFromMatches\(index\)/);
  assert.match(entrySource, /window\.__sxfOpenMatchModalFromAPIImpl = async function openMatchModalFromAPI\(homeTeam, awayTeam/);
  assert.match(entrySource, /window\.__sxfOpenMatchModalImpl = async function openMatchModal\(index\)/);
  assert.match(entryRuntime, /__sxfOpenMatchModalFromMatchesImpl/);
  assert.match(entryRuntime, /__sxfOpenMatchModalFromAPIImpl/);
  assert.match(entryRuntime, /__sxfOpenMatchModalImpl/);
});

test('modal-entry loader inherits app asset version and is single-flight/retryable', () => {
  assert.match(mainSource, /return '\/static\/js\/modal-entry\.js' \+ query;/);
  assert.match(mainSource, /if \(window\._sxfModalEntryRuntimePromise\) return window\._sxfModalEntryRuntimePromise;/);
  const resets = mainSource.match(/window\._sxfModalEntryRuntimePromise = null;/g) || [];
  assert.ok(resets.length >= 2);
});

test('modal-entry stubs await runtime and delegate without changing arguments', () => {
  assert.match(mainSource, /async function openMatchModalFromMatches\(\.\.\.args\) \{\s*await loadModalEntryRuntime\(\);\s*return window\.__sxfOpenMatchModalFromMatchesImpl\(\.\.\.args\);/);
  assert.match(mainSource, /async function openMatchModalFromAPI\(\.\.\.args\) \{\s*await loadModalEntryRuntime\(\);\s*return window\.__sxfOpenMatchModalFromAPIImpl\(\.\.\.args\);/);
  assert.match(mainSource, /async function openMatchModal\(\.\.\.args\) \{\s*await loadModalEntryRuntime\(\);\s*return window\.__sxfOpenMatchModalImpl\(\.\.\.args\);/);
});

test('modal orchestration stays behavior-complete in deferred runtime', () => {
  for (const marker of [
    'resetModalState()',
    'loadAllMarketsAtOnce(',
    'loadChartWithTrends(',
    'renderMatchAlarmsSection(',
    '_checkModalLiveData(',
    '_setModalFavBtnState(',
  ]) assert.match(entrySource, new RegExp(marker.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  assert.match(entrySource, /_isTestFreeMatch/);
  assert.match(entrySource, /_showTestLockedToast/);
});

test('shared modal helpers remain eager', () => {
  assert.match(mainSource, /function\s+resetModalState\s*\(/);
  assert.match(mainSource, /async function\s+loadAllMarketsAtOnce\s*\(/);
  assert.match(mainSource, /async function\s+loadChartWithTrends\s*\(/);
});

test('modal-entry runtime is not eagerly executed by template', () => {
  assert.doesNotMatch(template, /<script[^>]+modal-entry\.js/);
});

test('canonical minifier includes modal-entry runtime', () => {
  assert.match(minifySource, /static\/js\/modal-entry\.js\.src/);
  assert.match(minifySource, /static\/js\/modal-entry\.js/);
});
''')

print('P2.17 staged')
print('app.js.src', APP_SRC.stat().st_size)
print('app.js', APP_RUN.stat().st_size)
print('modal-entry.js.src', ENTRY_SRC.stat().st_size)
print('modal-entry.js', ENTRY_RUN.stat().st_size)
