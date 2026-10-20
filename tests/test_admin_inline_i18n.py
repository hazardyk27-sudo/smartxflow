"""Protect localized admin inline confirmation/toast literals across seven languages."""
import json
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    html=(ROOT/"templates/admin.html").read_text(encoding="utf8")
    catalog=json.loads((ROOT/"static/i18n/admin.json").read_text(encoding="utf8"))
    keys=re.findall(r"sxfAdminInlineT\('([^']+)'",html)
    assert len(keys)>=26,len(keys)
    assert "function sxfAdminInlineT(key, fallback)" in html
    for l in ("tr","en","de","fr","nl","it","es"):
        missing=[k for k in keys if not isinstance(catalog[l].get(k),str) or not catalog[l][k].strip()]
        assert not missing,(l,missing)
    for text in ("En fazla 5 maç seçilebilir","Bu maç zaten seçili","Bu içeriği silmek istediğinize emin misiniz?"):
        assert "showToast('"+text not in html
        assert "confirm('"+text not in html
    print("ADMIN_INLINE_TOAST_CONTRACT_OK",len(keys),"bindings x 7 locales")
if __name__=="__main__": main()
