const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function extractFinishedStartup(source) {
  const start = source.indexOf("runOptionalStartupTask('finished scores'");
  assert.ok(start >= 0, 'finished score startup task should exist');
  const end = source.indexOf("runOptionalStartupTask('favorites'", start);
  assert.ok(end > start, 'favorites startup should follow finished scores');
  return source.slice(start, end);
}

for (const file of ['app.js.src', 'app.js']) {
  const source = fs.readFileSync(path.join(__dirname, '..', 'static', 'js', file), 'utf8');
  const snippet = extractFinishedStartup(source);

  test(`finished scores wait for browser idle (${file})`, () => {
    let idleCallback = null;
    let calls = 0;
    let rerenderArg = null;
    const context = {
      runOptionalStartupTask(name, task) {
        assert.equal(name, 'finished scores');
        task();
      },
      loadFinishedScores(arg) {
        calls += 1;
        rerenderArg = arg;
      },
      setTimeout() {
        throw new Error('timer fallback must not run when requestIdleCallback exists');
      },
      window: {
        requestIdleCallback(callback, options) {
          idleCallback = callback;
          assert.equal(options.timeout, 5000);
        }
      }
    };

    vm.runInNewContext(snippet, context);
    assert.equal(calls, 0, 'finished scores must not fetch synchronously during dashboard bootstrap');
    assert.equal(typeof idleCallback, 'function');
    idleCallback();
    assert.equal(calls, 1);
    assert.equal(rerenderArg, true, 'late score arrival must repaint already-rendered matches');
  });

  test(`finished scores use delayed fallback (${file})`, () => {
    let timerCallback = null;
    let timerDelay = null;
    let calls = 0;
    const context = {
      runOptionalStartupTask(name, task) { task(); },
      loadFinishedScores(arg) {
        calls += 1;
        assert.equal(arg, true);
      },
      setTimeout(callback, delay) {
        timerCallback = callback;
        timerDelay = delay;
        return 7;
      },
      window: {}
    };

    vm.runInNewContext(snippet, context);
    assert.equal(calls, 0);
    assert.equal(timerDelay, 2500);
    assert.equal(typeof timerCallback, 'function');
    timerCallback();
    assert.equal(calls, 1);
  });
}
