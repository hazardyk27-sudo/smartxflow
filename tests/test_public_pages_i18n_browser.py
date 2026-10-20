"""Browser localization coverage for public pages, status and app shell.

Jinja templates rendered as static DOM; no production endpoints are accessed.
"""
import json,re
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
LANGS=("tr","en","de","fr","nl","it","es")
CASES=(
    ("landing","/","nav.features"),
    ("pricing","/pricing","pricing.header.title"),
    ("rehber","/rehber","rehber.hero_title"),
    ("rehber_oran_analizi","/rehber/oran-analizi","rehber_oran.s2t"),
    ("rehber_para_hareketi","/rehber/para-hareketi","rehber_para.s1t"),
    ("rehber_canli_oran_takibi","/rehber/canli-oran-takibi","rehber_canli.s1t"),
    ("nedir","/nedir","nedir.adv_title"),
    ("legal","/legal","nav.features"),
    ("status","/status","status.nav"),
    ("analysis","/analysis","app.an.page_title"),
    ("index","/app","app.hdr.logout"),
    ("match_detail","/match/a","app.md.subtitle"),
)
def original_html(name):
    raw=(ROOT/"templates"/(name+".html")).read_text(encoding="utf8")
    return re.sub(r"<script\b[^>]*>[\s\S]*?<\/script\s*>","",raw,flags=re.I)

def main():
    catalogs={l:json.loads((ROOT/"static/i18n"/(l+".json")).read_text(encoding="utf8")) for l in LANGS}
    runtime=(ROOT/"static/js/i18n.js").read_text(encoding="utf8")
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        for kind,width,height in (("desktop",1280,900),("mobile",390,844)):
            for name,route,key in CASES:
                page=browser.new_page(viewport={"width":width,"height":height})
                errors=[]
                page.on("pageerror",lambda e:errors.append(str(e)))
                page.route("https://preview-sxf.test"+route,lambda r:r.fulfill(
                    status=200,content_type="text/html",body="<html><body></body></html>"))
                def source_response(r):
                    lang=Path(urlparse(r.request.url).path).stem
                    r.fulfill(status=200,content_type="application/json",body=json.dumps(catalogs[lang],ensure_ascii=False))
                page.route("https://preview-sxf.test/static/i18n/*.json*",source_response)
                page.goto("https://preview-sxf.test"+route)
                page.evaluate("localStorage.setItem('sxf_lang','en')")
                page.set_content(original_html(name),wait_until="load")
                page.add_script_tag(content=runtime)
                page.wait_for_function("() => !!window.SXFI18n")
                for lang in LANGS:
                    page.evaluate("lang => window.SXFI18n.set(lang)",lang)
                    value=key.split(".")
                    result=catalogs[lang]
                    for part in value:result=result[part]
                    page.wait_for_function("({key,value})=>[...document.querySelectorAll('[data-i18n]')].some(el=>el.getAttribute('data-i18n')===key && el.textContent===value)",
                        arg={"key":key,"value":result})
                    assert page.evaluate("document.documentElement.lang")==lang,(name,lang)
                print(f"PUBLIC_PAGE_OK {name} {kind} 7 languages")
                # Browser's default styles are intentionally omitted for Jinja DOM
                # contract testing; responsive layout is separately smoke-tested.
                assert not errors,(name,kind,errors)
                page.close()
        browser.close()
if __name__=="__main__":main()
