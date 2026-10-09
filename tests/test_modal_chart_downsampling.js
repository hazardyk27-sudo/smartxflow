const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.join(__dirname, '..');
const runtime = fs.readFileSync(path.join(root, 'static/js/modal-chart.js'), 'utf8');
const source = fs.readFileSync(path.join(root, 'static/js/modal-chart.js.src'), 'utf8');

function extractFunction(text, signature) {
  const start = text.indexOf(signature);
  assert.ok(start >= 0, `${signature} should exist`);
  const bodyStart = text.indexOf('{', start);
  let depth = 0;
  for (let i = bodyStart; i < text.length; i += 1) {
    if (text[i] === '{') depth += 1;
    if (text[i] === '}') {
      depth -= 1;
      if (depth === 0) return text.slice(start, i + 1);
    }
  }
  assert.fail(`${signature} should have a closing brace`);
}

function loadSampler(text) {
  const fn = extractFunction(text, 'function getChartRenderSampleIndexes(');
  const context = vm.createContext({ Math, Array, Number });
  vm.runInContext(`${fn}\nthis.sample = getChartRenderSampleIndexes;`, context);
  return context.sample;
}

for (const [name, text] of [['runtime', runtime], ['source', source]]) {
  test(`chart render cap is present in ${name}`, () => {
    assert.match(text, /isMobile\(\)\s*\?\s*220\s*:\s*320/);
    assert.match(text, /getChartRenderSampleIndexes\(datasets,\s*chartPointBudget\)/);
    assert.match(text, /sampledHistory/);
    assert.match(text, /pointRadius/);
    assert.match(text, /pointBackgroundColor/);
    assert.match(text, /pointBorderColor/);
  });

  test(`sampler preserves endpoints and point budgets in ${name}`, () => {
    const sample = loadSampler(text);
    const datasets = [
      { data: Array.from({ length: 742 }, (_, i) => 40 + Math.sin(i / 13) * 8) },
      { data: Array.from({ length: 742 }, (_, i) => 35 + Math.cos(i / 17) * 6) },
    ];

    const desktop = Array.from(sample(datasets, 320));
    const mobile = Array.from(sample(datasets, 220));

    assert.ok(desktop.length <= 320 && desktop.length > 2);
    assert.ok(mobile.length <= 220 && mobile.length > 2);
    assert.equal(desktop[0], 0);
    assert.equal(desktop.at(-1), 741);
    assert.equal(mobile[0], 0);
    assert.equal(mobile.at(-1), 741);
    assert.ok(desktop.every((value, index) => index === 0 || value > desktop[index - 1]));
    assert.ok(mobile.every((value, index) => index === 0 || value > mobile[index - 1]));
  });

  test(`sampler leaves small series untouched and keeps a sharp move in ${name}`, () => {
    const sample = loadSampler(text);
    const small = [{ data: Array.from({ length: 50 }, (_, i) => i) }];
    assert.deepEqual(Array.from(sample(small, 320)), Array.from({ length: 50 }, (_, i) => i));

    const spike = Array.from({ length: 742 }, (_, i) => i / 1000);
    spike[250] = 1000;
    const sampled = Array.from(sample([{ data: spike }], 220));
    assert.ok(sampled.includes(250), 'sharp local move should survive render downsampling');
  });
}
