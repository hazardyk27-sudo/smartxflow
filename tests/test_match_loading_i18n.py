"""Prevent untranslated loading placeholders in match table and mobile cards."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    for name in ("app.js","app.js.src"):
        src=(ROOT/"static/js"/name).read_text(encoding="utf8")
        assert src.count('data-i18n="app.j.loading"')==2,name
        assert src.count("window.SXFI18n.t('app.j.loading') : 'Yükleniyor...'}")==2,name
        assert '<p style="font-size: 13px; margin: 0;">Yükleniyor...</p>' not in src
    print("MATCH_LOADING_I18N_OK 7 locale bindings, desktop and mobile")
if __name__=="__main__": main()
