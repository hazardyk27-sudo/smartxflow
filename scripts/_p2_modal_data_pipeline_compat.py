#!/usr/bin/env python3
from pathlib import Path

path = Path(__file__).with_name('_p2_modal_data_pipeline_stage.py')
text = path.read_text()
old_guard = "if source.count('loadChartWithTrends(') != 2:\n    raise SystemExit(f'P2.18 unexpected eager loadChartWithTrends refs: {source.count(\"loadChartWithTrends(\")}')"
new_guard = "if source.count('loadChartWithTrends(') != 3:\n    raise SystemExit(f'P2.18 unexpected eager loadChartWithTrends refs: {source.count(\"loadChartWithTrends(\")}')"
if text.count(old_guard) != 1:
    raise SystemExit('P2.18 loadChartWithTrends guard anchor missing')
text = text.replace(old_guard, new_guard, 1)

anchor = r'''test('mobile chart history still reaches lazy chart-history pipeline', () => {
  const start = mainSource.indexOf('async function loadChartHistory(');
  assert.ok(start >= 0);
  const end = mainSource.indexOf('\\n}', start);
  const fn = mainSource.slice(start, end + 2);
  assert.match(fn, /await loadChartWithTrends\\(/);
});'''
addition = anchor + r'''


test('modal chart-tab switching still reaches lazy chart-history pipeline', () => {
  const start = mainSource.indexOf('function setupModalChartTabs(');
  assert.ok(start >= 0);
  const end = mainSource.indexOf('function setupSearch(', start);
  assert.ok(end > start);
  const fn = mainSource.slice(start, end);
  assert.match(fn, /showChartLoading\\(\\)/);
  assert.match(fn, /loadChartWithTrends\\(selectedMatch\\.home_team, selectedMatch\\.away_team, selectedChartMarket, selectedMatch\\.league \\|\\| ''\\)/);
});'''
if text.count(anchor) != 1:
    raise SystemExit('P2.18 generated test anchor missing')
text = text.replace(anchor, addition, 1)
path.write_text(text)
print('P2.18 verified call-site compatibility patch applied')
