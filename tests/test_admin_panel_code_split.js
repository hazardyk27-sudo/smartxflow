const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.join(__dirname, '..');
const mainSource = fs.readFileSync(path.join(root, 'static/js/app.js.src'), 'utf8');
const mainRuntime = fs.readFileSync(path.join(root, 'static/js/app.js'), 'utf8');
const adminSourcePath = path.join(root, 'static/js/admin-panel.js.src');
const adminRuntimePath = path.join(root, 'static/js/admin-panel.js');
const adminSource = fs.existsSync(adminSourcePath) ? fs.readFileSync(adminSourcePath, 'utf8') : '';
const adminRuntime = fs.existsSync(adminRuntimePath) ? fs.readFileSync(adminRuntimePath, 'utf8') : '';
const minifySource = fs.readFileSync(path.join(root, 'minify.py'), 'utf8');

for (const [label, text] of [['source', mainSource], ['runtime', mainRuntime]]) {
  test(`main bundle keeps only Admin-panel lazy entrypoints (${label})`, () => {
    assert.match(text, /function\s+loadAdminPanelRuntime\s*\(/);
    assert.match(text, /async\s+function\s+openAdminPanel\s*\(\.\.\.args\)/);
    assert.match(text, /async\s+function\s+closeAdminPanel\s*\(\.\.\.args\)/);
    assert.match(text, /async\s+function\s+switchAdminTab\s*\(\.\.\.args\)/);
    assert.doesNotMatch(text, /function\s+loadAdminVolumeLeaderData\s*\(/);
    assert.doesNotMatch(text, /function\s+loadAdminDroppingData\s*\(/);
    assert.doesNotMatch(text, /function\s+loadAdminMimData\s*\(/);
    assert.doesNotMatch(text, /function\s+saveVolumeLeaderConfig\s*\(/);
    assert.doesNotMatch(text, /function\s+saveDroppingConfig\s*\(/);
    assert.doesNotMatch(text, /function\s+saveMimConfig\s*\(/);
  });
}

test('admin hotkey and shared alarm/license helpers stay eager', () => {
  assert.match(mainSource, /e\.ctrlKey\s*&&\s*e\.shiftKey\s*&&\s*e\.key\s*===\s*'A'/);
  assert.match(mainSource, /openAdminPanel\(\)/);
  assert.match(mainSource, /async\s+function\s+fetchAlarmsBatch\s*\(/);
  assert.match(mainSource, /function\s+getCachedAlarmsByType\s*\(/);
  assert.match(mainSource, /function\s+checkWebLicense\s*\(/);
});

test('deferred Admin runtime owns renderer/config implementations', () => {
  for (const fn of [
    'openAdminPanel', 'closeAdminPanel', 'switchAdminTab',
    'loadAdminVolumeLeaderData', 'saveVolumeLeaderConfig', 'calculateVolumeLeaderAlarms', 'deleteVolumeLeaderAlarms',
    'loadAdminDroppingData', 'saveDroppingConfig', 'calculateDroppingAlarms', 'deleteDroppingAlarms',
    'loadAdminMimData', 'saveMimConfig', 'deleteMimAlarms',
  ]) {
    assert.match(adminSource, new RegExp(`function\\s+${fn}\\s*\\(`), `${fn} should live in deferred Admin source`);
  }
  assert.match(adminSource, /window\.__sxfOpenAdminPanelImpl\s*=\s*openAdminPanel;/);
  assert.match(adminSource, /window\.__sxfCloseAdminPanelImpl\s*=\s*closeAdminPanel;/);
  assert.match(adminSource, /window\.__sxfSwitchAdminTabImpl\s*=\s*switchAdminTab;/);
  for (const fn of [
    'saveVolumeLeaderConfig', 'calculateVolumeLeaderAlarms', 'deleteVolumeLeaderAlarms',
    'saveDroppingConfig', 'calculateDroppingAlarms', 'deleteDroppingAlarms',
    'saveMimConfig', 'deleteMimAlarms',
  ]) {
    assert.match(adminSource, new RegExp(`window\\.${fn}\\s*=\\s*${fn};`), `${fn} should be exposed for inline Admin buttons`);
  }
  assert.match(adminRuntime, /__sxfOpenAdminPanelImpl/);
});

test('Admin loader inherits app asset version and is single-flight/retryable', () => {
  assert.match(mainSource, /return '\/static\/js\/admin-panel\.js' \+ query;/);
  assert.match(mainSource, /if \(window\._sxfAdminPanelRuntimePromise\) return window\._sxfAdminPanelRuntimePromise;/);
  const resets = mainSource.match(/window\._sxfAdminPanelRuntimePromise = null;/g) || [];
  assert.ok(resets.length >= 2);
});

test('Admin public entrypoints lazy-delegate through the runtime', () => {
  const entrypoints = [
    ['openAdminPanel', '__sxfOpenAdminPanelImpl'],
    ['closeAdminPanel', '__sxfCloseAdminPanelImpl'],
    ['switchAdminTab', '__sxfSwitchAdminTabImpl'],
  ];
  for (const [fn, impl] of entrypoints) {
    const re = new RegExp(`async\\s+function\\s+${fn}\\s*\\(\\.\\.\\.args\\)[\\s\\S]*?loadAdminPanelRuntime\\(\\)[\\s\\S]*?window\\.${impl}\\(\\.\\.\\.args\\)`);
    assert.match(mainSource, re, `${fn} should lazy-delegate to ${impl}`);
  }
});

test('canonical minifier includes the Admin-panel runtime', () => {
  assert.match(minifySource, /static\/js\/admin-panel\.js\.src/);
  assert.match(minifySource, /static\/js\/admin-panel\.js/);
});
