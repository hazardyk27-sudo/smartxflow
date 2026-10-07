#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
stage_path = Path(__file__).with_name('_p2_modal_data_pipeline_stage.py')
stage = stage_path.read_text()
old_guard = "if source.count('loadChartWithTrends(') != 2:\n    raise SystemExit(f'P2.18 unexpected eager loadChartWithTrends refs: {source.count(\"loadChartWithTrends(\")}')"
new_guard = "if source.count('loadChartWithTrends(') != 3:\n    raise SystemExit(f'P2.18 unexpected eager loadChartWithTrends refs: {source.count(\"loadChartWithTrends(\")}')"
if old_guard in stage:
    stage = stage.replace(old_guard, new_guard, 1)
    stage_path.write_text(stage)
elif new_guard not in stage:
    raise SystemExit('P2.18 loadChartWithTrends guard anchor missing')

# On the second invocation the staging script has produced the permanent regression file.
test_path = root / 'tests/test_modal_data_pipeline_split.js'
if test_path.exists():
    test = test_path.read_text()
    title = "test('modal chart-tab switching still reaches lazy chart-history pipeline'"
    if title not in test:
        test += r'''

test('modal chart-tab switching still reaches lazy chart-history pipeline', () => {
  const start = mainSource.indexOf('function setupModalChartTabs(');
  assert.ok(start >= 0);
  const end = mainSource.indexOf('function setupSearch(', start);
  assert.ok(end > start);
  const fn = mainSource.slice(start, end);
  assert.match(fn, /showChartLoading\(\)/);
  assert.match(fn, /loadChartWithTrends\(selectedMatch\.home_team, selectedMatch\.away_team, selectedChartMarket, selectedMatch\.league \|\| ''\)/);
});
'''
        test_path.write_text(test)
        print('P2.18 chart-tab caller regression appended')

print('P2.18 verified call-site compatibility patch applied')
