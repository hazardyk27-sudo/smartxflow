#!/usr/bin/env python3
"""Regression: ensure known-bad TR literals never re-appear unwrapped.
Run after i18n_extract.py — fails CI if any known fixture is still raw."""
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# (file, regex pattern that MUST NOT appear)
# Each fixture: (file, pattern that matches an UNWRAPPED occurrence).
# Wrapped occurrences carry data-i18n="..." on the SAME tag, so we exclude
# patterns where data-i18n appears just before the text.
# Per-line scan: each fixture flags any line in `file` matching `bad_pat`
# UNLESS that same line also matches `ok_pat` (the wrapped form).
FIXTURES = [
    # (file, bad regex, optional ok regex on same line)
    ('templates/index.html', r'placeholder="Ara\.\.\."', r'data-i18n-attr="placeholder:'),
    ('templates/index.html', r'>\s*Alarmlar\s*<',        r'data-i18n="[^"]+">\s*Alarmlar'),
    ('templates/index.html', r'>\s*Favoriler\s*<',       r'data-i18n="[^"]+">\s*Favoriler'),
    ('templates/index.html', r'>\s*Analizler\s*<',       r'data-i18n="[^"]+">\s*Analizler'),
    ('templates/analysis.html', r'>\s*Ana Sayfa\s*<',    r'data-i18n="nav\.home"'),
    ('templates/analysis.html', r'>\s*Paketler\s*<',     r'data-i18n="nav\.(?:packages|pricing)"'),
    ('templates/status.html',   r'>\s*Ana Sayfa\s*<',    r'data-i18n="nav\.home"'),
    ('templates/status.html',   r'<th>\s*Durum\s*</th>', r'data-i18n="status\.col_durum"'),
    ('static/js/app.js',        r"`PNG kaydedildi:",     None),
    ('static/js/app.js',        r"txt\+='===== ALARM VERILERI =====", None),
    ('static/js/ui.js',         r"'Beklemede</span>'",   None),
]
fail = 0
for entry in FIXTURES:
    relpath, bad, ok = entry
    fp = os.path.join(ROOT, relpath)
    if not os.path.exists(fp):
        print(f'WARN missing {relpath}'); continue
    bad_re = re.compile(bad); ok_re = re.compile(ok) if ok else None
    for ln, line in enumerate(open(fp, encoding='utf-8'), 1):
        if bad_re.search(line) and not (ok_re and ok_re.search(line)):
            print(f'FAIL {relpath}:{ln} matched /{bad}/ -> {line.strip()[:80]!r}')
            fail += 1
if fail:
    print(f'\n{fail} regression(s) found'); sys.exit(1)
print('OK: 0 regressions across', len(FIXTURES), 'fixtures')
