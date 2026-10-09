const assert = require('node:assert/strict');
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

  test(`first chart-open loader excludes export-only html2canvas (${name})`, () => {
    const start = source.indexOf('window.loadChartLibs');
    const end = source.indexOf('let currentMarket', start);
    assert.ok(start >= 0 && end > start, 'chart loader boundary should exist');
    const loader = source.slice(start, end);
    assert.doesNotMatch(loader, /html2canvas/);
    assert.match(source, /loadHtml2CanvasForExport/);
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
      assert.doesNotMatch(fn, /loadAllMarketsAtOnce/);
      assert.doesNotMatch(fn, /marketsPromise/);
    });
  }
}
