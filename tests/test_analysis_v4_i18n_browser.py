"""Playwright smoke: compact V5 multi-engine cards in seven languages, desktop and phone."""
from __future__ import annotations
import json
from datetime import datetime,time,timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright
from test_analysis_v4_browser import ROOT,fixture

LANGS=("tr","en","de","fr","nl","it","es")

def main():
    locales={c:json.loads((ROOT/"static/i18n"/f"{c}.json").read_text(encoding="utf8")) for c in LANGS}
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
    base=fixture(now.isoformat(),kickoff,"1X2_CONCENTRATION_V1","Team V1","uid-v1")
    base.update({"id":11,"valid_on_time":True,"final_score":"1-1","result_state":"FT","outcome":"LOSS"})
    v2=dict(base,engine="1X2_CONCENTRATION_V2",id=12)
    heavy=dict(base,engine="HEAVY_1X2_CONCENTRATION",id=13)
    early=dict(base,engine="EARLY_MONEY_CORE",id=14,checkpoint=72,valid_on_time=False)
    excluded=fixture(now.isoformat(),kickoff,"1X2_CONCENTRATION_V2","Team V2","uid-other")
    payload={"status":"ok","phase":"SHADOW","results_source_state":"ok","ruleset_mode":"CURRENT",
             "items":[base,v2,heavy,early,excluded]}
    with sync_playwright() as browser_api:
        browser=browser_api.chromium.launch(headless=True)
        for viewport,width,height in (("desktop",1440,900),("phone",390,844)):
            page=browser.new_page(viewport={"width":width,"height":height})
            errors=[]
            page.on("pageerror",lambda e:errors.append(str(e)))
            calls=[]
            page.route("https://sxf-preview.test/",lambda route:route.fulfill(status=200,body="<html></html>"))
            def respond(route):
                calls.append(route.request.url)
                route.fulfill(status=200,json=payload)
            page.route("**/api/base-signals/feed*",respond)
            def localized(route):
                code=Path(urlparse(route.request.url).path).stem
                assert code in locales
                route.fulfill(status=200,content_type="application/json",
                              body=json.dumps(locales[code],ensure_ascii=False))
            page.route("**/static/i18n/*.json*",localized)
            page.goto("https://sxf-preview.test/",wait_until="load")
            page.set_content(content,wait_until="load")
            page.add_script_tag(content=i18n)
            page.wait_for_function("window.SXFI18n && window.SXFI18n.current()==='en'")
            page.add_script_tag(content=ui)
            page.evaluate("window.openBaseSignalsPanel()")
            page.locator('[data-motor="1X2_CONCENTRATION_V1"]').wait_for()
            page.locator('[data-motor="1X2_CONCENTRATION_V1"]').click()
            assert len(calls)==1
            for lang in LANGS:
                page.evaluate("async c => await window.SXFI18n.set(c)",lang)
                lex=locales[lang]["app"]["v4"]
                assert page.locator("#sxfBaseSignalTitle").inner_text()==lex["title"],(viewport,lang)
                body=page.locator("#sxfSignalContent").inner_text()
                assert "Team V1" in body and "Team V2" not in body,(viewport,lang,body)
                assert lex["home_wins"].replace("{team}","Team V1") in body,(viewport,lang)
                assert lex["market_1x2"] in body,(viewport,lang)
                assert lex["odds"] in body,(viewport,lang)
                assert lex["status_mixed"] in body,(viewport,lang)
                assert page.locator(".sxf-list-result").first.get_attribute("title")==lex["final_score_label"],(viewport,lang)
                assert lex["back_engines"] in body,(viewport,lang)
                assert page.locator(".sxf-fixture-line").count()==1
                for key in ("list_col_time","list_col_match","list_col_pick","list_col_engines","list_col_status"):
                    assert lex[key] in page.locator(".sxf-fixture-list-head").text_content(),(viewport,lang,key)
                assert page.locator(".sxf-list-history-group").count()==1
                assert page.locator(".sxf-line-engines .sxf-direction-badge").all_inner_texts()==["V1","V2","HEAVY","EARLY CORE"]
                assert page.locator(".sxf-fixture-line").first.get_attribute("open") is None
                page.locator(".sxf-fixture-line summary").first.click()
                assert lex["history_count"].replace("{count}","4") in page.locator(".sxf-fixture-expanded").first.inner_text(),(viewport,lang)
                assert lex["lost"] in page.locator(".sxf-history-list").inner_text(),(viewport,lang)
                page.locator(".sxf-fixture-line summary").first.click()
                assert page.locator("#sxfSignalSearch").get_attribute("placeholder")==lex["search_placeholder"]
                assert page.locator("#sxfSignalRefresh").get_attribute("aria-label")==lex["refresh"]
                assert page.locator(".sxf-day.is-active").get_attribute("aria-label").endswith(
                    lex["day_count"].replace("{date}",now.isoformat()).replace("{count}","1"))
                assert len(calls)==1,"locale switch must never re-query backend"
                overflow=page.evaluate("document.documentElement.scrollWidth-window.innerWidth")
                assert overflow<=1,(viewport,lang,overflow)
                Path("artifacts").mkdir(exist_ok=True)
                page.screenshot(path=f"artifacts/analizler-v5-{lang}-{viewport}.png")
                print(f"V5_I18N_OK {viewport} {lang} same-side grouped / no overflow")
            # A results-service outage does not rewrite stored picks or fake final scores.
            payload["results_source_state"]="unavailable"
            page.locator("#sxfSignalRefresh").click()
            page.wait_for_function(
                "(msg)=>document.querySelector('#sxfSignalNotice').textContent===msg",
                arg=locales[LANGS[-1]]["app"]["v4"]["score_source_error"])
            assert "Team V1" in page.locator("#sxfSignalContent").inner_text()
            assert not errors,errors
            payload["results_source_state"]="ok"
            page.close()
        browser.close()

if __name__=="__main__":
    main()
