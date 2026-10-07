const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.join(__dirname, '..');
const mainRuntime = fs.readFileSync(path.join(root, 'static/js/app.js'), 'utf8');
const mainSource = fs.readFileSync(path.join(root, 'static/js/app.js.src'), 'utf8');
const chartRuntime = fs.readFileSync(path.join(root, 'static/js/modal-chart.js'), 'utf8');
const chartSource = fs.readFileSync(path.join(root, 'static/js/modal-chart.js.src'), 'utf8');

const movedHelpers = [
  'getBucketConfig',
  'formatTimeLabel',
  'createBrushSlider',
  'drawMiniChart',
  'renderChartLegendFilters',
  'filterHistoryByTimeRange',
];

for (const helper of movedHelpers) {
  test(`${helper} lives only in deferred chart runtime`, () => {
    const signature = new RegExp(`function\\s+${helper}\\s*\\(`);
    assert.doesNotMatch(mainRuntime, signature, `${helper} must leave app.js`);
    assert.doesNotMatch(mainSource, signature, `${helper} must leave app.js.src`);
    assert.match(chartRuntime, signature, `${helper} must exist in modal-chart.js`);
    assert.match(chartSource, signature, `${helper} must exist in modal-chart.js.src`);
  });
}

test('eager bundle keeps chart loader and user-facing chart controls', () => {
  assert.match(mainSource, /function loadModalChartRuntime\s*\(/);
  assert.match(mainSource, /async function loadChart\s*\(/);
  assert.match(mainSource, /function resetChartZoom\s*\(/);
  assert.match(mainSource, /function toggleChartSeries\s*\(/);
  assert.match(mainSource, /function setChartTimeRange\s*\(/);
  assert.match(mainSource, /function setChartViewMode\s*\(/);
});

test('deferred chart implementation still consumes moved helpers', () => {
  assert.match(chartSource, /filterHistoryByTimeRange\(data\.history\)/);
  assert.match(chartSource, /getBucketConfig\(\)/);
  assert.match(chartSource, /formatTimeLabel\(/);
  assert.match(chartSource, /createBrushSlider\(/);
  assert.match(chartSource, /renderChartLegendFilters\(/);
});
