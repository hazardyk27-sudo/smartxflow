"""Static full-site translation contract for every non-Polymarket HTML route."""
from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LANGS=("tr","en","de","fr","nl","it","es")
EXCLUDED={"poly.html"}
class Reader(HTMLParser):
    def __init__(self):
        super().__init__();self.keys=[];self.bad=[]
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        for attr in ("data-i18n","data-i18n-html"):
            if d.get(attr):self.keys.append(d[attr])
        if d.get("data-i18n-attr"):
            for item in d["data-i18n-attr"].split(";"):
                if ":" not in item:self.bad.append(item)
                else:self.keys.append(item.split(":",1)[1].strip())
def resolve(obj,key):
    for part in key.split("."):
        if not isinstance(obj,dict):return None
        obj=obj.get(part)
    return obj
def test_all_public_app_and_auth_templates_load_i18n_and_have_valid_keys():
    templates=sorted(p for p in (ROOT/"templates").glob("*.html") if p.name not in EXCLUDED)
    assert len(templates)>20
    locales={
        code:json.loads((ROOT/"static/i18n"/f"{code}.json").read_text(encoding="utf8"))
        for code in LANGS
    }
    keys=set()
    for path in templates:
        source=path.read_text(encoding="utf8")
        assert 'js/i18n.js' in source, f"{path.name}: no translation loader"
        parser=Reader();parser.feed(source)
        assert not parser.bad,(path.name,parser.bad)
        keys.update(parser.keys)
        for lang,obj in locales.items():
            missing=[key for key in parser.keys if '{{' not in key and '{%' not in key and not isinstance(resolve(obj,key),str)]
            assert not missing,(path.name,lang,sorted(set(missing)))
    assert len(keys)>300, f"translation annotations unexpectedly dropped: {len(keys)}"
    auth=json.loads((ROOT/"static/i18n/auth.json").read_text(encoding="utf8"))
    for code in LANGS:
        assert set(auth[code])==set(auth["en"])
        assert len(auth[code])>90
        assert all(isinstance(text,str) and text.strip() for text in auth[code].values())
