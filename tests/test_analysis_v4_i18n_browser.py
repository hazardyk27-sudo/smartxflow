"""Real Playwright i18n regression: seven languages, mobile and desktop."""
from __future__ import annotations
import json
from datetime import datetime,time,timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright
from test_analysis_v4_browser import ROOT, fixture

LANGS=("tr","en","de","fr","nl","it","es")

def main():
    locales={
        code:json.loads((ROOT/"static/i18n"/f"{code}.json").read_text(encoding="utf8"))
        for code in LANGS
    }
    html=(ROOT/"templates/index.html").read_text(encoding="utf8")
    a=html.index('<div id="sxfBaseSignalOverlay"')
    b=html.index("<!-- Trendler Modal -->",a)
    modal=html[a:b]
    style=(ROOT/"static/css/style.css").read_text(encoding="utf8")
    css=(ROOT/"static/css/base-signals.css").read_text(encoding="utf8")
    i18n=(ROOT/"static/js/i18n.js").read_text(encoding="utf8")
    ui=(ROOT/"static/js/base-signals.js").read_text(encoding="utf8")
    content="<!doctype html><html lang='en'><head><meta name='viewport' content='width=device-width,initial-scale=1'><style>"+style+"</style><style>"+css+"</style></head><body>"+modal+"</body></html>"
    now=datetime.now(ZoneInfo("Europe/Istanbul")).date()
    kickoff=datetime.combine(now,time(18,0),ZoneInfo("Europe/Istanbul")).astimezone(timezone.utc).isoformat()
    a=fixture(now.isoformat(),kickoff,"1X2_CONCENTRATION_V1","Team V1","uid-v1")
    b=fixture(now.isoformat(),kickoff,"1X2_CONCENTRATION_V2","Team V2","uid-v2")
    a.update({"final_score":"1-1","result_state":"FT","outcome":"LOSS"})
    b.update({"final_score":"1-1","result_state":"FT","outcome":"LOSS"})
    legacy=fixture(now.isoformat(),kickoff,"LEGACY_EARLY_MONEY_LOCK","Legacy Team","uid-legacy")
    legacy.update({"id":10000000022,"kind":"LEGACY_SIGNAL","stage_status":"LEGACY_RECORDED",
                   "checkpoint":None,"source_checkpoint":None,"odds":None,
                   "observed_at":None,"shadow":False,"result_state":"PENDING",
                   "final_score":None,"outcome":None})
    payload={"status":"ok","phase":"BASE_SHADOW_AND_LEGACY_HISTORY",
             "engines":["1X2_CONCENTRATION_V1","1X2_CONCENTRATION_V2","LEGACY_EARLY_MONEY_LOCK"],
             "items":[a,b,legacy],"results_source_state":"ok"}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        for viewport,width,height in (("desktop",1440,900),("phone",390,844)):
            # Each viewport begins with the fully available source state;
            # the outage scenario mutates this payload only within that run.
            payload["legacy_source_status"]="ok"
            payload["phase"]="BASE_SHADOW_AND_LEGACY_HISTORY"
            payload["items"]=[a,b,legacy]
            page=browser.new_page(viewport={"width":width,"height":height})
            errors=[]
            page.on("pageerror",lambda e:errors.append(str(e)))
            feed_calls=[]
            page.route("https://sxf-preview.test/",lambda route:route.fulfill(status=200,body="<html></html>"))
            def feed_handler(route):
                feed_calls.append(route.request.url)
                route.fulfill(status=200,json=payload)
            page.route("**/api/base-signals/feed*",feed_handler)
            def locale_handler(route):
                code=Path(urlparse(route.request.url).path).stem
                assert code in locales,code
                route.fulfill(status=200,content_type="application/json",
                              body=json.dumps(locales[code],ensure_ascii=False))
            page.route("**/static/i18n/*.json*",locale_handler)
            page.goto("https://sxf-preview.test/",wait_until="load")
            page.set_content(content,wait_until="load")
            page.add_script_tag(content=i18n)
            page.wait_for_function("window.SXFI18n && window.SXFI18n.current()==='en' && document.querySelector('#sxfBaseSignalTitle').textContent==='Analyses'")
            page.add_script_tag(content=ui)
            page.evaluate("window.openBaseSignalsPanel()")
            page.locator('[data-motor="1X2_CONCENTRATION_V1"]').wait_for()
            page.locator('[data-motor="1X2_CONCENTRATION_V1"]').click()
            assert len(feed_calls)==1
            for code in LANGS:
                page.evaluate("async (lang) => await window.SXFI18n.set(lang)",code)
                lex=locales[code]["app"]["v4"]
                assert page.locator("#sxfBaseSignalTitle").inner_text()==lex["title"],(viewport,code)
                details=page.locator("#sxfSignalContent").inner_text()
                assert "Team V1" in details and "Team V2" not in details,(viewport,code,details)
                assert lex["home_wins"].replace("{team}","Team V1") in details,(viewport,code,details)
                assert lex["market_1x2"] in details,(viewport,code,details)
                assert lex["final_score_label"] in details,(viewport,code,details)
                assert lex["lost"] in details,(viewport,code,details)
                assert lex["back_engines"] in details,(viewport,code,details)
                assert lex["odds"] in details,(viewport,code,details)
                assert lex["mixed_notice"] in page.locator("#sxfSignalNotice").inner_text()
                page.locator("#sxfSignalBack").click()
                page.locator('[data-motor="LEGACY_EARLY_MONEY_LOCK"]').click()
                legacy_details=page.locator("#sxfSignalContent").inner_text()
                assert "Legacy Team" in legacy_details and "Team V1" not in legacy_details
                assert lex["legacy_recorded"] in legacy_details,(viewport,code,legacy_details)
                assert lex["legacy_warning"] in legacy_details,(viewport,code,legacy_details)
                assert lex["odds_missing"] in legacy_details,(viewport,code,legacy_details)
                assert lex["score_unverified"] in legacy_details,(viewport,code,legacy_details)
                page.locator("#sxfSignalBack").click()
                page.locator('[data-motor="1X2_CONCENTRATION_V1"]').click()
                assert page.locator("#sxfSignalSearch").get_attribute("placeholder")==lex["search_placeholder"]
                assert page.locator("#sxfSignalRefresh").get_attribute("aria-label")==lex["refresh"]
                assert page.locator(".sxf-signal-date-rail").locator(".sxf-day-now").inner_text()==lex["today"]
                assert page.locator(".sxf-day.is-active").get_attribute("aria-label").endswith(lex["day_count"].replace("{date}",now.isoformat()).replace("{count}","1"))
                assert len(feed_calls)==1,"language change must not refetch source"
                overflow=page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                assert overflow<=1,(viewport,code,overflow)
                target=Path("artifacts")
                target.mkdir(exist_ok=True)
                page.screenshot(path=str(target/f"analizler-v4-i18n-{code}-{viewport}.png"))
                print(f"I18N_BROWSER_OK {viewport} {code} no-overflow stable-engine no-refetch")
            # Source outage: genuine Base picks stay visible, legacy count is
            # not falsely shown as zero in any of the seven languages.
            payload["legacy_source_status"]="unavailable"
            payload["phase"]="BASE_SHADOW_LEGACY_UNAVAILABLE"
            payload["items"]=[a,b]
            page.locator("#sxfSignalRefresh").click()
            page.wait_for_function(
                "(text) => document.querySelector('#sxfSignalNotice').textContent === text",
                arg=locales[LANGS[-1]]["app"]["v4"]["legacy_unavailable_notice"])
            page.locator("#sxfSignalBack").click()
            page.locator(".sxf-legacy-source-alert").wait_for()
            for code in LANGS:
                await_locale=page.evaluate("async lang => await window.SXFI18n.set(lang)",code)
                lex=locales[code]["app"]["v4"]
                assert lex["legacy_unavailable_desc"] in page.locator("#sxfSignalContent").inner_text()
                assert lex["legacy_unavailable_notice"] in page.locator("#sxfSignalNotice").inner_text()
                page.locator('[data-motor="LEGACY_EARLY_MONEY_LOCK"]').click()
                assert lex["legacy_unavailable_title"] in page.locator("#sxfSignalContent").inner_text()
                page.locator("#sxfSignalBack").click()
            assert not errors,errors
            page.close()
        browser.close()

if __name__=="__main__":
    main()
