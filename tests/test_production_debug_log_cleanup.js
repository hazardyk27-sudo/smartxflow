const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.join(__dirname, '..');

function countExecutableConsoleLogs(text) {
  let count = 0;
  let i = 0;
  let quote = null;
  let escaped = false;
  let lineComment = false;
  let blockComment = false;
  const needle = 'console.log';

  while (i < text.length) {
    const ch = text[i];
    const next = text[i + 1] || '';

    if (lineComment) {
      if (ch === '\n') lineComment = false;
      i++;
      continue;
    }
    if (blockComment) {
      if (ch === '*' && next === '/') {
        blockComment = false;
        i += 2;
      } else {
        i++;
      }
      continue;
    }
    if (quote) {
      if (escaped) escaped = false;
      else if (ch === '\\') escaped = true;
      else if (ch === quote) quote = null;
      i++;
      continue;
    }

    if (ch === '/' && next === '/') {
      lineComment = true;
      i += 2;
      continue;
    }
    if (ch === '/' && next === '*') {
      blockComment = true;
      i += 2;
      continue;
    }
    if (ch === "'" || ch === '"' || ch === '`') {
      quote = ch;
      i++;
      continue;
    }

    if (text.startsWith(needle, i)) {
      let j = i + needle.length;
      while (j < text.length && /\s/.test(text[j])) j++;
      if (text[j] === '(') count++;
      i += needle.length;
      continue;
    }
    i++;
  }
  return count;
}

for (const file of ['static/js/app.js', 'static/js/app.js.src']) {
  test(`${file} has no executable production console.log calls`, () => {
    const text = fs.readFileSync(path.join(root, file), 'utf8');
    assert.equal(countExecutableConsoleLogs(text), 0, 'debug/success console.log calls must be stripped');
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
      'function renderLiveMatches',
      'async function openMatchModal',
    ]) {
      assert.ok(text.includes(marker), `${marker} must remain`);
    }
  });
}
