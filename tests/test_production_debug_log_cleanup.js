const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.join(__dirname, '..');

for (const file of ['static/js/app.js', 'static/js/app.js.src']) {
  test(`${file} has no production console.log calls`, () => {
    const text = fs.readFileSync(path.join(root, file), 'utf8');
    assert.doesNotMatch(
      text,
      /console\.log\s*\(/,
      'production console.log text must be absent; this intentionally avoids lexer false negatives'
    );
  });

  test(`${file} preserves warning/error diagnostics and core entrypoints`, () => {
    const text = fs.readFileSync(path.join(root, file), 'utf8');
    assert.match(text, /console\.error\s*\(/, 'error diagnostics must remain');
    assert.match(text, /console\.warn\s*\(/, 'warning diagnostics must remain');
    for (const marker of [
      'async function loadMatches',
      'function renderMatches',
      'function applySorting',
      'async function fetchAlarmsBatch',
      'async function loadAllMarketsAtOnce',
      'async function loadOddsTrend',
      'function getOddsTrend',
      'async function openMatchModal',
    ]) {
      assert.ok(text.includes(marker), `${marker} must remain`);
    }
  });
}

for (const file of ['static/js/live-tab.js', 'static/js/live-tab.js.src']) {
  test(`${file} has no production console.log calls`, () => {
    const text = fs.readFileSync(path.join(root, file), 'utf8');
    assert.doesNotMatch(text, /console\.log\s*\(/, 'deferred Live runtime must stay free of production console.log calls');
  });

  test(`${file} preserves the deferred Live renderer entrypoint`, () => {
    const text = fs.readFileSync(path.join(root, file), 'utf8');
    assert.match(text, /function\s+renderLiveMatches\s*\(/, 'renderLiveMatches must remain in the deferred Live runtime');
  });
}
