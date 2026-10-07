const assert = require('node:assert/strict');
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

test('modal data helpers keep public lazy entrypoints in main bundle', () => {
  assert.match(mainSource, /function\s+resetModalState\s*\(\.\.\.args\)/);
  assert.match(mainSource, /async function\s+loadAllMarketsAtOnce\s*\(\.\.\.args\)/);
  assert.match(mainSource, /async function\s+loadChartWithTrends\s*\(\.\.\.args\)/);
  assert.match(mainSource, /loadModalEntryRuntime/);
});

test('modal-entry runtime is not eagerly executed by template', () => {
  assert.doesNotMatch(template, /<script[^>]+modal-entry\.js/);
});

test('canonical minifier includes modal-entry runtime', () => {
  assert.match(minifySource, /static\/js\/modal-entry\.js\.src/);
  assert.match(minifySource, /static\/js\/modal-entry\.js/);
});
