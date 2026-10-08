const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..');
const i18n = fs.readFileSync(path.join(root, 'static/js/i18n.js'), 'utf8');

function between(text, startMarker, endMarker) {
  const start = text.indexOf(startMarker);
  const end = text.indexOf(endMarker, start + startMarker.length);
  assert.ok(start >= 0, `missing ${startMarker}`);
  assert.ok(end > start, `missing ${endMarker}`);
  return text.slice(start, end);
}

test('interaction warmup waits for rendered matches and idle time', () => {
  const schedule = between(i18n, 'function scheduleInteractionWarmup()', 'var init = detectLang();');
  assert.match(schedule, /\.fav-heart\[data-matchkey\]/);
  assert.match(schedule, /MutationObserver/);
  assert.match(schedule, /requestIdleCallback/);
  assert.match(schedule, /timeout:\s*1500/);
  assert.match(schedule, /setTimeout\(armWarmup,\s*6000\)/);
});

test('warmup prepares first-click runtimes without adding eager script tags', () => {
  const warmup = between(i18n, 'function runInteractionWarmup()', 'function scheduleInteractionWarmup()');
  for (const helper of [
    '_getModalEntryRuntimeUrl',
    '_getModalInfoRuntimeUrl',
    '_getLiveTabRuntimeUrl',
    '_getAdminPanelRuntimeUrl',
    '_getMobileChartPanelRuntimeUrl'
  ]) {
    assert.match(warmup, new RegExp(helper));
  }
  assert.match(warmup, /loadSxfAnalysisUi/);
  assert.match(warmup, /loadChartLibs/);
  assert.doesNotMatch(warmup, /createElement\(['"]script['"]\)/,
    'local split runtimes should be prefetched, not eagerly executed by script injection');
});

test('jsdelivr connection is warmed before deferred chart download', () => {
  assert.match(i18n, /addInteractionPreconnect\('https:\/\/cdn\.jsdelivr\.net'\)/);
  assert.match(i18n, /link\.rel\s*=\s*'preconnect'/);
});
