const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.join(__dirname, '..');
const mainSource = fs.readFileSync(path.join(root, 'static/js/app.js.src'), 'utf8');
const mainRuntime = fs.readFileSync(path.join(root, 'static/js/app.js'), 'utf8');
const indexHtml = fs.readFileSync(path.join(root, 'templates/index.html'), 'utf8');

for (const [label, text] of [['source', mainSource], ['runtime', mainRuntime]]) {
  test(`legacy Alert Band detail renderer is absent (${label})`, () => {
    assert.doesNotMatch(text, /function\s+showAlertBandDetail\s*\(/);
    assert.doesNotMatch(text, /function\s+formatAlertValue\s*\(/);
  });

  test(`active Alert Band flow remains intact (${label})`, () => {
    assert.match(text, /(?:async\s+)?function\s+loadAlertBand\s*\(/);
    assert.match(text, /function\s+renderAlertBand\s*\(/);
    assert.match(text, /function\s+getAlertType\s*\(/);
    assert.match(text, /(?:async\s+)?function\s+goToMatchFromAlarm\s*\(/);
    assert.match(text, /goToMatchFromAlarm\s*\(/);
  });
}

test('template has no legacy Alert Band detail callbacks', () => {
  assert.doesNotMatch(indexHtml, /showAlertBandDetail/);
  assert.doesNotMatch(indexHtml, /formatAlertValue/);
});

test('active Alert Band still boots after license and refreshes periodically', () => {
  assert.match(mainSource, /setInterval\s*\(\s*\(\)\s*=>\s*\{\s*if\s*\(_isLicensed\)\s*loadAlertBand\(\);\s*\}\s*,\s*120000\s*\)/);
  assert.match(mainSource, /setTimeout\s*\(\s*loadAlertBand\s*,\s*500\s*\)/);
});
