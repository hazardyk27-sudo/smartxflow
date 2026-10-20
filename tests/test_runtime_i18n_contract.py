"""Every literal first-party runtime translation reference exists in seven locales."""
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CODES=("tr","en","de","fr","nl","it","es")
RUNTIMES=(
  "static/js/app.js","static/js/inline.js","static/js/live-tab.js",
  "static/js/alarm-sidebar.js","static/js/modal-alarms.js",
  "static/js/modal-chart.js","static/js/modal-info.js",
  "static/js/modal-live.js","static/js/modal-entry.js",
  "static/js/mobile-chart-panel.js","static/js/chart-export.js",
  "static/js/admin-panel.js","static/js/base-signals.js",
)
REF=re.compile(r"""(?:_t|SXFI18n\.t)\(\s*['"]((?:app|ui)\.[a-zA-Z0-9_.]+)['"]""")
ATTR=re.compile(r"""\bdata-i18n(?:-attr|-html)?=["']([^"']+)["']""")

def resolve(data,path):
  node=data
  for part in path.split("."):
    if not isinstance(node,dict):return None
    node=node.get(part)
  return node

def test_runtime_translation_keys_complete():
  keys=set()
  for path in RUNTIMES:
    source=(ROOT/path).read_text(encoding="utf8")
    keys.update(REF.findall(source))
  html=(ROOT/"templates/index.html").read_text(encoding="utf8")
  for attr in ATTR.findall(html):
    for token in attr.split(";"):
      key=token.split(":",1)[-1].strip()
      if key.startswith(("app.","ui.")):keys.add(key)
  # Short calendar labels in app.js concatenate app.j.ms + month number.
  keys.discard("app.j.ms")  # dynamic prefix, not itself a dictionary leaf
  keys.update(f"app.j.ms{x}" for x in range(12))
  assert len(keys)>170, "i18n scan unexpectedly bypassed"
  for code in CODES:
    data=json.loads((ROOT/f"static/i18n/{code}.json").read_text(encoding="utf8"))
    missing=sorted(k for k in keys if not isinstance(resolve(data,k),str) or not resolve(data,k).strip())
    assert not missing, f"{code}: missing {len(missing)} runtime references: {missing}"
