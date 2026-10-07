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
  test(`dashboard schedules deferred modal prefetch (${name})`, () => {
    assert.match(source, /function scheduleDeferredModalRuntimePrefetch\(\)/);
    assert.match(
      source,
      /runOptionalStartupTask\('modal runtime prefetch',\s*scheduleDeferredModalRuntimePrefetch\)/
    );
  });

  test(`modal prefetch waits for idle and does not execute scripts (${name})`, () => {
    const fn = extractFunction(source, 'function scheduleDeferredModalRuntimePrefetch(');
    let idleCallback = null;
    const created = [];
    const appended = [];
    const windowObj = {
      requestIdleCallback(callback, options) {
        idleCallback = callback;
        assert.equal(options.timeout, 7000);
      }
    };
    const context = vm.createContext({
      window: windowObj,
      document: {
        createElement(tag) {
          created.push(tag);
          return { dataset: {} };
        },
        head: {
          appendChild(node) { appended.push(node); }
        }
      },
      _getModalChartRuntimeUrl: () => '/static/js/modal-chart.js?v=test',
      _getModalAlarmsRuntimeUrl: () => '/static/js/modal-alarms.js?v=test',
      setTimeout() { throw new Error('timer fallback should not run with requestIdleCallback'); },
    });
    vm.runInContext(`let _sxfDeferredModalPrefetchScheduled = false;\n${fn}\nwindow.__testPrefetch = scheduleDeferredModalRuntimePrefetch;`, context);
    windowObj.__testPrefetch();
    assert.equal(appended.length, 0, 'no prefetch request should start before idle');
    assert.equal(typeof idleCallback, 'function');
    idleCallback();
    assert.deepEqual(created, ['link', 'link'], 'prefetch must use links, not executable script tags');
    assert.equal(appended.length, 2);
    assert.deepEqual(appended.map(x => x.rel), ['prefetch', 'prefetch']);
    assert.deepEqual(appended.map(x => x.as), ['script', 'script']);
    assert.deepEqual(appended.map(x => x.href), [
      '/static/js/modal-chart.js?v=test',
      '/static/js/modal-alarms.js?v=test'
    ]);
    windowObj.__testPrefetch();
    assert.equal(appended.length, 2, 'prefetch scheduling must deduplicate repeated calls');
  });

  test(`modal prefetch skips already loaded runtimes (${name})`, () => {
    const fn = extractFunction(source, 'function scheduleDeferredModalRuntimePrefetch(');
    let timerCallback = null;
    let timerDelay = null;
    const appended = [];
    const windowObj = {
      __sxfLoadChartImpl: () => {},
    };
    const context = vm.createContext({
      window: windowObj,
      document: {
        createElement() { return { dataset: {} }; },
        head: { appendChild(node) { appended.push(node); } }
      },
      _getModalChartRuntimeUrl: () => '/static/js/modal-chart.js?v=test',
      _getModalAlarmsRuntimeUrl: () => '/static/js/modal-alarms.js?v=test',
      setTimeout(callback, delay) {
        timerCallback = callback;
        timerDelay = delay;
      },
    });
    vm.runInContext(`let _sxfDeferredModalPrefetchScheduled = false;\n${fn}\nwindow.__testPrefetch = scheduleDeferredModalRuntimePrefetch;`, context);
    windowObj.__testPrefetch();
    assert.equal(timerDelay, 4000);
    assert.equal(appended.length, 0);
    timerCallback();
    assert.equal(appended.length, 1);
    assert.equal(appended[0].href, '/static/js/modal-alarms.js?v=test');
  });
}
