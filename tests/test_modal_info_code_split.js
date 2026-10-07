const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.join(__dirname, '..');
const mainRuntime = fs.readFileSync(path.join(root, 'static/js/app.js'), 'utf8');
const mainSource = fs.readFileSync(path.join(root, 'static/js/app.js.src'), 'utf8');
const infoRuntime = fs.readFileSync(path.join(root, 'static/js/modal-info.js'), 'utf8');
const infoSource = fs.readFileSync(path.join(root, 'static/js/modal-info.js.src'), 'utf8');
const entryRuntime = fs.readFileSync(path.join(root, 'static/js/modal-entry.js'), 'utf8');
const entrySource = fs.readFileSync(path.join(root, 'static/js/modal-entry.js.src'), 'utf8');
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
  assert.match(entrySource, /await updateMatchInfoCard\(\);[\s\S]{0,120}await loadChart\(home, away, market, league\);/);
  assert.match(entryRuntime, /await updateMatchInfoCard\(\);await loadChart\(home,away,market,league\)/);
});

test('shared trend helper remains eager', () => {
  assert.match(mainSource, /function\s+getTrendArrow\s*\(current, previous\)/);
  assert.doesNotMatch(infoSource, /function\s+getTrendArrow\s*\(/);
});

test('canonical minifier includes modal info runtime', () => {
  assert.match(minifySource, /static\/js\/modal-info\.js\.src/);
  assert.match(minifySource, /static\/js\/modal-info\.js/);
});