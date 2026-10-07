const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const bundles = [
  ['runtime', fs.readFileSync(path.join(__dirname, '..', 'static', 'js', 'app.js'), 'utf8')],
  ['source', fs.readFileSync(path.join(__dirname, '..', 'static', 'js', 'app.js.src'), 'utf8')],
];

for (const [name, source] of bundles) {
  test(`dashboard analysis entrypoints use lazy loader (${name})`, () => {
    assert.equal((source.match(/openTrendsModal\(/g) || []).length, 0);
    assert.ok((source.match(/openDeferredTrendsModal\(/g) || []).length >= 2);
    assert.match(source, /function getAnalysisStarHtml\(/);
    assert.match(source, /function _testGuardAnalysis\(/);
  });
}
