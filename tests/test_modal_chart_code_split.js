const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.join(__dirname, '..');
const bundles = [
  ['runtime', fs.readFileSync(path.join(root, 'static/js/app.js'), 'utf8')],
  ['source', fs.readFileSync(path.join(root, 'static/js/app.js.src'), 'utf8')],
];
const deferredRuntime = fs.readFileSync(path.join(root, 'static/js/modal-chart.js'), 'utf8');
const deferredSource = fs.readFileSync(path.join(root, 'static/js/modal-chart.js.src'), 'utf8');
const template = fs.readFileSync(path.join(root, 'templates/index.html'), 'utf8');

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

for (const [name, source] of bundles) {
  test(`main bundle keeps only the lazy loadChart stub (${name})`, () => {
    const fn = extractFunction(source, 'async function loadChart(');
    assert.match(fn, /loadModalChartRuntime\(\)/);
    assert.match(fn, /window\.__sxfLoadChartImpl/);
    assert.doesNotMatch(fn, /Error loading chart:/);
    assert.match(source, /function loadModalChartRuntime\(\)/);
  });
}

test('deferred chart implementation is not eagerly referenced by template', () => {
  assert.doesNotMatch(template, /modal-chart\.js/);
  assert.match(deferredRuntime, /window\.__sxfLoadChartImpl\s*=\s*async function loadChart/);
  assert.match(deferredSource, /window\.__sxfLoadChartImpl\s*=\s*async function loadChart/);
  assert.match(deferredRuntime, /Error loading chart:/);
});

test('modal chart loader deduplicates concurrent requests and inherits app asset version', async () => {
  const source = bundles[1][1];
  const urlFn = extractFunction(source, 'function _getModalChartRuntimeUrl(');
  const loaderFn = extractFunction(source, 'function loadModalChartRuntime(');
  const stubFn = extractFunction(source, 'async function loadChart(');
  const appended = [];
  const windowObj = {};
  const context = vm.createContext({
    window: windowObj,
    document: {
      getElementsByTagName(name) {
        assert.equal(name, 'script');
        return [{ src: 'https://preview.example/static/js/app.js?v=abc123' }];
      },
      createElement(name) {
        assert.equal(name, 'script');
        return {};
      },
      head: {
        appendChild(script) {
          appended.push(script);
          setImmediate(() => {
            windowObj.__sxfLoadChartImpl = async (...args) => args.join('|');
            script.onload();
          });
        }
      }
    },
    Promise,
    Error,
    setImmediate,
  });
  vm.runInContext(`${urlFn}\n${loaderFn}\n${stubFn}\nwindow.__testLoadChart = loadChart;`, context);

  const [a, b] = await Promise.all([
    windowObj.__testLoadChart('A', 'B'),
    windowObj.__testLoadChart('C', 'D'),
  ]);
  assert.equal(appended.length, 1, 'concurrent modal opens must share one script request');
  assert.equal(appended[0].src, '/static/js/modal-chart.js?v=abc123');
  assert.equal(a, 'A|B');
  assert.equal(b, 'C|D');
});
