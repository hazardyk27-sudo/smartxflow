const assert = require('node:assert/strict');
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
  assert.match(mainSource, /await loadModalChartRuntime\(\);\s*if \(typeof isMobile === 'function' && isMobile\(\)\) await loadMobileChartPanelRuntime\(\);\s*return window\.__sxfLoadChartImpl/);
  assert.match(mainRuntime, /await loadModalChartRuntime\(\);\s*if \(typeof isMobile === 'function' && isMobile\(\)\) await loadMobileChartPanelRuntime\(\);\s*return window\.__sxfLoadChartImpl/);
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
