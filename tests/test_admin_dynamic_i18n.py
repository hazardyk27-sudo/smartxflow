"""Fail-closed translation coverage for JS-generated admin overlay controls."""
import json
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
LANGS=("tr","en","de","fr","nl","it","es")
def main():
    catalog=json.loads((ROOT/"static/i18n/admin.json").read_text(encoding="utf8"))
    assert all(set(catalog[lang])==set(catalog["tr"]) for lang in LANGS)
    assert all(catalog[lang][key].strip() for lang in LANGS for key in ("panel_dyn_alarms","panel_dyn_more","panel_dyn_no_mim"))
    for name in ("admin-panel.js","admin-panel.js.src"):
        data=(ROOT/"static/js"/name).read_text(encoding="utf8")
        keys=re.findall(r'data-i18n="app\.adminui\.([a-zA-Z0-9_]+)"',data)
        assert len(keys)>=30,(name,len(keys))
        assert all(key in catalog["tr"] for key in keys)
        assert data.count("await window.SXFI18n.ensureAdminCatalog()")==3
        assert data.count("window.SXFI18n.apply()")>=3
        assert "panel_dyn_more" in data and "panel_dyn_alarms" in data
    print("ADMIN_DYNAMIC_CONTRACT_OK 7 languages")
if __name__=="__main__": main()
