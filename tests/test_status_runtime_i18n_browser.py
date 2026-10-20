"""Browser acceptance: cached status and engine timestamps update in seven languages, no new API requests."""
import json
import re
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
LANGS=("tr","en","de","fr","nl","it","es")
RAW=(ROOT/"templates/status.html").read_text(encoding="utf8")
I18N=(ROOT/"static/js/i18n.js").read_text(encoding="utf8")
SCRIPT=re.findall(r"<script(?:\s[^>]*)?>([\s\S]*?)</script>",RAW,flags=re.I)[-1]
HTML=re.sub(r"<script\b[^>]*>[\s\S]*?</script>","",RAW,flags=re.I)
NOW="2026-10-20T09:00:00Z"
SCRAPER={"heartbeat":{"status":"active","last_heartbeat":NOW},"signals":[{"created_at":NOW,"match_count":3,"snapshot_count":14}],"active_match_count":3}
ENGINE={"heartbeat":{"status":"idle","last_heartbeat":NOW},"processed_signals":[{"created_at":NOW,"processed_at":NOW,"match_count":2}],"stats":{"total_active_alarms":4,"pending_count":1,"active_match_count":3},"alarm_counts":{"sharp":2}}

def main():
    cats={l:json.loads((ROOT/"static/i18n"/f"{l}.json").read_text(encoding="utf8")) for l in LANGS}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        for width,height in ((1440,900),(390,844)):
            page=browser.new_page(viewport={"width":width,"height":height})
            page.route("https://status-i18n.test/status",lambda r:r.fulfill(status=200,content_type="text/html",body="<html><body></body></html>"))
            calls={"scraper":0,"engine":0}
            def endpoint(route):
                key="scraper" if "scraper-status" in route.request.url else "engine"
                calls[key]+=1
                route.fulfill(status=200,content_type="application/json",body=json.dumps(SCRAPER if key=="scraper" else ENGINE))
            page.route("**/api/scraper-status",endpoint)
            page.route("**/api/alarm-engine-status",endpoint)
            def catalog(route):
                lang=Path(urlparse(route.request.url).path).stem
                route.fulfill(status=200,content_type="application/json",body=json.dumps(cats[lang],ensure_ascii=False))
            page.route("**/static/i18n/*.json*",catalog)
            page.goto("https://status-i18n.test/status")
            page.set_content(HTML,wait_until="load")
            page.evaluate("() => localStorage.setItem('sxf_lang','tr')")
            page.add_script_tag(content=I18N)
            page.add_script_tag(content=SCRIPT)
            page.wait_for_function("() => document.querySelector('#engineHistoryBody .badge-success')")
            for lang in LANGS:
                page.evaluate("lang => window.SXFI18n.set(lang)",lang)
                for element,key in (("#engineHistoryBody .badge-success","processed"),("#historyBody .badge-success","success"),("#engineState","idle"),("#mainStatusText","active")):
                    page.wait_for_function("({selector,text}) => document.querySelector(selector)?.textContent===text",
                      arg={"selector":element,"text":cats[lang]["status"][key]})
                assert page.locator("#engineLastBeat").inner_text() != "-"
                assert page.locator("#lastScrape").inner_text() != "-"
                assert page.locator("html").get_attribute("lang")==lang
                assert calls=={"scraper":1,"engine":1},(lang,calls)
            print("STATUS_RUNTIME_I18N_OK",width,height,"7 locales; no extra service fetches")
            page.close()
        browser.close()
if __name__=="__main__": main()
