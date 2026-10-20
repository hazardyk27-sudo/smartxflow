"""Full-site i18n regression: standalone auth/status, seven locales and desktop/mobile.

No production network requests, no credentials, and no server mutations.
"""
from __future__ import annotations

import json, re
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
CODES=("tr","en","de","fr","nl","it","es")
ROUTES=(
    ("login","/login","welcome"),
    ("signup","/signup","new_account"),
    ("forgot_password","/forgot-password","reset_your"),
    ("reset_password","/reset-password","set_password"),
    ("verify_email","/verify-email","resend_verification"),
    ("auth_callback","/auth-callback","verifying"),
    ("membership_required","/membership-required","contact_support"),
    ("migrate_account","/migrate-account","migrate_header"),
    ("account","/account","my_account"),
    ("admin_login","/admin-login","admin_login_header"),
)
def clean_template(file):
    html=(ROOT/"templates"/(file+".html")).read_text(encoding="utf8")
    return re.sub(r"<script\b[^>]*>[\s\S]*?<\/script\s*>","",html,flags=re.I)

def main():
    locales={code:json.loads((ROOT/"static/i18n"/(code+".json")).read_text(encoding="utf8")) for code in CODES}
    auth=json.loads((ROOT/"static/i18n/auth.json").read_text(encoding="utf8"))
    i18n=(ROOT/"static/js/i18n.js").read_text(encoding="utf8")
    styles=(ROOT/"static/css/auth.css").read_text(encoding="utf8")
    assert all(set(auth[c])==set(auth["en"]) for c in CODES)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        for form,width,height in (("desktop",1280,900),("phone",390,844)):
            for template,route,key in ROUTES:
                page=browser.new_page(viewport={"width":width,"height":height})
                errors=[]
                page.on("pageerror", lambda x:errors.append(str(x)))
                page.route("https://sxf-preview.test"+route,lambda r:r.fulfill(
                    status=200,content_type="text/html",body="<html><body>start</body></html>"))
                def locale_handler(r):
                    code=Path(urlparse(r.request.url).path).stem
                    data=auth if code=="auth" else locales[code]
                    r.fulfill(status=200,content_type="application/json",body=json.dumps(data,ensure_ascii=False))
                page.route("https://sxf-preview.test/static/i18n/*.json*",locale_handler)
                page.goto("https://sxf-preview.test"+route)
                page.evaluate("localStorage.setItem('sxf_lang','en')")
                page.set_content(clean_template(template),wait_until="load")
                # The full styles are local rather than fetched over the network.
                page.add_style_tag(content=styles)
                page.add_script_tag(content=i18n)
                page.wait_for_function("!!document.getElementById('sxfStandaloneLanguage')")
                page.wait_for_function("!!document.querySelector('[data-i18n=\"app.auth."+key+"\"]')",timeout=15000)
                for code in CODES:
                    page.locator("#sxfStandaloneLanguage").select_option(code)
                    page.wait_for_function("(lang)=>window.SXFI18n.current()===lang",arg=code)
                    # Both the language switch and async source catalog can
                    # finish on separate microtasks; assert eventual UI state.
                    expected=auth[code][key]
                    page.wait_for_function("({key,value}) => [...document.querySelectorAll('[data-i18n]')].some(e => e.getAttribute('data-i18n')===key && e.textContent.trim()===value)",arg={"key":"app.auth."+key,"value":expected})
                    assert page.evaluate("document.documentElement.lang")==code
                    select=page.locator("#sxfStandaloneLanguage")
                    assert select.input_value()==code
                    assert page.evaluate("document.documentElement.scrollWidth-window.innerWidth")<=1,(template,form,code)
                assert not errors,(template,form,errors)
                if template in ("login","signup","admin_login"):
                    out=Path("artifacts")
                    out.mkdir(exist_ok=True)
                    page.screenshot(path=str(out/f"i18n-{template}-{form}.png"))
                print(f"PAGE_I18N_OK {template} {form} 7-locales")
                page.close()
        browser.close()

if __name__=="__main__":main()
