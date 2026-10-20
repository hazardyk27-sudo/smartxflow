"""Browser acceptance for three JavaScript-built admin tabs inside /app.

Mocks only read endpoints; checks language switching on desktop/mobile without
refetching admin data or overwriting typed configuration.
"""
import json
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
LANGS=("tr","en","de","fr","nl","it","es")
BASE={l:json.loads((ROOT/"static/i18n"/f"{l}.json").read_text(encoding="utf8")) for l in LANGS}
ADMIN=json.loads((ROOT/"static/i18n/admin.json").read_text(encoding="utf8"))
I18N=(ROOT/"static/js/i18n.js").read_text(encoding="utf8")
BUNDLE=(ROOT/"static/js/admin-panel.js").read_text(encoding="utf8")

def main():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        for device,width,height in (("desktop",1440,900),("mobile",390,844)):
            page=browser.new_page(viewport={"width":width,"height":height})
            errors=[]
            page.on("pageerror",lambda e:errors.append(str(e)))
            calls={"api":0,"admin_catalog":0}
            page.route("https://admin-dynamic.test/app",lambda r:r.fulfill(status=200,content_type="text/html",body="<html><body></body></html>"))
            def serve_catalog(route):
                code=Path(urlparse(route.request.url).path).stem
                if code=="admin":calls["admin_catalog"]+=1
                obj=ADMIN if code=="admin" else BASE[code]
                route.fulfill(status=200,content_type="application/json",body=json.dumps(obj,ensure_ascii=False))
            page.route("**/static/i18n/*.json*",serve_catalog)
            def serve_api(route):
                calls["api"]+=1
                route.fulfill(status=200,content_type="application/json",body="{}")
            page.route("**/api/**",serve_api)
            page.goto("https://admin-dynamic.test/app")
            page.set_content("""<html><body>
                <div id="adminPanelOverlay"><div id="adminPanelBody"></div></div>
            </body></html>""",wait_until="load")
            page.evaluate("() => localStorage.setItem('sxf_lang','en')")
            page.add_script_tag(content=I18N)
            page.wait_for_function("() => window.SXFI18n?.current()==='en'")
            page.add_script_tag(content="""window.fetchAlarmsBatch=async()=>{};
                window.getCachedAlarmsByType=()=>[];
                window.showToast=()=>{};
                window.invalidateAlarmCache=()=>{};""")
            page.add_script_tag(content=BUNDLE)
            page.evaluate("() => window.__sxfOpenAdminPanelImpl()")
            page.wait_for_selector("#vlLeaderThreshold")
            assert calls["admin_catalog"]==1,calls
            for tab,input_id,button,key in (
                ("volumeleader","#vlLeaderThreshold",'button[onclick="saveVolumeLeaderConfig()"]',"panel_001"),
                ("dropping","#drMaxOdds1x2",'button[onclick="saveDroppingConfig()"]',"panel_018"),
                ("mim","#mimMinImpact",'button[onclick="saveMimConfig()"]',"panel_037")
            ):
                if tab!="volumeleader":
                    page.evaluate("tab => window.__sxfSwitchAdminTabImpl(tab)",tab)
                    page.wait_for_selector(input_id)
                page.locator(input_id).fill("61")
                api_count=calls["api"]
                for lang in LANGS:
                    page.evaluate("lang => window.SXFI18n.set(lang)",lang)
                    page.wait_for_function("({selector,value}) => document.querySelector(selector)?.textContent===value",
                        arg={"selector":button,"value":ADMIN[lang]["panel_007"]})
                    page.wait_for_function("value => [...document.querySelectorAll('#adminPanelBody h3')].some(el => el.textContent === value)",
                        arg=ADMIN[lang][key])
                    assert page.locator(input_id).input_value()=="61",(device,tab,lang)
                    assert calls["api"]==api_count,(device,tab,lang,calls)
                print("ADMIN_DYNAMIC_I18N_OK",device,tab,"7 languages; typed value preserved")
            assert calls["admin_catalog"]==1,calls
            assert not errors,errors
            page.close()
        browser.close()
if __name__=="__main__": main()
