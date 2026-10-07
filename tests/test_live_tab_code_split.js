const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.join(__dirname, '..');
const mainSource = fs.readFileSync(path.join(root, 'static/js/app.js.src'), 'utf8');
const mainRuntime = fs.readFileSync(path.join(root, 'static/js/app.js'), 'utf8');
const liveSourcePath = path.join(root, 'static/js/live-tab.js.src');
const liveRuntimePath = path.join(root, 'static/js/live-tab.js');
const liveSource = fs.existsSync(liveSourcePath) ? fs.readFileSync(liveSourcePath, 'utf8') : '';
const liveRuntime = fs.existsSync(liveRuntimePath) ? fs.readFileSync(liveRuntimePath, 'utf8') : '';
const minifySource = fs.readFileSync(path.join(root, 'minify.py'), 'utf8');

for (const [label, text] of [['source', mainSource], ['runtime', mainRuntime]]) {
  test(`main bundle keeps only Live-tab lazy entrypoints (${label})`, () => {
    assert.match(text, /function\s+loadLiveTabRuntime\s*\(/);
    assert.match(text, /async\s+function\s+switchToLive\s*\(\.\.\.args\)/);
    assert.doesNotMatch(text, /function\s+renderLiveMatches\s*\(/);
    assert.doesNotMatch(text, /function\s+_renderLiveProLock\s*\(/);
    assert.doesNotMatch(text, /function\s+loadLiveMatches\s*\(/);
    assert.doesNotMatch(text, /function\s+_startGoalTakeover\s*\(/);
    assert.doesNotMatch(text, /function\s+_calcLiveMatchMin\s*\(/);
    assert.doesNotMatch(text, /function\s+_liveMobileCard\s*\(/);
  });
}

test('background Live polling and shared helpers stay eager', () => {
  assert.match(mainSource, /async\s+function\s+_fetchBackgroundLiveData\s*\(/);
  assert.match(mainSource, /function\s+_updateLiveCapsulesInDOM\s*\(/);
  assert.match(mainSource, /function\s+_startBackgroundLiveFetch\s*\(/);
  assert.match(mainSource, /function\s+switchFromLive\s*\(/);
  assert.match(mainSource, /function\s+proLockPanelHtml\s*\(/);
  assert.match(mainSource, /function\s+formatLiveVol\s*\(/);
  assert.match(mainSource, /function\s+escLiveHtml\s*\(/);
  assert.match(mainSource, /function\s+_minuteToNum\s*\(/);
});

test('deferred Live runtime owns heavy Live-tab implementations', () => {
  assert.match(liveSource, /function\s+switchToLive\s*\(/);
  assert.match(liveSource, /function\s+renderLiveMatches\s*\(/);
  assert.match(liveSource, /function\s+_renderLiveProLock\s*\(/);
  assert.match(liveSource, /function\s+loadLiveMatches\s*\(/);
  assert.match(liveSource, /function\s+_startGoalTakeover\s*\(/);
  assert.match(liveSource, /function\s+_calcLiveMatchMin\s*\(/);
  assert.match(liveSource, /function\s+_liveMobileCard\s*\(/);
  assert.match(liveSource, /window\.__sxfSwitchToLiveImpl\s*=\s*switchToLive;/);
  assert.match(liveSource, /window\.__sxfOpenLiveDetailImpl\s*=\s*openLiveDetail;/);
  assert.match(liveRuntime, /__sxfSwitchToLiveImpl/);
});

test('Live loader inherits app asset version and is single-flight/retryable', () => {
  assert.match(mainSource, /return '\/static\/js\/live-tab\.js' \+ query;/);
  assert.match(mainSource, /if \(window\._sxfLiveTabRuntimePromise\) return window\._sxfLiveTabRuntimePromise;/);
  const resets = mainSource.match(/window\._sxfLiveTabRuntimePromise = null;/g) || [];
  assert.ok(resets.length >= 2);
});

test('Live public entrypoints delegate through the deferred runtime', () => {
  const entrypoints = [
    ['switchToLive', '__sxfSwitchToLiveImpl'],
    ['setLiveMarket', '__sxfSetLiveMarketImpl'],
    ['toggleLiveMarketDropdown', '__sxfToggleLiveMarketDropdownImpl'],
    ['setLiveMarketFromDropdown', '__sxfSetLiveMarketFromDropdownImpl'],
    ['openLiveDetail', '__sxfOpenLiveDetailImpl'],
    ['setLiveDetailMarket', '__sxfSetLiveDetailMarketImpl'],
    ['closeLiveDetail', '__sxfCloseLiveDetailImpl'],
  ];
  for (const [fn, impl] of entrypoints) {
    const re = new RegExp(`async\\s+function\\s+${fn}\\s*\\(\\.\\.\\.args\\)[\\s\\S]*?loadLiveTabRuntime\\(\\)[\\s\\S]*?window\\.${impl}\\(\\.\\.\\.args\\)`);
    assert.match(mainSource, re, `${fn} should lazy-delegate to ${impl}`);
  }
});

test('pending Live activation is cancelled when the user leaves before runtime load completes', () => {
  assert.match(mainSource, /window\._sxfLiveTabEntryGeneration\s*=\s*window\._sxfLiveTabEntryGeneration\s*\|\|\s*0/);
  assert.match(mainSource, /function\s+_cancelPendingLiveTabEntry\s*\(\)[\s\S]*?_sxfLiveTabEntryGeneration\s*\+=\s*1/);
  assert.match(mainSource, /const\s+entryGeneration\s*=\s*\+\+window\._sxfLiveTabEntryGeneration;[\s\S]*?await\s+loadLiveTabRuntime\(\);[\s\S]*?if\s*\(entryGeneration\s*!==\s*window\._sxfLiveTabEntryGeneration\)\s*return;/);
  assert.match(mainSource, /window\.setTab\s*=\s*function\(market\)[\s\S]*?market\s*!==\s*'live'[\s\S]*?_cancelPendingLiveTabEntry\(\)/);
  assert.match(mainSource, /window\.setMobileGroup\s*=\s*function\(group\)[\s\S]*?_cancelPendingLiveTabEntry\(\)/);
});

test('canonical minifier includes the Live-tab runtime', () => {
  assert.match(minifySource, /static\/js\/live-tab\.js\.src/);
  assert.match(minifySource, /static\/js\/live-tab\.js/);
});
