const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'static/js/modal-entry.js.src'), 'utf8');
const runtime = fs.readFileSync(path.join(root, 'static/js/modal-entry.js'), 'utf8');

function occurrences(text, needle) {
  return text.split(needle).length - 1;
}

test('bulk loader and chart pipeline use the same fixture-aware cache key in source', () => {
  const key = 'const cacheKey = `${home}|${away}|${league}|${matchIdHash}|${currentSource}`;';
  assert.equal(occurrences(source, key), 2,
    'source must use the same fixture-aware bulk cache key when writing and reading');
});

test('served runtime keeps the same fixture-aware cache key', () => {
  const key = 'const cacheKey=`${home}|${away}|${league}|${matchIdHash}|${currentSource}`;';
  assert.equal(occurrences(runtime, key), 2,
    'served runtime must use the same fixture-aware bulk cache key when writing and reading');
});

test('single-market history remains fallback-only after bulk cache lookup', () => {
  for (const text of [source, runtime]) {
    const cacheCheck = text.indexOf('bulkHistoryCacheKey===cacheKey') >= 0
      ? text.indexOf('bulkHistoryCacheKey===cacheKey')
      : text.indexOf('bulkHistoryCacheKey === cacheKey');
    const singleFetch = text.indexOf('/api/match/history?home=');
    assert.ok(cacheCheck >= 0, 'bulk cache check must remain');
    assert.ok(singleFetch > cacheCheck, 'single-market history request must remain after the bulk cache check');
  }
});
