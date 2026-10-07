const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const bundles = [
  ['runtime', fs.readFileSync(path.join(__dirname, '..', 'static', 'js', 'app.js'), 'utf8')],
  ['source', fs.readFileSync(path.join(__dirname, '..', 'static', 'js', 'app.js.src'), 'utf8')],
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

for (const [name, source] of bundles) {
  test(`chart libraries are absent from dashboard startup (${name})`, () => {
    const bootstrap = extractBootstrap(source);
    assert.doesNotMatch(bootstrap, /loadChartLibs/);
    assert.doesNotMatch(bootstrap, /chart libraries/);
  });

  for (const signature of [
    'async function openMatchModalFromMatches(',
    'async function openMatchModalFromAPI(',
    'async function openMatchModal(',
  ]) {
    test(`${signature} keeps on-demand chart loading (${name})`, () => {
      const fn = extractFunction(source, signature);
      assert.match(fn, /loadChartLibs/);
      assert.match(fn, /registerChartPlugins/);
    });
  }
}
