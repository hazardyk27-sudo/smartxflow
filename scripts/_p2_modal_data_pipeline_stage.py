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


def extract_function(text: str, marker: str):
    start = text.find(marker)
    if start < 0:
        raise RuntimeError(f'missing marker: {marker}')
    brace = text.find('{', start)
    if brace < 0:
        raise RuntimeError(f'missing function body: {marker}')
    end = find_balanced_end(text, brace)
    while end < len(text) and text[end] in ' \t':
        end += 1
    if end < len(text) and text[end] == ';':
        end += 1
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

# 1) resetModalState: modal-entry-only in the current eager bundle.
s0, s1, reset_src = extract_function(source, 'function resetModalState(')
r0, r1, reset_run = extract_function(runtime, 'function resetModalState(')
parity(reset_src, reset_run, 'resetModalState')
if source.count('resetModalState(') != 1:
    raise SystemExit(f'P2.18 unexpected eager resetModalState callers: {source.count("resetModalState(")}')

# 2) Cache/bulk/history pipeline is contiguous from bulk cache declarations through loadChartWithTrends.
state_marker = 'let bulkHistoryCache = {};'
bs0 = source.find(state_marker)
br0 = runtime.find('let bulkHistoryCache={};')
if bs0 < 0 or br0 < 0:
    raise SystemExit('P2.18 bulk history state marker missing')
_, bs1, chart_src = extract_function(source, 'async function loadChartWithTrends(')
_, br1, chart_run = extract_function(runtime, 'async function loadChartWithTrends(')
source_pipeline = source[bs0:bs1]
runtime_pipeline = runtime[br0:br1]
parity(source_pipeline, runtime_pipeline, 'modal data pipeline')

# No hidden eager consumers of private cache state/helpers are allowed.
# resetModalState is moving in the same change, so its cache-reset references are part of the owned target.
private_names = [
    'bulkHistoryCache', 'bulkHistoryCacheKey', 'MODAL_CACHE_TTL', 'modalDataCache',
    'getModalCacheKey', 'getModalCachedData', 'setModalCachedData'
]
for name in private_names:
    owned_count = source_pipeline.count(name) + reset_src.count(name)
    if source.count(name) != owned_count:
        raise SystemExit(f'P2.18 {name} has an eager consumer outside reset + pipeline target')

# loadAllMarketsAtOnce should only be the eager definition now that modal entry orchestration is deferred.
if source.count('loadAllMarketsAtOnce(') != 1:
    raise SystemExit(f'P2.18 unexpected eager loadAllMarketsAtOnce callers: {source.count("loadAllMarketsAtOnce(")}')
# loadChartWithTrends has its definition plus the mobile chart-history caller.
if source.count('loadChartWithTrends(') != 2:
    raise SystemExit(f'P2.18 unexpected eager loadChartWithTrends references: {source.count("loadChartWithTrends(")}')

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

# Re-locate pipeline after the earlier replacement changed offsets.
bs0 = source.find(state_marker)
br0 = runtime.find('let bulkHistoryCache={};')
_, bs1, _ = extract_function(source, 'async function loadChartWithTrends(')
_, br1, _ = extract_function(runtime, 'async function loadChartWithTrends(')
source = source[:bs0] + pipeline_stub_src + source[bs1:]
runtime = runtime[:br0] + pipeline_stub_run + runtime[br1:]

# Expand loader completeness contract so a partially loaded modal-entry runtime cannot pass readiness.
ls0, ls1, loader_src_old = extract_function(source, 'function loadModalEntryRuntime(')
lr0, lr1, loader_run_old = extract_function(runtime, 'function loadModalEntryRuntime(')
parity(loader_src_old, loader_run_old, 'modal-entry loader')
loader_src_new = loader_src_old
needle = "typeof window.__sxfOpenMatchModalImpl === 'function';"
replacement = "typeof window.__sxfOpenMatchModalImpl === 'function' &&\n        typeof window.__sxfResetModalStateImpl === 'function' &&\n        typeof window.__sxfLoadAllMarketsAtOnceImpl === 'function' &&\n        typeof window.__sxfLoadChartWithTrendsImpl === 'function';"
if loader_src_new.count(needle) != 2:
    raise SystemExit(f'P2.18 expected two modal-entry readiness tails, found {loader_src_new.count(needle)}')
loader_src_new = loader_src_new.replace(needle, replacement)
loader_run_new = rjsmin.jsmin(loader_src_new)
source = source[:ls0] + loader_src_new + source[ls1:]
runtime = runtime[:lr0] + loader_run_new + runtime[lr1:]

# Append original behavior to the existing modal-entry IIFE; local function declarations are hoisted.
close_marker = '\n})();'
if entry_source.count(close_marker) != 1:
    raise SystemExit('P2.18 modal-entry IIFE close marker mismatch')
exports = r'''

window.__sxfResetModalStateImpl = resetModalState;
window.__sxfLoadAllMarketsAtOnceImpl = loadAllMarketsAtOnce;
window.__sxfLoadChartWithTrendsImpl = loadChartWithTrends;
'''
append_block = '\n\n' + reset_src.strip() + '\n\n' + source_pipeline.strip() + exports
entry_source = entry_source.replace(close_marker, append_block + close_marker, 1)
entry_runtime = rjsmin.jsmin(entry_source)

APP_SRC.write_text(source)
APP_RUN.write_text(runtime)
ENTRY_SRC.write_text(entry_source)
ENTRY_RUN.write_text(entry_runtime)

# P2.17 test now verifies public/shared entrypoints as lazy stubs rather than eager implementations.
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
  test(`main bundle keeps lazy modal-data stubs only (${label})`, () => {
    assert.match(text, /function\s+resetModalState\s*\(\.\.\.args\)/);
    assert.match(text, /async function\s+loadAllMarketsAtOnce\s*\(\.\.\.args\)/);
    assert.match(text, /async function\s+loadChartWithTrends\s*\(\.\.\.args\)/);
    assert.doesNotMatch(text, /const\s+MODAL_CACHE_TTL\s*=/);
    assert.doesNotMatch(text, /let\s+modalDataCache\s*=/);
    assert.doesNotMatch(text, /let\s+bulkHistoryCache\s*=/);
    assert.doesNotMatch(text, /function\s+getModalCacheKey\s*\(/);
    assert.doesNotMatch(text, /function\s+getModalCachedData\s*\(/);
    assert.doesNotMatch(text, /function\s+setModalCachedData\s*\(/);
  });
}

test('modal-entry runtime owns reset, cache, bulk, and chart-history implementations', () => {
  for (const marker of [
    'function resetModalState(',
    'let bulkHistoryCache = {}',
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
  assert.match(entrySource, /reqId && reqId !== _modalRequestId/);
  assert.match(entrySource, /await updateMatchInfoCard\(\)/);
  assert.match(entrySource, /await loadChart\(/);
});
''')

print('P2.18 staged')
print('app.js.src', APP_SRC.stat().st_size)
print('app.js', APP_RUN.stat().st_size)
print('modal-entry.js.src', ENTRY_SRC.stat().st_size)
print('modal-entry.js', ENTRY_RUN.stat().st_size)
