#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
for rel in ('static/js/app.js.src', 'static/js/app.js'):
    path = root / rel
    text = path.read_text()
    old = 'if (isMobile()) await loadMobileChartPanelRuntime();'
    new = "if (typeof isMobile === 'function' && isMobile()) await loadMobileChartPanelRuntime();"
    if text.count(old) != 1:
        raise SystemExit(f'{rel}: expected exactly one mobile panel await, found {text.count(old)}')
    path.write_text(text.replace(old, new, 1))

test_path = root / 'tests/test_mobile_chart_panel_split.js'
test = test_path.read_text()
old_src = r"/await loadModalChartRuntime\\(\\);\\s*if \\(isMobile\\(\\)\\) await loadMobileChartPanelRuntime\\(\\);\\s*return window\\.__sxfLoadChartImpl/"
new_src = r"/await loadModalChartRuntime\\(\\);\\s*if \\(typeof isMobile === 'function' && isMobile\\(\\)\\) await loadMobileChartPanelRuntime\\(\\);\\s*return window\\.__sxfLoadChartImpl/"
if old_src not in test:
    raise SystemExit('mobile panel test regex anchor missing')
test_path.write_text(test.replace(old_src, new_src))
print('P2.16 compatibility guard applied')
