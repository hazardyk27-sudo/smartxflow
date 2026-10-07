const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.join(__dirname, '..');
const mainRuntime = fs.readFileSync(path.join(root, 'static/js/app.js'), 'utf8');
const mainSource = fs.readFileSync(path.join(root, 'static/js/app.js.src'), 'utf8');
const exportRuntime = fs.readFileSync(path.join(root, 'static/js/chart-export.js'), 'utf8');
const exportSource = fs.readFileSync(path.join(root, 'static/js/chart-export.js.src'), 'utf8');
const minifySource = fs.readFileSync(path.join(root, 'minify.py'), 'utf8');

const movedHelpers = [
  'generateExportFilename', 'isEXEEnvironment', 'showExportNotification',
  'savePNGViaAPI', 'showExportOverlay', 'removeExportOverlay',
  'exportChartPNGFallback',
];

for (const helper of movedHelpers) {
  test(`${helper} lives only in deferred chart export runtime`, () => {
    const signature = new RegExp(`(?:async\\s+)?function\\s+${helper}\\s*\\(`);
    assert.doesNotMatch(mainRuntime, signature);
    assert.doesNotMatch(mainSource, signature);
    assert.match(exportRuntime, signature);
    assert.match(exportSource, signature);
  });
}

test('eager bundle keeps lazy public export entrypoints', () => {
  assert.match(mainSource, /function _getChartExportRuntimeUrl\s*\(/);
  assert.match(mainSource, /function loadChartExportRuntime\s*\(/);
  assert.match(mainSource, /return '\/static\/js\/chart-export\.js' \+ query;/);
  assert.match(mainSource, /async function exportChartPNG\s*\(\.\.\.args\)/);
  assert.match(mainSource, /async function exportChartCSV\s*\(\.\.\.args\)/);
  assert.match(mainSource, /async function exportFullMatchTXT\s*\(\.\.\.args\)/);
  assert.match(mainSource, /window\.__sxfExportChartPNGImpl\(\.\.\.args\)/);
  assert.match(mainSource, /window\.__sxfExportChartCSVImpl\(\.\.\.args\)/);
  assert.match(mainSource, /window\.__sxfExportFullMatchTXTImpl\(\.\.\.args\)/);
});

test('loader is single-flight and retryable after failure', () => {
  assert.match(mainSource, /if \(window\._sxfChartExportRuntimePromise\) return window\._sxfChartExportRuntimePromise;/);
  const resets = mainSource.match(/window\._sxfChartExportRuntimePromise = null;/g) || [];
  assert.ok(resets.length >= 2);
});

test('deferred runtime publishes implementations and full TXT exporter', () => {
  assert.match(exportSource, /window\.__sxfExportChartPNGImpl = exportChartPNG;/);
  assert.match(exportSource, /window\.__sxfExportChartCSVImpl = exportChartCSV;/);
  assert.match(exportSource, /window\.__sxfExportFullMatchTXTImpl = exportFullMatchTXT;/);
  assert.match(exportSource, /SmartXFlow - Full Match Data Export/);
  assert.doesNotMatch(mainSource, /SmartXFlow - Full Match Data Export/);
});

test('canonical minifier includes chart export runtime', () => {
  assert.match(minifySource, /static\/js\/chart-export\.js\.src/);
  assert.match(minifySource, /static\/js\/chart-export\.js/);
});
