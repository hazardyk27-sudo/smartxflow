"""Legacy analyst page: outcome and date localization contract."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
LANGS=("tr","en","de","fr","nl","it","es")

def test_legacy_analyst_results_use_current_language_and_tr_match_time():
    src=(ROOT/"templates/analysis.html").read_text(encoding="utf-8")
    assert "function analysisLocale()" in src
    assert "window.SXFI18n.current" in src
    assert "function analysisT(key, fallback)" in src
    assert "timeZone:'Europe/Istanbul'" in src
    assert "new Intl.DateTimeFormat(analysisLocale()" in src
    assert "analysisT(pair[0],pair[1])" in src
    assert "analysisT('awaiting','Beklemede')" in src
    for code in LANGS:
        dicts=json.loads((ROOT/"static/i18n"/f"{code}.json").read_text(encoding="utf-8"))
        for key in ("result_won","result_lost","result_push","result_void","awaiting"):
            assert isinstance(dicts["app"]["j"][key],str)
            assert dicts["app"]["j"][key].strip()
