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
    'templates/index.html', 'templates/landing.html', 'templates/nedir.html',
    'templates/rehber.html', 'templates/rehber_oran_analizi.html',
    'templates/rehber_para_hareketi.html', 'templates/rehber_canli_oran_takibi.html',
    'templates/pricing.html', 'templates/legal.html',
    'templates/analysis.html', 'templates/match_detail.html',
    'templates/status.html',
]
JS_FILES = [
    'static/js/app.js', 'static/js/ui.js', 'static/js/i18n.js',
    # NOTE: static/js/inline.js is intentionally excluded.  It is a single,
    # densely-packed bundle of dynamically-injected HTML template fragments
    # (each line is an HTML chunk that's later inserted into the DOM via
    # innerHTML).  Its TR strings can't be auto-wrapped without restructuring
    # the file; they are tracked manually in `static/i18n/_unwrapped_inline.md`.
]


# --- Brand allowlist ---------------------------------------------------------
# Texts that are nothing more than brand tokens / marketing words must not be
# reported as untranslatable.  We strip every brand string from the candidate
# text and ask: does it still contain TR alphabet letters?  If not → skip.
_BRANDS_RE = re.compile(
    r'\b(?:' + '|'.join(sorted((re.escape(b) for b in BRANDS), key=len, reverse=True)) + r')\b',
    re.IGNORECASE,
)


def has_tr(text: str) -> bool:
    return any(c in TR_CHARS for c in text)


def needs_translation(text: str) -> bool:
    """True if the text actually contains TR letters AFTER stripping brands."""
    if not has_tr(text):
        return False
    stripped = _BRANDS_RE.sub(' ', text)
    return has_tr(stripped)


# ---------- HTML scanner ----------
# We look at every visible text node that contains TR characters and is NOT
# inside an element that already has data-i18n / data-i18n-html / data-i18n-attr.
# A pragmatic regex-based approach: find ">TEXT<" segments outside <script>/<style>.
SCRIPT_BLOCK = re.compile(r'<(script|style)\b[^>]*>.*?</\1>', re.DOTALL | re.IGNORECASE)
# Open tag + simple text content + close tag (no nested tags)
TAG_TEXT_RE = re.compile(
    r'(<([a-zA-Z][\w:-]*)\b([^>]*)>)([^<>{}]*?)(</\2\s*>)', re.DOTALL,
)
ATTR_RE = re.compile(r'\b(title|placeholder|alt|aria-label|content)\s*=\s*"([^"]*)"')


def _mask_blocks(src: str) -> str:
    return SCRIPT_BLOCK.sub(lambda m: re.sub(r'[^\n]', ' ', m.group(0)), src)


def scan_html(path: str) -> list[dict]:
    src = open(path, encoding='utf-8').read()
    masked = _mask_blocks(src)
    findings = []
    # text-content slots — only flag when open tag lacks data-i18n
    for m in TAG_TEXT_RE.finditer(masked):
        open_tag = m.group(1)
        text     = m.group(4)
        if 'data-i18n' in open_tag:
            continue
        if '{{' in text or '{%' in text:
            continue
        stripped = text.strip()
        if not stripped or not needs_translation(stripped):
            continue
        if stripped in BRANDS:
            continue
        ln = masked.count('\n', 0, m.start(4)) + 1
        findings.append({
            'file': path, 'line': ln, 'kind': 'html-text',
            'text': stripped[:200],
        })
    # attribute slots
    for m in ATTR_RE.finditer(masked):
        attr_name = m.group(1); val = m.group(2)
        if not needs_translation(val):
            continue
        tag_start = src.rfind('<', 0, m.start())
        tag_end   = src.find('>', m.start())
        tag = src[tag_start:tag_end + 1] if tag_start >= 0 and tag_end > tag_start else ''
        if 'data-i18n-attr=' in tag and re.search(rf'\b{attr_name}:', tag):
            continue
        ln = src.count('\n', 0, m.start()) + 1
        findings.append({
            'file': path, 'line': ln, 'kind': f'html-attr:{attr_name}',
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


def _inside_t_call(src: str, pos: int) -> bool:
    """True if pos sits inside `(...)` whose callee is _t / i18n.t / SXFI18n.t.
    Walks backwards across balanced parens & string literals (up to 600 chars)."""
    i = pos - 1; depth = 0; limit = max(0, pos - 800)
    while i >= limit:
        ch = src[i]
        if ch in ('"', "'", '`'):
            q = ch; j = i - 1
            while j >= 0:
                if src[j] == q and (j == 0 or src[j - 1] != '\\'): break
                j -= 1
            i = j - 1; continue
        if ch == ')': depth += 1; i -= 1; continue
        if ch == '(':
            if depth > 0: depth -= 1; i -= 1; continue
            j = i - 1
            while j >= 0 and src[j] in ' \t\n\r': j -= 1
            k = j
            while k >= 0 and (src[k].isalnum() or src[k] in '_.$'): k -= 1
            ident = src[k + 1:j + 1]
            return ident in ('_t', 'i18n.t', 'SXFI18n.t')
        i -= 1
    return False


_CONSOLE_RE = re.compile(r'console\s*\.\s*(?:log|warn|error|info|debug|trace)\s*\($')


def _inside_console_call(src: str, pos: int) -> bool:
    """True if pos is inside a console.{log,warn,...}( ... ) call."""
    i = pos - 1; depth = 0; limit = max(0, pos - 800)
    while i >= limit:
        ch = src[i]
        if ch in ('"', "'", '`'):
            q = ch; j = i - 1
            while j >= 0:
                if src[j] == q and (j == 0 or src[j - 1] != '\\'): break
                j -= 1
            i = j - 1; continue
        if ch == ')': depth += 1; i -= 1; continue
        if ch == '(':
            if depth > 0: depth -= 1; i -= 1; continue
            j = i + 1
            return bool(_CONSOLE_RE.search(src[max(0, i - 40):j]))
        i -= 1
    return False


def scan_js(path: str) -> list[dict]:
    src = open(path, encoding='utf-8').read()
    findings = []
    for start, q, body in _iter_js_strings(src):
        if not needs_translation(body):
            continue
        if _inside_t_call(src, start):
            continue
        # Developer-only debug messages — not user-facing, intentionally TR.
        if _inside_console_call(src, start):
            continue
        # Bracket-prefixed log tags like '[AutoRefresh] foo' / '[Live] bar'
        if body.lstrip().startswith('[') and ']' in body[:40]:
            continue
        # Inline HTML fragments embedded in template literals — these are
        # structurally combined chunks, not single user-visible messages.
        if '<' in body or '>' in body or '&#' in body:
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
