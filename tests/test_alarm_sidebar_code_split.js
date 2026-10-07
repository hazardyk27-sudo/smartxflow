const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.join(__dirname, '..');
const read = (rel) => {
  const file = path.join(root, rel);
  return fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : '';
};

const mainRuntime = read('static/js/app.js');
const mainSource = read('static/js/app.js.src');
const sidebarRuntime = read('static/js/alarm-sidebar.js');
const sidebarSource = read('static/js/alarm-sidebar.js.src');
const template = read('templates/index.html');

const mainBundles = [
  ['runtime', mainRuntime],
  ['source', mainSource]
];
const sidebarBundles = [
  ['runtime', sidebarRuntime],
  ['source', sidebarSource]
];

const publicDelegates = [
  ['loadAllAlarms', '__sxfLoadAllAlarmsImpl'],
  ['selectDateFilter', '__sxfSelectDateFilterImpl'],
  ['filterAlarms', '__sxfFilterAlarmsImpl'],
  ['searchAlarms', '__sxfSearchAlarmsImpl'],
  ['toggleAlarmDetail', '__sxfToggleAlarmDetailImpl'],
  ['loadMoreAlarms', '__sxfLoadMoreAlarmsImpl']
];

test('alarm sidebar shell stays eager but list runtime is lazy', () => {
  for (const [label, source] of mainBundles) {
    assert.match(source, /function openAlarmsSidebar\(/, `${label}: sidebar shell should remain eager`);
    assert.match(source, /loadAllAlarms\((?:false|true)\)/, `${label}: opening sidebar should trigger lazy list load`);
    assert.match(source, /function loadAlarmSidebarRuntime\(/, `${label}: lazy runtime loader should exist`);
    assert.match(source, /_sxfAlarmSidebarRuntimePromise/, `${label}: loader should be single-flight`);
    assert.match(source, /alarm-sidebar\.js/, `${label}: loader should target alarm-sidebar.js`);
  }
});

test('public alarm sidebar callbacks remain available as lazy delegates', () => {
  for (const [label, source] of mainBundles) {
    for (const [fnName, implName] of publicDelegates) {
      assert.match(source, new RegExp(`function ${fnName}\\(`), `${label}: ${fnName} stub should remain eager`);
      assert.match(source, new RegExp(implName), `${label}: ${fnName} should delegate to deferred implementation`);
    }
  }
});

test('heavy alarm list implementations move out of the main bundle', () => {
  const heavyFunctions = [
    'updateAlarmCounts',
    'updateDateFilterCounts',
    'filterAlarmsByMatchDate',
    'getFilteredAlarms',
    'renderAlarmsList'
  ];

  for (const [label, source] of mainBundles) {
    for (const fnName of heavyFunctions) {
      assert.doesNotMatch(source, new RegExp(`function ${fnName}\\(`), `${label}: ${fnName} implementation should be deferred`);
    }
  }

  for (const [label, source] of sidebarBundles) {
    assert.ok(source.length > 0, `${label}: deferred alarm-sidebar bundle should exist`);
    for (const fnName of heavyFunctions) {
      assert.match(source, new RegExp(`function ${fnName}\\(`), `${label}: ${fnName} implementation should live in deferred runtime`);
    }
  }
});

test('deferred runtime exposes every callback used after the sidebar opens', () => {
  for (const [label, source] of sidebarBundles) {
    for (const [, implName] of publicDelegates) {
      assert.match(source, new RegExp(`window\\.${implName}\\s*=`), `${label}: ${implName} should be exported`);
    }
  }
});

test('shared alarm cache, identity grouping, and alert-band navigation stay eager', () => {
  for (const [label, source] of mainBundles) {
    assert.match(source, /async function fetchAlarmsBatch\(/, `${label}: centralized alarm cache should remain eager`);
    assert.match(source, /function getCachedAlarmsWithType\(/, `${label}: shared cache projection should remain eager`);
    assert.match(source, /function groupAlarmsByMatch\(/, `${label}: shared alarm identity grouping should remain eager`);
    assert.match(source, /function goToMatchFromAlarm\(/, `${label}: alert-band navigation should remain eager`);
  }
});

test('template keeps one eager entrypoint for opening the sidebar', () => {
  assert.match(template, /onclick="toggleAlarmsSidebar\(\)"/);
  assert.match(template, /oninput="searchAlarms\(this\.value\)"/);
  assert.match(template, /onclick="selectDateFilter\('all'\)"/);
});
