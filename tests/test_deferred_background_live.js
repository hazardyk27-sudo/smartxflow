const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function extractFunction(source, signature) {
  const start = source.indexOf(signature);
  assert.ok(start >= 0, `missing ${signature}`);
  const open = source.indexOf('{', start);
  let depth = 0;
  for (let i = open; i < source.length; i += 1) {
    if (source[i] === '{') depth += 1;
    else if (source[i] === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error(`unterminated ${signature}`);
}

for (const file of ['app.js.src', 'app.js']) {
  const source = fs.readFileSync(path.join(__dirname, '..', 'static', 'js', file), 'utf8');

  test(`background live waits for browser idle (${file})`, () => {
    const fn = extractFunction(source, 'function _startBackgroundLiveFetch()');
    let idleCallback = null;
    let fetchCount = 0;
    let intervalDelay = null;
    const context = {
      _bgLiveInterval: null,
      _bgLiveStartScheduled: false,
      _fetchBackgroundLiveData() { fetchCount += 1; },
      setInterval(callback, delay) { intervalDelay = delay; return 41; },
      window: {
        requestIdleCallback(callback, options) {
          assert.equal(options.timeout, 5000);
          idleCallback = callback;
          return 9;
        },
        setTimeout() { throw new Error('fallback timer should not run when requestIdleCallback exists'); }
      }
    };
    vm.runInNewContext(`${fn}\n_startBackgroundLiveFetch();`, context);
    assert.equal(fetchCount, 0, 'live request must not start synchronously during bootstrap');
    assert.equal(context._bgLiveStartScheduled, true);
    assert.equal(typeof idleCallback, 'function');

    idleCallback();
    assert.equal(fetchCount, 1);
    assert.equal(intervalDelay, 60000);
    assert.equal(context._bgLiveStartScheduled, false);
    assert.equal(context._bgLiveInterval, 41);
  });

  test(`background live uses delayed fallback without idle callback (${file})`, () => {
    const fn = extractFunction(source, 'function _startBackgroundLiveFetch()');
    let timeoutCallback = null;
    let timeoutDelay = null;
    let fetchCount = 0;
    const context = {
      _bgLiveInterval: null,
      _bgLiveStartScheduled: false,
      _fetchBackgroundLiveData() { fetchCount += 1; },
      setInterval() { return 12; },
      window: {
        setTimeout(callback, delay) {
          timeoutCallback = callback;
          timeoutDelay = delay;
          return 7;
        }
      }
    };
    vm.runInNewContext(`${fn}\n_startBackgroundLiveFetch();`, context);
    assert.equal(fetchCount, 0);
    assert.equal(timeoutDelay, 2500);
    assert.equal(typeof timeoutCallback, 'function');

    timeoutCallback();
    assert.equal(fetchCount, 1);
    assert.equal(context._bgLiveInterval, 12);
  });
}
