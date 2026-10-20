"""Contract for all localized dynamic /status text, including every supported locale."""
import json
from pathlib import Path
from html.parser import HTMLParser
ROOT = Path(__file__).resolve().parents[1]
LANGS = ("tr","en","de","fr","nl","it","es")
REQUIRED = ("page_title","app_link","scraper_heading","checking","last_scrape","last_heartbeat",
            "time_istanbul","success","processed","no_processed","active","delayed","offline",
            "connection_error","idle","calculating","started","error","ssl_error","stopped",
            "no_data","just_now")
class KeyReader(HTMLParser):
    def __init__(self):
        super().__init__(); self.keys=set()
    def handle_starttag(self, tag, attrs):
        key=dict(attrs).get("data-i18n")
        if key: self.keys.add(key)
def test_status_locale_contract():
    src=(ROOT/"templates/status.html").read_text(encoding="utf-8")
    reader=KeyReader(); reader.feed(src)
    for l in LANGS:
        data=json.loads((ROOT/"static/i18n"/f"{l}.json").read_text(encoding="utf-8"))
        assert all(isinstance(data["status"].get(k),str) and data["status"][k].strip() for k in REQUIRED),(l,"missing status keys")
        assert "{minutes}" in data["status"]["delayed"],l
        assert reader.keys.issuperset({"status.page_title","status.scraper_heading","status.time_istanbul"})
    assert "Intl.RelativeTimeFormat" in src
    assert "Europe/Istanbul" in src
    assert "window.addEventListener('i18n:change'" in src
    assert "renderScraperStatus();" in src and "renderEngineStatus();" in src
    assert "lastScraperPayload = await res.json()" in src
    assert "lastEnginePayload = await res.json()" in src

if __name__ == '__main__':
    test_status_locale_contract()
    print('STATUS_LOCALE_CONTRACT_OK')
