#!/usr/bin/env python3
"""
SmartXFlow i18n extractor / auditor.

Scans templates/*.html and static/js/*.js for Turkish-character literals
that are NOT yet wrapped by an i18n mechanism (data-i18n on HTML, _t(...) /
i18n.t(...) on JS). Outputs a report grouped by file.

Usage:
    python3 scripts/i18n_extract.py            # report only
    python3 scripts/i18n_extract.py --csv      # also write static/i18n/_unwrapped.csv
"""
from __future__ import annotations
import os, re, sys, json, csv, html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TR_CHARS = set('ığşöüçĞŞÖÜÇİ')
BRANDS = {
    'SmartXFlow', 'MIM', 'Sharp', 'Big Money', 'BigMoney', 'Moneyway',
    'MW', 'Underdog Pressure', 'Confirmed Money', 'Early Money Lock',
    'Fake Sharp', 'Dropping Odds', 'HUGE MONEY', 'Public Move', 'Public move',
}

HTML_FILES = [
    'templates/index.html', 'templates/nedir.html', 'templates/rehber.html',
    'templates/rehber_oran_analizi.html', 'templates/rehber_para_hareketi.html',
    'templates/rehber_canli_oran_takibi.html',
    'templates/blog.html', 'templates/blog_detail.html',
    'templates/pricing.html', 'templates/contact.html',
    'templates/privacy.html', 'templates/terms.html', 'templates/cookies.html',
]
JS_FILES = ['static/js/app.js', 'static/js/ui.js']


def has_tr(text: str) -> bool:
    return any(c in TR_CHARS for c in text)


# ---------- HTML scanner ----------
# We look at every visible text node that contains TR characters and is NOT
# inside an element that already has data-i18n / data-i18n-html / data-i18n-attr.
# A pragmatic regex-based approach: find ">TEXT<" segments outside <script>/<style>.
SCRIPT_BLOCK = re.compile(r'<(script|style)\b[^>]*>.*?</\1>', re.DOTALL | re.IGNORECASE)
TAG_RE = re.compile(r'<[^>]+>')


def scan_html(path: str) -> list[dict]:
    src = open(path, encoding='utf-8').read()
    # Track wrapped tags by line for context
    findings = []
    # Strip <script>/<style> for visible-text scan
    visible = SCRIPT_BLOCK.sub(lambda m: '\n' * m.group(0).count('\n'), src)
    # Walk line by line so we get line numbers
    line_no = 0
    in_open_tag_with_i18n = []  # stack of bool
    for line in visible.split('\n'):
        line_no += 1
        if not has_tr(line):
            continue
        # Skip lines that are clearly inside data-i18n attribute already
        # (heuristic: the line declares data-i18n=... and then text)
        # We keep them only if the visible TR text is OUTSIDE the tag attrs.
        # Strip tags, see what remains
        no_tags = TAG_RE.sub('', line).strip()
        if not no_tags or not has_tr(no_tags):
            continue
        # Find element directly enclosing the text (look back to nearest opening tag)
        # If that tag has data-i18n=, skip
        # cheap check: does the same line carry data-i18n / data-i18n-html?
        if 'data-i18n=' in line or 'data-i18n-html=' in line:
            # The visible text is the localized fallback — already covered
            continue
        # Could be split across lines; we still report (manual review).
        findings.append({
            'file': path, 'line': line_no, 'kind': 'html-text',
            'text': no_tags[:200],
        })
    # Attribute scan: title=, placeholder=, alt=, aria-label= containing TR
    attr_re = re.compile(r'\b(title|placeholder|alt|aria-label|content)\s*=\s*"([^"]*)"')
    for m in attr_re.finditer(src):
        val = m.group(2)
        if not has_tr(val):
            continue
        # find line
        ln = src.count('\n', 0, m.start()) + 1
        # skip if the attribute is itself a meta tag content (covered separately) — keep but tag
        # also skip if there's data-i18n-attr= on same element (rough check)
        # find tag start
        tag_start = src.rfind('<', 0, m.start())
        tag_end = src.find('>', m.start())
        tag = src[tag_start:tag_end + 1] if tag_start >= 0 and tag_end > tag_start else ''
        if 'data-i18n-attr=' in tag and m.group(1) in tag:
            continue
        findings.append({
            'file': path, 'line': ln, 'kind': f'html-attr:{m.group(1)}',
            'text': val[:200],
        })
    return findings


# ---------- JS scanner ----------
# A literal is "interesting" when it contains TR characters and is NOT the
# argument of _t( / i18n.t( / SXFI18n.t(.
# We look at every "..." or '...' or `...` literal.
_REGEX_PREV = set('(,=:[;!&|?{}+-*~^%<>')


def _prev_nonws(src: str, i: int) -> str:
    j = i - 1
    while j >= 0 and src[j] in ' \t\n\r':
        j -= 1
    return src[j] if j >= 0 else ''


def _skip_regex(src: str, i: int) -> int:
    n = len(src)
    i += 1
    in_class = False
    while i < n:
        ch = src[i]
        if ch == '\\' and i + 1 < n:
            i += 2
            continue
        if ch == '[' and not in_class:
            in_class = True
        elif ch == ']' and in_class:
            in_class = False
        elif ch == '/' and not in_class:
            i += 1
            while i < n and src[i] in 'gimsuy':
                i += 1
            return i
        elif ch == '\n':
            return i
        i += 1
    return n


def _iter_js_strings(src: str):
    """Hand-rolled string scanner: yields (start, quote, body)."""
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            j = src.find('\n', i)
            i = n if j < 0 else j + 1
            continue
        if c == '/' and i + 1 < n and src[i + 1] == '*':
            j = src.find('*/', i + 2)
            i = n if j < 0 else j + 2
            continue
        if c == '/':
            prev = _prev_nonws(src, i)
            if prev == '' or prev in _REGEX_PREV:
                i = _skip_regex(src, i)
                continue
        if c in ('"', "'", '`'):
            q = c
            start = i
            i += 1
            buf = []
            while i < n:
                ch = src[i]
                if ch == '\\' and i + 1 < n:
                    buf.append(src[i + 1])
                    i += 2
                    continue
                if ch == q:
                    i += 1
                    yield start, q, ''.join(buf)
                    break
                # template literal: skip ${...}
                if q == '`' and ch == '$' and i + 1 < n and src[i + 1] == '{':
                    depth = 1
                    i += 2
                    while i < n and depth:
                        if src[i] == '{':
                            depth += 1
                        elif src[i] == '}':
                            depth -= 1
                        i += 1
                    buf.append('${...}')
                    continue
                buf.append(ch)
                i += 1
            else:
                break
            continue
        i += 1


def scan_js(path: str) -> list[dict]:
    src = open(path, encoding='utf-8').read()
    findings = []
    for start, q, body in _iter_js_strings(src):
        if not has_tr(body):
            continue
        # Already wrapped by _t( / i18n.t( / SXFI18n.t( ?
        prefix = src[max(0, start - 32):start]
        if re.search(r'(?:_t|i18n\.t|SXFI18n\.t)\s*\(\s*$', prefix):
            continue
        ln = src.count('\n', 0, start) + 1
        findings.append({
            'file': path, 'line': ln, 'kind': f'js-{q}',
            'text': body[:200],
        })
    return findings


def main():
    write_csv = '--csv' in sys.argv
    all_findings: list[dict] = []
    for f in HTML_FILES:
        fp = os.path.join(ROOT, f)
        if os.path.exists(fp):
            all_findings.extend(scan_html(fp))
    for f in JS_FILES:
        fp = os.path.join(ROOT, f)
        if os.path.exists(fp):
            all_findings.extend(scan_js(fp))

    # Group by file
    by_file: dict[str, list[dict]] = {}
    for f in all_findings:
        by_file.setdefault(f['file'], []).append(f)

    print('=' * 70)
    print(f'i18n EXTRACT REPORT — {len(all_findings)} unwrapped TR strings')
    print('=' * 70)
    for fp, items in sorted(by_file.items()):
        print(f'\n{fp}  ({len(items)} unwrapped)')
        for it in items[:8]:
            preview = it['text'].replace('\n', ' ')[:90]
            print(f"  L{it['line']:>5}  [{it['kind']:<16}]  {preview}")
        if len(items) > 8:
            print(f"  ... +{len(items) - 8} more")

    if write_csv:
        out = os.path.join(ROOT, 'static/i18n/_unwrapped.csv')
        with open(out, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(['file', 'line', 'kind', 'text'])
            for it in all_findings:
                w.writerow([it['file'], it['line'], it['kind'], it['text']])
        print(f'\nCSV written: {out}')

    # Exit non-zero if anything left → CI-friendly
    return 1 if all_findings else 0


if __name__ == '__main__':
    sys.exit(main())
