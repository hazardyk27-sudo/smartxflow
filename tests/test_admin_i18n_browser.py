"""Admin-localization smoke: protected UI text only; no backend access."""
import json,re
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
CODES=("tr","en","de","fr","nl","it","es")
def main():
    admin=json.loads((ROOT/"static/i18n/admin.json").read_text(encoding="utf8"))
    locales={lang:json.loads((ROOT/"static/i18n"/(lang+".json")).read_text(encoding="utf8")) for lang in CODES}
    assert all(set(admin[x])==set(admin["tr"]) for x in CODES)
    html=(ROOT/"templates/admin.html").read_text(encoding="utf8")
    html=re.sub(r"<script\b[^>]*>[\s\S]*?<\/script\s*>","",html,flags=re.I)
    script=(ROOT/"static/js/i18n.js").read_text(encoding="utf8")
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        for mode,width,height in (("desktop",1440,900),("mobile",390,844)):
            page=browser.new_page(viewport={"width":width,"height":height})
            errors=[]
            page.on("pageerror",lambda err:errors.append(str(err)))
            page.route("https://sxf-preview.test/admin",lambda r:r.fulfill(
                status=200,content_type="text/html",body="<html><body></body></html>"))
            def source(r):
                name=Path(urlparse(r.request.url).path).stem
                data=admin if name=="admin" else locales[name]
                r.fulfill(status=200,content_type="application/json",body=json.dumps(data,ensure_ascii=False))
            page.route("https://sxf-preview.test/static/i18n/*.json*",source)
            page.goto("https://sxf-preview.test/admin")
            page.evaluate("localStorage.setItem('sxf_lang','en')")
            page.set_content(html,wait_until="load")
            page.add_script_tag(content=script)
            page.wait_for_function("() => !!document.getElementById('sxfStandaloneLanguage')",timeout=15000)
            page.wait_for_function("() => document.querySelectorAll('[data-i18n^=\"app.adminui.\"]').length>25",timeout=15000)
            for lang in CODES:
                page.locator("#sxfStandaloneLanguage").select_option(lang)
                page.wait_for_function("lang => window.SXFI18n.current()===lang",arg=lang)
                key="app.adminui.sales"
                expected=admin[lang]["sales"]
                page.wait_for_function("({key,value}) => [...document.querySelectorAll('[data-i18n]')].some(e=>e.getAttribute('data-i18n')===key && e.textContent.trim()===value)",arg={"key":key,"value":expected})
                assert page.evaluate("document.documentElement.lang")==lang
            assert not errors,errors
            if mode=="desktop":
                Path("artifacts").mkdir(exist_ok=True)
                page.screenshot(path="artifacts/i18n-admin-desktop.png",full_page=False)
            print(f"ADMIN_I18N_OK {mode}: 7 languages, dedicated admin control")
            page.close()
        browser.close()
if __name__=="__main__":main()
