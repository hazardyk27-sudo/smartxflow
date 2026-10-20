"""Verify lazy admin overlay translations inside /app for seven languages."""
import json
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
LANGS=("tr","en","de","fr","nl","it","es")
def main():
    base={lang:json.loads((ROOT/"static/i18n"/f"{lang}.json").read_text(encoding="utf8")) for lang in LANGS}
    admin=json.loads((ROOT/"static/i18n/admin.json").read_text(encoding="utf8"))
    i18n=(ROOT/"static/js/i18n.js").read_text(encoding="utf8")
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        for size,width,height in (("desktop",1440,900),("phone",390,844)):
            page=browser.new_page(viewport={"width":width,"height":height})
            requests=[]
            errors=[]
            page.on("pageerror",lambda exc:errors.append(str(exc)))
            page.route("https://sxf-preview.test/app",lambda route:route.fulfill(
                status=200,body="<html><body>OK</body></html>"))
            def catalog(route):
                code=Path(urlparse(route.request.url).path).stem
                requests.append(code)
                assert code in LANGS or code=="admin",code
                result=admin if code=="admin" else base[code]
                route.fulfill(status=200,content_type="application/json",
                              body=json.dumps(result,ensure_ascii=False))
            page.route("https://sxf-preview.test/static/i18n/*.json*",catalog)
            page.goto("https://sxf-preview.test/app")
            page.evaluate("localStorage.setItem('sxf_lang','en')")
            page.set_content('''<html><body><section id="adminPanelOverlay">
                <h3 id="sharpHelp">📖 Sharp Alarm Nasil Hesaplanir?</h3>
                <h3 id="licenseTitle">🔑 Yeni Lisans Olustur</h3>
                <h3 id="analystTitle">Yeni Analizci Ekle</h3>
                <p id="amountHelp">Maximum odds in UI</p>
            </section></body></html>''',wait_until="load")
            page.add_script_tag(content=i18n)
            page.wait_for_function("window.SXFI18n && window.SXFI18n.current()==='en'")
            page.wait_for_function("() => document.querySelector('#sharpHelp') !== null")
            assert "admin" not in requests, "Admin catalog must load lazily"
            page.evaluate("() => window.SXFI18n.ensureAdminCatalog()")
            page.wait_for_function("() => document.querySelector('#sharpHelp').getAttribute('data-i18n')==='app.adminui.help_006'")
            assert requests.count("admin")==1,requests
            for lang in LANGS:
                page.evaluate("(lang) => window.SXFI18n.set(lang)",lang)
                page.wait_for_function("(lang) => window.SXFI18n.current()===lang",arg=lang)
                for selector,key in (
                    ("#sharpHelp","help_006"),
                    ("#licenseTitle","management_027"),
                    ("#analystTitle","management_086")
                ):
                    page.wait_for_function("({selector,text}) => document.querySelector(selector).textContent===text",
                        arg={"selector":selector,"text":admin[lang][key]})
                assert page.locator("#amountHelp").inner_text()=="Maximum odds in UI"
            assert requests.count("admin")==1,requests
            assert not errors,errors
            print(f"ADMIN_OVERLAY_OK {size}: 7 locale switches, one catalog fetch")
            page.close()
        browser.close()
if __name__=="__main__":main()
