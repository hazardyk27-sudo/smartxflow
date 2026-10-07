const assert = require('node:assert/strict');
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
  assert.match(entrySource, /reqId && reqId !== _modalRequestId/);
});

test('modal chart-tab switching still reaches lazy chart-history pipeline', () => {
  const start = mainSource.indexOf('function setupModalChartTabs(');
  assert.ok(start >= 0);
  const end = mainSource.indexOf('function setupSearch(', start);
  assert.ok(end > start);
  const fn = mainSource.slice(start, end);
  assert.match(fn, /showChartLoading\(\)/);
  assert.match(fn, /loadChartWithTrends\(selectedMatch\.home_team, selectedMatch\.away_team, selectedChartMarket, selectedMatch\.league \|\| ''\)/);
});
