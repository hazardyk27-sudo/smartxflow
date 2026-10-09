const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'static/js/app.js.src'), 'utf8');
const runtime = fs.readFileSync(path.join(root, 'static/js/app.js'), 'utf8');
const backend = fs.readFileSync(path.join(root, 'services/supabase_client.py'), 'utf8');
const appPy = fs.readFileSync(path.join(root, 'app.py'), 'utf8');

function between(text, start, end) {
  const a = text.indexOf(start);
  const b = text.indexOf(end, a + start.length);
  assert.ok(a >= 0, `missing start marker: ${start}`);
  assert.ok(b > a, `missing end marker: ${end}`);
  return text.slice(a, b);
}

test('initial match load requests a real first page instead of blocking on bulk', () => {
  const loader = between(source, 'async function loadMatches(', 'async function loadAllRemainingMatches()');
  assert.match(loader, /limit=\$\{matchesDisplayCount\}&offset=0/);
  assert.doesNotMatch(loader, /bulk=1/);
  assert.match(loader, /result\.has_more/);
  assert.match(loader, /loadAllRemainingMatches\(\)/);
});

test('background hydration keeps today_future/source semantics and uses larger pages', () => {
  const bg = between(source, 'async function loadAllRemainingMatches()', 'function updateTableHeaders()');
  assert.match(bg, /const pageSize = 200/);
  assert.match(bg, /date_filter=today_future/);
  assert.match(bg, /source=/);
  assert.match(bg, /_matchesMarketCache\[cacheKey\]/);
});

test('served runtime contains the same first-page path', () => {
  const loader = between(runtime, 'async function loadMatches(', 'async function loadAllRemainingMatches()');
  assert.match(loader, /limit=\$\{matchesDisplayCount\}&offset=0/);
  assert.doesNotMatch(loader, /bulk=1/);
  assert.match(loader, /result\.has_more/);
});

test('database pagination is real and page-scoped', () => {
  const fn = between(backend, '    def get_matches_paginated(', '    def _get_empty_odds(');
  assert.match(fn, /page_limit/);
  assert.match(fn, /page_offset/);
  assert.match(fn, /Prefer.*count=exact/);
  assert.match(fn, /offset=\{page_offset\}/);
  assert.match(fn, /limit=\{page_limit\}/);
  assert.match(fn, /fixtures_page/);
  assert.match(fn, /_fetch_page_odds/);
  assert.doesNotMatch(fn, /_fetch_main_table_odds\(market, date_gte=date_gte\)/);
});

test('today_future route uses the fast paginated database path', () => {
  const route = between(appPy, "@app.route('/api/matches')", "@app.route('/api/match/history/bulk')");
  assert.match(route, /date_filter in \(None, 'today_future'\)/);
  assert.match(route, /today_only=\(date_filter == 'today_future'\)/);
});
