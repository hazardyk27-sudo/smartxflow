#!/usr/bin/env python3
from pathlib import Path
import rjsmin

ROOT = Path(__file__).resolve().parents[1]
APP_SRC = ROOT / 'static/js/app.js.src'
APP_RUN = ROOT / 'static/js/app.js'
ENTRY_SRC = ROOT / 'static/js/modal-entry.js.src'
ENTRY_RUN = ROOT / 'static/js/modal-entry.js'
ENTRY_TEST = ROOT / 'tests/test_modal_entry_code_split.js'
DATA_TEST = ROOT / 'tests/test_modal_data_pipeline_split.js'


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
            if ch == '\n': line_comment = False
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
        if ch == '{': depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0: return i + 1
        i += 1
    raise RuntimeError('unbalanced JavaScript block')


def extract_function(text: str, marker: str):
    start = text.find(marker)
    if start < 0: raise RuntimeError(f'missing marker: {marker}')
    brace = text.find('{', start)
    if brace < 0: raise RuntimeError(f'missing body: {marker}')
    end = find_balanced_end(text, brace)
    while end < len(text) and text[end] in ' \t': end += 1
    if end < len(text) and text[end] == ';': end += 1
    return start, end, text[start:end]


def parity(source_block: str, runtime_block: str, label: str):
    if rjsmin.jsmin(source_block).strip() != runtime_block.strip():
        raise SystemExit(f'P2.18 {label} source/runtime parity mismatch; refusing to stage')


source = APP_SRC.read_text()
runtime = APP_RUN.read_text()
entry_source = ENTRY_SRC.read_text()
entry_runtime = ENTRY_RUN.read_text()
if rjsmin.jsmin(entry_source).strip() != entry_runtime.strip():
    raise SystemExit('P2.18 existing modal-entry source/runtime parity mismatch')

# resetModalState is modal-entry-only after P2.17.
s0, s1, reset_src = extract_function(source, 'function resetModalState(')
r0, r1, reset_run = extract_function(runtime, 'function resetModalState(')
parity(reset_src, reset_run, 'resetModalState')
if source.count('resetModalState(') != 1:
    raise SystemExit(f'P2.18 unexpected eager resetModalState callers: {source.count("resetModalState(")}')

# Bulk cache state intentionally remains eager because closeModal clears it too.
for text, bulk_decl, key_decl in [
    (source, 'let bulkHistoryCache = {};', "let bulkHistoryCacheKey = '';"),
    (runtime, 'let bulkHistoryCache={};', "let bulkHistoryCacheKey='';"),
]:
    if bulk_decl not in text or key_decl not in text:
        raise SystemExit('P2.18 eager bulk cache declarations missing')
cs0, cs1, close_src = extract_function(source, 'function closeModal(')
if 'bulkHistoryCache = {};' not in close_src or "bulkHistoryCacheKey = '';" not in close_src:
    raise SystemExit('P2.18 closeModal bulk cache lifecycle contract missing')
if 'bulkHistoryCache = {};' not in reset_src or "bulkHistoryCacheKey = '';" not in reset_src:
    raise SystemExit('P2.18 resetModalState bulk cache lifecycle contract missing')

# Defer modal cache + bulk fetch + chart-history pipeline, but not the shared bulk cache variables.
cache_marker_src = 'const MODAL_CACHE_TTL = 30000;'
cache_marker_run = 'const MODAL_CACHE_TTL=30000;'
ps0 = source.find(cache_marker_src)
pr0 = runtime.find(cache_marker_run)
if ps0 < 0 or pr0 < 0:
    raise SystemExit('P2.18 modal cache marker missing')
_, ps1, _ = extract_function(source, 'async function loadChartWithTrends(')
_, pr1, _ = extract_function(runtime, 'async function loadChartWithTrends(')
source_pipeline = source[ps0:ps1]
runtime_pipeline = runtime[pr0:pr1]
parity(source_pipeline, runtime_pipeline, 'modal data pipeline')

private_names = ['MODAL_CACHE_TTL', 'modalDataCache', 'getModalCacheKey', 'getModalCachedData', 'setModalCachedData']
for name in private_names:
    if source.count(name) != source_pipeline.count(name):
        raise SystemExit(f'P2.18 {name} has an eager consumer outside the target pipeline')
if source.count('loadAllMarketsAtOnce(') != 1:
    raise SystemExit(f'P2.18 unexpected eager loadAllMarketsAtOnce callers: {source.count("loadAllMarketsAtOnce(")}')
if source.count('loadChartWithTrends(') != 2:
    raise SystemExit(f'P2.18 unexpected eager loadChartWithTrends refs: {source.count("loadChartWithTrends(")}')

reset_stub_src = r'''function resetModalState(...args) {
    if (typeof window.__sxfResetModalStateImpl === 'function') {
        return window.__sxfResetModalStateImpl(...args);
    }
    return loadModalEntryRuntime().then(() => window.__sxfResetModalStateImpl(...args));
}
'''
reset_stub_run = rjsmin.jsmin(reset_stub_src)
pipeline_stub_src = r'''async function loadAllMarketsAtOnce(...args) {
    await loadModalEntryRuntime();
    return window.__sxfLoadAllMarketsAtOnceImpl(...args);
}

async function loadChartWithTrends(...args) {
    await loadModalEntryRuntime();
    return window.__sxfLoadChartWithTrendsImpl(...args);
}
'''
pipeline_stub_run = rjsmin.jsmin(pipeline_stub_src)

source = source[:s0] + reset_stub_src + source[s1:]
runtime = runtime[:r0] + reset_stub_run + runtime[r1:]
ps0 = source.find(cache_marker_src)
pr0 = runtime.find(cache_marker_run)
_, ps1, _ = extract_function(source, 'async function loadChartWithTrends(')
_, pr1, _ = extract_function(runtime, 'async function loadChartWithTrends(')
source = source[:ps0] + pipeline_stub_src + source[ps1:]
runtime = runtime[:pr0] + pipeline_stub_run + runtime[pr1:]

# Require all modal-entry/data implementations before the runtime is considered loaded.
ls0, ls1, loader_src_old = extract_function(source, 'function loadModalEntryRuntime(')
lr0, lr1, loader_run_old = extract_function(runtime, 'function loadModalEntryRuntime(')
parity(loader_src_old, loader_run_old, 'modal-entry loader')
needle = "typeof window.__sxfOpenMatchModalImpl === 'function';"
replacement = "typeof window.__sxfOpenMatchModalImpl === 'function' &&\n        typeof window.__sxfResetModalStateImpl === 'function' &&\n        typeof window.__sxfLoadAllMarketsAtOnceImpl === 'function' &&\n        typeof window.__sxfLoadChartWithTrendsImpl === 'function';"
if loader_src_old.count(needle) != 2:
    raise SystemExit(f'P2.18 expected two modal-entry readiness tails, found {loader_src_old.count(needle)}')
loader_src_new = loader_src_old.replace(needle, replacement)
source = source[:ls0] + loader_src_new + source[ls1:]
runtime = runtime[:lr0] + rjsmin.jsmin(loader_src_new) + runtime[lr1:]

# Expand the existing modal-entry IIFE, avoiding a second deferred network hop.
close_marker = '\n})();'
if entry_source.count(close_marker) != 1:
    raise SystemExit('P2.18 modal-entry IIFE close marker mismatch')
exports = r'''

window.__sxfResetModalStateImpl = resetModalState;
window.__sxfLoadAllMarketsAtOnceImpl = loadAllMarketsAtOnce;
window.__sxfLoadChartWithTrendsImpl = loadChartWithTrends;
'''
clean_reset_src = '\n'.join(line.rstrip() for line in reset_src.strip().splitlines())
clean_source_pipeline = '\n'.join(line.rstrip() for line in source_pipeline.strip().splitlines())
append_block = '\n\n' + clean_reset_src + '\n\n' + clean_source_pipeline + exports
entry_source = entry_source.replace(close_marker, append_block + close_marker, 1)
entry_runtime = rjsmin.jsmin(entry_source)

APP_SRC.write_text(source)
APP_RUN.write_text(runtime)
ENTRY_SRC.write_text(entry_source)
ENTRY_RUN.write_text(entry_runtime)

entry_test = ENTRY_TEST.read_text()
old_test = r'''test('shared modal helpers remain eager', () => {
  assert.match(mainSource, /function\s+resetModalState\s*\(/);
  assert.match(mainSource, /async function\s+loadAllMarketsAtOnce\s*\(/);
  assert.match(mainSource, /async function\s+loadChartWithTrends\s*\(/);
});'''
new_test = r'''test('modal data helpers keep public lazy entrypoints in main bundle', () => {
  assert.match(mainSource, /function\s+resetModalState\s*\(\.\.\.args\)/);
  assert.match(mainSource, /async function\s+loadAllMarketsAtOnce\s*\(\.\.\.args\)/);
  assert.match(mainSource, /async function\s+loadChartWithTrends\s*\(\.\.\.args\)/);
  assert.match(mainSource, /loadModalEntryRuntime/);
});'''
if old_test not in entry_test:
    raise SystemExit('P2.18 modal-entry test anchor missing')
ENTRY_TEST.write_text(entry_test.replace(old_test, new_test, 1))

DATA_TEST.write_text(r'''const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.join(__dirname, '..');
const mainRuntime = fs.readFileSync(path.join(root, 'static/js/app.js'), 'utf8');
const mainSource = fs.readFileSync(path.join(root, 'static/js/app.js.src'), 'utf8');
const entryRuntime = fs.readFileSync(path.join(root, 'static/js/modal-entry.js'), 'utf8');
const entrySource = fs.readFileSync(path.join(root, 'static/js/modal-entry.js.src'), 'utf8');

for (const [label, text] of [['runtime', mainRuntime], ['source', mainSource]]) {
  test(`main bundle keeps lazy modal-data stubs and shared bulk state (${label})`, () => {
    assert.match(text, /function\s+resetModalState\s*\(\.\.\.args\)/);
    assert.match(text, /async function\s+loadAllMarketsAtOnce\s*\(\.\.\.args\)/);
    assert.match(text, /async function\s+loadChartWithTrends\s*\(\.\.\.args\)/);
    assert.doesNotMatch(text, /const\s+MODAL_CACHE_TTL\s*=/);
    assert.doesNotMatch(text, /let\s+modalDataCache\s*=/);
    assert.doesNotMatch(text, /function\s+getModalCacheKey\s*\(/);
    assert.doesNotMatch(text, /function\s+getModalCachedData\s*\(/);
    assert.doesNotMatch(text, /function\s+setModalCachedData\s*\(/);
    assert.match(text, /let\s+bulkHistoryCache\s*=\s*\{\}/);
    assert.match(text, /let\s+bulkHistoryCacheKey\s*=\s*''/);
  });
}

test('modal-entry runtime owns reset, modal cache, bulk fetch, and chart-history implementations', () => {
  for (const marker of [
    'function resetModalState(',
    'const MODAL_CACHE_TTL = 30000',
    'let modalDataCache = {}',
    'function getModalCacheKey(',
    'function getModalCachedData(',
    'function setModalCachedData(',
    'async function loadAllMarketsAtOnce(',
    'async function loadChartWithTrends(',
    'window.__sxfResetModalStateImpl = resetModalState',
    'window.__sxfLoadAllMarketsAtOnceImpl = loadAllMarketsAtOnce',
    'window.__sxfLoadChartWithTrendsImpl = loadChartWithTrends',
  ]) assert.ok(entrySource.includes(marker), `${marker} should be deferred`);
  assert.match(entryRuntime, /__sxfLoadChartWithTrendsImpl/);
});

test('modal-entry loader completeness includes data pipeline implementations', () => {
  for (const text of [mainSource, mainRuntime]) {
    assert.match(text, /__sxfResetModalStateImpl/);
    assert.match(text, /__sxfLoadAllMarketsAtOnceImpl/);
    assert.match(text, /__sxfLoadChartWithTrendsImpl/);
  }
});

test('mobile chart history still reaches lazy chart-history pipeline', () => {
  const start = mainSource.indexOf('async function loadChartHistory(');
  assert.ok(start >= 0);
  const end = mainSource.indexOf('\n}', start);
  const fn = mainSource.slice(start, end + 2);
  assert.match(fn, /await loadChartWithTrends\(/);
});

test('close and reset lifecycle still clear shared bulk cache', () => {
  assert.match(mainSource, /function closeModal\([\s\S]*?bulkHistoryCache = \{\};[\s\S]*?bulkHistoryCacheKey = '';/);
  assert.match(entrySource, /function resetModalState\([\s\S]*?bulkHistoryCache = \{\};[\s\S]*?bulkHistoryCacheKey = '';/);
});

test('shared loading UI helpers remain eager', () => {
  for (const marker of [
    'function showSmartMoneyLoading(',
    'function hideSmartMoneyLoading(',
    'function showChartLoading(',
    'function hideChartLoading(',
  ]) assert.ok(mainSource.includes(marker), `${marker} should stay eager`);
});

test('deferred modal data pipeline preserves request and stale-request guards', () => {
  assert.match(entrySource, /\/api\/match\/history\/bulk\?/);
  assert.match(entrySource, /\/api\/match\/history\?/);
  assert.match(entrySource, /modalLoadRequestId/);
});

test('modal chart-tab switching still reaches lazy chart-history pipeline', () => {
  const marker = "tab.addEventListener('click', async function()";
  const start = mainSource.indexOf(marker);
  assert.ok(start >= 0, 'chart-tab click handler should remain eager');
  const end = mainSource.indexOf('\n    });', start);
  assert.ok(end > start, 'chart-tab click handler should remain parseable');
  const handler = mainSource.slice(start, end + 7);
  assert.match(handler, /await loadChartWithTrends\(/);
});
''')

print('P2.18 staged')
print('app.js.src', APP_SRC.stat().st_size)
print('app.js', APP_RUN.stat().st_size)
print('modal-entry.js.src', ENTRY_SRC.stat().st_size)
print('modal-entry.js', ENTRY_RUN.stat().st_size)
