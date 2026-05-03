#!/usr/bin/env python3
"""
i18n wrap pass — replaces unwrapped TR string literals in JS source files
with `_t('<key>', '<TR fallback>')` calls and registers each new key in the
master CSV (TR populated, other languages left blank → build falls back to TR).

Scope (this pass):
    - static/js/app.js
    - static/js/ui.js
HTML files are intentionally NOT touched here — their TR text is handled by
hand-curated patches because element semantics matter (data-i18n vs
data-i18n-html vs data-i18n-attr).

Usage:
    python3 scripts/i18n_wrap.py            # dry-run, prints summary
    python3 scripts/i18n_wrap.py --apply    # rewrite files + update master CSV
"""
from __future__ import annotations
import os, re, sys, csv, hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER = os.path.join(ROOT, 'static/i18n/_master.csv')
LANGS = ['tr', 'en', 'de', 'fr', 'nl', 'it', 'es']

JS_TARGETS = [
    ('static/js/app.js', 'app.dyn'),
    ('static/js/ui.js',  'ui.dyn'),
]

# Strings we intentionally LEAVE alone (brand names, code identifiers used as keys, etc.)
SKIP_EXACT = {
    'TR', 'EN', 'DE', 'FR', 'NL', 'IT', 'ES',
}


def _slug(text: str) -> str:
    s = text.lower()
    s = re.sub(r'\$\{\.\.\.\}', '_', s)
    s = re.sub(r'[^a-z0-9çğıöşü ]+', ' ', s)
    s = (s.replace('ç', 'c').replace('ğ', 'g').replace('ı', 'i')
           .replace('ö', 'o').replace('ş', 's').replace('ü', 'u'))
    s = re.sub(r'\s+', '_', s).strip('_')
    return s[:48] or 'x'


def _make_key(prefix: str, text: str, used: set[str]) -> str:
    base = f'{prefix}.{_slug(text)}'
    if base not in used:
        return base
    h = hashlib.md5(text.encode()).hexdigest()[:6]
    return f'{base}_{h}'


# ---------- JS string scanner (same logic as extract) ----------
# Characters that, as the previous non-whitespace token, mean "/" starts a
# regex literal rather than a division operator.
_REGEX_PREV = set('(,=:[;!&|?{}+-*~^%<>')


def _prev_nonws(src: str, i: int) -> str:
    j = i - 1
    while j >= 0 and src[j] in ' \t\n\r':
        j -= 1
    return src[j] if j >= 0 else ''


def _skip_regex(src: str, i: int) -> int:
    """src[i] == '/' starts a regex; return index after the closing '/flags'."""
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
            return i  # broken regex; bail
        i += 1
    return n


def iter_js_strings(src: str):
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
            buf, raw_parts, has_interp = [], [], False
            while i < n:
                ch = src[i]
                if ch == '\\' and i + 1 < n:
                    buf.append(src[i + 1])
                    raw_parts.append(src[i:i + 2])
                    i += 2
                    continue
                if ch == q:
                    i += 1
                    yield (start, i, q, ''.join(buf), has_interp)
                    break
                if q == '`' and ch == '$' and i + 1 < n and src[i + 1] == '{':
                    has_interp = True
                    depth, expr_start = 1, i + 2
                    i += 2
                    while i < n and depth:
                        if src[i] == '{':
                            depth += 1
                        elif src[i] == '}':
                            depth -= 1
                        i += 1
                    buf.append('${...}')
                    raw_parts.append(src[expr_start - 2:i])
                    continue
                buf.append(ch)
                raw_parts.append(ch)
                i += 1
            else:
                break
            continue
        i += 1


TR_CHARS = set('ığşöüçĞŞÖÜÇİ')


def has_tr(t): return any(c in TR_CHARS for c in t)


def js_escape(s: str, quote: str = "'") -> str:
    """Escape a string for a JS single-quoted literal."""
    out = s.replace('\\', '\\\\').replace(quote, '\\' + quote)
    out = out.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    return out


_T_CALL_RE = re.compile(r'(?:_t|i18n\.t|SXFI18n\.t)\s*$')


def _inside_t_call(src: str, pos: int) -> bool:
    """Return True if `pos` is somewhere inside a `(...)` whose callee is one of
    _t / i18n.t / SXFI18n.t.  Walks backwards skipping balanced parens, strings,
    comments and regex literals up to ~600 chars."""
    i = pos - 1
    depth = 0
    limit = max(0, pos - 600)
    while i >= limit:
        ch = src[i]
        # Skip backwards through string literals
        if ch in ('"', "'", '`'):
            q = ch
            j = i - 1
            while j >= 0:
                if src[j] == q and (j == 0 or src[j - 1] != '\\'):
                    break
                j -= 1
            i = j - 1
            continue
        if ch == ')':
            depth += 1
            i -= 1
            continue
        if ch == '(':
            if depth > 0:
                depth -= 1
                i -= 1
                continue
            # Unclosed paren — inspect callee
            callee_end = i
            j = i - 1
            while j >= 0 and src[j] in ' \t\n\r':
                j -= 1
            # walk back over identifier chars (incl. dot for i18n.t / SXFI18n.t)
            k = j
            while k >= 0 and (src[k].isalnum() or src[k] in '_.$'):
                k -= 1
            ident = src[k + 1:j + 1]
            if ident in ('_t', 'i18n.t', 'SXFI18n.t'):
                return True
            return False
        i -= 1
    return False


def find_unwrapped_in_js(src: str):
    """Yield (start, end, text) for each TR literal NOT already inside _t( )."""
    for start, end, q, body, has_interp in iter_js_strings(src):
        if not has_tr(body):
            continue
        if body.strip() in SKIP_EXACT:
            continue
        if has_interp:
            continue
        # Safety filters — skip anything that looks like an HTML/JS fragment
        # rather than a clean user-facing message.
        if len(body) > 180 or len(body) < 2:
            continue
        if any(bad in body for bad in ('\n', '\r', '<', '>', '&#', '&amp;', '${')):
            continue
        # First non-space char should be a normal letter / digit (not '/' '\\' etc.)
        head = body.lstrip()
        if not head or not (head[0].isalpha() or head[0].isdigit() or head[0] in '"\'(¡¿“„«…→•·'):
            continue
        # Already wrapped?  Walk backwards: find the unclosed '(' (if any) and
        # check whether its callee identifier is _t / i18n.t / SXFI18n.t.
        if _inside_t_call(src, start):
            continue
        yield start, end, body


def load_master() -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    if not os.path.exists(MASTER):
        return rows, ['key'] + LANGS
    with open(MASTER, encoding='utf-8') as fh:
        r = csv.DictReader(fh)
        fields = r.fieldnames or (['key'] + LANGS)
        for row in r:
            rows.append(row)
    return rows, fields


def save_master(rows: list[dict], fields: list[str]):
    rows_sorted = sorted(rows, key=lambda r: r['key'])
    with open(MASTER, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fields, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for r in rows_sorted:
            w.writerow(r)


def main():
    apply = '--apply' in sys.argv
    rows, fields = load_master()
    by_key = {r['key']: r for r in rows}
    by_tr_text = {r.get('tr', ''): r['key'] for r in rows if r.get('tr')}
    used_keys = set(by_key)

    new_rows: list[dict] = []
    total_replacements = 0
    file_summaries = []

    for rel, prefix in JS_TARGETS:
        path = os.path.join(ROOT, rel)
        src = open(path, encoding='utf-8').read()
        finds = list(find_unwrapped_in_js(src))
        if not finds:
            file_summaries.append((rel, 0, 0))
            continue

        # Replace from end → start so offsets stay valid
        finds_sorted = sorted(finds, key=lambda x: x[0], reverse=True)
        new_src = src
        replaced = 0
        new_for_file = 0
        for start, end, body in finds_sorted:
            # Existing key for this exact TR text?
            if body in by_tr_text:
                key = by_tr_text[body]
            else:
                key = _make_key(prefix, body, used_keys)
                used_keys.add(key)
                row = {f: '' for f in fields}
                row['key'] = key
                row['tr'] = body
                by_key[key] = row
                by_tr_text[body] = key
                new_rows.append(row)
                new_for_file += 1
            # Build replacement: _t('key', 'TR fallback')
            esc_key = js_escape(key, "'")
            esc_body = js_escape(body, "'")
            replacement = f"_t('{esc_key}', '{esc_body}')"
            new_src = new_src[:start] + replacement + new_src[end:]
            replaced += 1

        file_summaries.append((rel, replaced, new_for_file))
        total_replacements += replaced
        if apply:
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(new_src)

    print('=' * 64)
    print(f'i18n WRAP {"APPLY" if apply else "DRY-RUN"} — JS targets')
    print('=' * 64)
    for rel, n, k in file_summaries:
        print(f'  {rel:<28} {n:>4} replacements  ({k} new keys)')
    print(f'  TOTAL                       {total_replacements:>4} replacements  ({len(new_rows)} new keys)')

    if apply and new_rows:
        rows.extend(new_rows)
        save_master(rows, fields)
        print(f'master: appended {len(new_rows)} new keys → {MASTER}')


if __name__ == '__main__':
    main()
