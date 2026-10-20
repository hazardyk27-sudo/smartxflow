"""Seven-locale Analizler V4 dictionary parity and binding coverage."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CODES=("tr","en","de","fr","nl","it","es")

def flatten(data,prefix=""):
    for key,value in data.items():
        name=f"{prefix}.{key}" if prefix else key
        if isinstance(value,dict):
            yield from flatten(value,name)
        else:
            yield name,value

class I18NCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dicts={
            c:json.loads((ROOT/"static/i18n"/f"{c}.json").read_text(encoding="utf-8"))
            for c in CODES
        }
    def test_existing_dictionary_key_sets_stay_complete(self):
        sets=[set(flatten(data)) for data in self.dicts.values()]
        # Compare KEYS, never values; seven locales must have the same tree.
        keysets=[set(k for k,_ in flatten(data)) for data in self.dicts.values()]
        self.assertTrue(all(k==keysets[0] for k in keysets), "locale key drift")
        self.assertGreater(len(keysets[0]),1100)
    def test_all_v4_visible_keys_are_translated(self):
        js=(ROOT/"static/js/base-signals.js").read_text(encoding="utf-8")
        html=(ROOT/"templates/index.html").read_text(encoding="utf-8")
        dynamic=set(re.findall(r"\\b(?:t|fmt)\\('([a-z][a-z0-9_]*)'",js))
        dynamic.update(re.findall(r"\\b(?:DESC|CATS)\\s*=",js) and
                       re.findall(r"['\"](engine_[a-z0-9_]+_desc|cat_[a-z0-9_]+)['\"]",js))
        attrs=set(re.findall(r"app\\.v4\\.([a-z0-9_]+)",html))
        keys=dynamic|attrs
        self.assertGreater(len(keys),70, "cannot verify unannotated hardcoded V4")
        for code,locale in self.dicts.items():
            v4=locale["app"]["v4"]
            missing=keys-set(v4)
            self.assertFalse(missing,f"{code} untranslated V4 keys: {sorted(missing)}")
            self.assertTrue(all(isinstance(v4[k],str) and v4[k].strip() for k in keys))
            self.assertEqual(set(v4),set(self.dicts["tr"]["app"]["v4"]))
            for k in ("home_wins","away_wins","match_count","signals_count",
                      "day_count","motor_open","engines_count"):
                self.assertIn("{",v4[k])
    def test_static_v4_accessibility_translated(self):
        html=(ROOT/"templates/index.html").read_text(encoding="utf-8")
        for id in ("sxfSignalClose","sxfSignalPrevious","sxfSignalNext",
                   "sxfSignalSearch","sxfSignalRefresh","sxfSignalDateRail"):
            tag=re.search(r'<[^>]+id="'+id+r'"[^>]*>',html)
            self.assertIsNotNone(tag,id)
            self.assertIn("data-i18n-attr=",tag.group(0),id)
        self.assertIn("window.addEventListener('i18n:change', refreshLanguage)", 
                      (ROOT/"static/js/base-signals.js").read_text(encoding="utf-8"))

if __name__=="__main__":
    unittest.main()
