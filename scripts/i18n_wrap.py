#!/usr/bin/env python3
"""
i18n auto-wrap pass.

  - JS targets (app.js, ui.js): rewrite each unwrapped TR string literal as
        _t('<key>', '<TR fallback>')
    inserting a leading space when the previous character is part of an
    identifier (so `return"foo"` becomes `return _t('k','foo')`, never
    `return_t(...)`).

  - HTML targets (every user-facing template): inject `data-i18n="<key>"` (or
    `data-i18n-attr="<attr>:<key>;..."`) on tags that contain unwrapped TR
    text or attribute values.  i18n.js then swaps them on load / lang-change.

Each new master row records the file(s) where the literal originated in the
`file_refs` column (semicolon-separated `path:line`).

Usage:
    python3 scripts/i18n_wrap.py            # dry-run summary
    python3 scripts/i18n_wrap.py --apply    # rewrite files + master CSV
"""
from __future__ import annotations
import os, re, sys, csv, hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER = os.path.join(ROOT, 'static/i18n/_master.csv')
LANGS = ['tr', 'en', 'de', 'fr', 'nl', 'it', 'es']
FIELDS = ['key', 'file_refs'] + LANGS

# --- targets ----------------------------------------------------------------
JS_TARGETS = [
    ('static/js/app.js', 'app.dyn'),
    ('static/js/ui.js',  'ui.dyn'),
]

HTML_TARGETS = [
    ('templates/index.html',                       'idx'),
    ('templates/landing.html',                     'land'),
    ('templates/nedir.html',                       'nedir'),
    ('templates/rehber.html',                      'reh'),
    ('templates/rehber_oran_analizi.html',         'reh.or'),
    ('templates/rehber_para_hareketi.html',        'reh.pa'),
    ('templates/rehber_canli_oran_takibi.html',    'reh.li'),
    ('templates/pricing.html',                     'pri'),
    ('templates/legal.html',                       'leg'),
    ('templates/analysis.html',                    'ana'),
    ('templates/match_detail.html',                'md'),
    ('templates/status.html',                      'sta'),
]

TR_CHARS = set('ığşöüçĞŞÖÜÇİ')

BRANDS = {
    'SmartXFlow', 'MIM', 'Sharp', 'Big Money', 'BigMoney', 'Moneyway',
    'MW', 'Underdog Pressure', 'Confirmed Money', 'Early Money Lock',
    'Fake Sharp', 'Dropping Odds', 'HUGE MONEY', 'Public Move', 'Public move',
    'Volume Shock',
}
_BRANDS_RE = re.compile(
    r'\b(?:' + '|'.join(sorted((re.escape(b) for b in BRANDS), key=len, reverse=True)) + r')\b',
    re.IGNORECASE,
)

SKIP_EXACT = {'TR', 'EN', 'DE', 'FR', 'NL', 'IT', 'ES'}


def has_tr(t: str) -> bool: return any(c in TR_CHARS for c in t)


def needs_translation(t: str) -> bool:
    if not has_tr(t):
        return False
    return has_tr(_BRANDS_RE.sub(' ', t))


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


# ============================================================================
# JS scanner / wrapper
# ============================================================================
_REGEX_PREV = set('(,=:[;!&|?{}+-*~^%<>')
_IDENT_TAIL = re.compile(r'[A-Za-z0-9_$]')


def _prev_nonws(src: str, i: int) -> str:
    j = i - 1
    while j >= 0 and src[j] in ' \t\n\r':
        j -= 1
    return src[j] if j >= 0 else ''


def _skip_regex(src: str, i: int) -> int:
    n = len(src); i += 1; in_class = False
    while i < n:
        ch = src[i]
        if ch == '\\' and i + 1 < n:
            i += 2; continue
        if ch == '[' and not in_class: in_class = True
        elif ch == ']' and in_class:    in_class = False
        elif ch == '/' and not in_class:
            i += 1
            while i < n and src[i] in 'gimsuy': i += 1
            return i
        elif ch == '\n': return i
        i += 1
    return n


def iter_js_strings(src: str):
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            j = src.find('\n', i); i = n if j < 0 else j + 1; continue
        if c == '/' and i + 1 < n and src[i + 1] == '*':
            j = src.find('*/', i + 2); i = n if j < 0 else j + 2; continue
        if c == '/':
            prev = _prev_nonws(src, i)
            if prev == '' or prev in _REGEX_PREV:
                i = _skip_regex(src, i); continue
        if c in ('"', "'", '`'):
            q = c; start = i; i += 1
            buf, has_interp = [], False
            while i < n:
                ch = src[i]
                if ch == '\\' and i + 1 < n:
                    buf.append(src[i + 1]); i += 2; continue
                if ch == q:
                    i += 1
                    yield (start, i, q, ''.join(buf), has_interp); break
                if q == '`' and ch == '$' and i + 1 < n and src[i + 1] == '{':
                    has_interp = True; depth = 1; i += 2
                    while i < n and depth:
                        if src[i] == '{': depth += 1
                        elif src[i] == '}': depth -= 1
                        i += 1
                    buf.append('${...}'); continue
                buf.append(ch); i += 1
            else: break
            continue
        i += 1


def js_escape(s: str, q: str = "'") -> str:
    out = s.replace('\\', '\\\\').replace(q, '\\' + q)
    return out.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')


def _inside_t_call(src: str, pos: int) -> bool:
    """True if pos sits inside `(...)` whose callee is _t / i18n.t / SXFI18n.t."""
    i = pos - 1; depth = 0; limit = max(0, pos - 600)
    while i >= limit:
        ch = src[i]
        if ch in ('"', "'", '`'):
            q = ch; j = i - 1
            while j >= 0:
                if src[j] == q and (j == 0 or src[j - 1] != '\\'): break
                j -= 1
            i = j - 1; continue
        if ch == ')':
            depth += 1; i -= 1; continue
        if ch == '(':
            if depth > 0:
                depth -= 1; i -= 1; continue
            j = i - 1
            while j >= 0 and src[j] in ' \t\n\r': j -= 1
            k = j
            while k >= 0 and (src[k].isalnum() or src[k] in '_.$'): k -= 1
            ident = src[k + 1:j + 1]
            return ident in ('_t', 'i18n.t', 'SXFI18n.t')
        i -= 1
    return False


def find_unwrapped_in_js(src: str):
    for start, end, q, body, has_interp in iter_js_strings(src):
        if not needs_translation(body):     continue
        if body.strip() in SKIP_EXACT:      continue
        if has_interp:                       continue
        if len(body) > 180 or len(body) < 2: continue
        if any(bad in body for bad in ('\n', '\r', '<', '>', '&#', '&amp;', '${')):
            continue
        head = body.lstrip()
        if not head or not (head[0].isalpha() or head[0].isdigit()
                            or head[0] in '"\'(¡¿“„«…→•·'):
            continue
        if _inside_t_call(src, start):       continue
        yield start, end, body


# ============================================================================
# HTML scanner / wrapper
# ============================================================================
SCRIPT_BLOCK_RE = re.compile(r'<(script|style)\b[^>]*>.*?</\1>', re.DOTALL | re.IGNORECASE)

# Open-tag with simple text content: <TAG ...>TEXT</TAG>  (no nested tags)
TAG_TEXT_RE = re.compile(
    r'(<([a-zA-Z][\w:-]*)\b([^>]*)>)([^<>{}]*?)(</\2\s*>)',
    re.DOTALL,
)
ATTR_TR_RE = re.compile(
    r'\b(title|placeholder|alt|aria-label|content)\s*=\s*"([^"]*)"',
)


def _mask_blocks(src: str) -> str:
    """Replace <script>/<style> blocks with whitespace of equal length so that
    line numbers and byte offsets stay stable."""
    def _repl(m):
        s = m.group(0)
        return re.sub(r'[^\n]', ' ', s)
    return SCRIPT_BLOCK_RE.sub(_repl, src)


def _line_of(src: str, idx: int) -> int:
    return src.count('\n', 0, idx) + 1


def find_unwrapped_in_html(src: str):
    """Yield ('text'|'attr', span, payload) for each unwrapped TR slot.
       text: payload = (open_tag_start, open_tag_end, text, full_match)
       attr: payload = (tag_start, tag_end, attr_name, value)
    """
    masked = _mask_blocks(src)

    # text-content slots
    for m in TAG_TEXT_RE.finditer(masked):
        open_tag = m.group(1)
        attrs    = m.group(3)
        text     = m.group(4)
        # skip already-wrapped tags
        if 'data-i18n' in open_tag:
            continue
        # skip Jinja expressions inside text
        if '{{' in text or '{%' in text:
            continue
        stripped = text.strip()
        if not stripped or len(stripped) > 200:
            continue
        if not needs_translation(stripped):
            continue
        # skip pure brand
        if stripped in BRANDS:
            continue
        yield 'text', (m.start(), m.end()), {
            'open_start': m.start(1), 'open_end': m.end(1),
            'text': stripped, 'inner_start': m.start(4), 'inner_end': m.end(4),
        }

    # attribute slots — find tag start, attr value
    for m in ATTR_TR_RE.finditer(masked):
        attr_name = m.group(1); val = m.group(2)
        if not val.strip() or not needs_translation(val):
            continue
        # locate enclosing tag
        tag_start = src.rfind('<', 0, m.start())
        tag_end   = src.find('>', m.start())
        if tag_start < 0 or tag_end < 0:
            continue
        tag_src = src[tag_start:tag_end + 1]
        # skip if same attr already in data-i18n-attr
        if 'data-i18n-attr' in tag_src and re.search(rf'\b{attr_name}:', tag_src):
            continue
        yield 'attr', (m.start(), m.end()), {
            'tag_start': tag_start, 'tag_end': tag_end + 1,
            'attr': attr_name, 'value': val,
        }


# ============================================================================
# Master CSV I/O
# ============================================================================
def load_master() -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    if not os.path.exists(MASTER):
        return rows, list(FIELDS)
    with open(MASTER, encoding='utf-8') as fh:
        r = csv.DictReader(fh)
        fields = r.fieldnames or list(FIELDS)
        if 'file_refs' not in fields:
            fields = ['key', 'file_refs'] + [f for f in fields if f not in ('key',)]
        for row in r:
            row.setdefault('file_refs', '')
            rows.append(row)
    return rows, fields


def save_master(rows: list[dict], fields: list[str]):
    rows_sorted = sorted(rows, key=lambda r: r['key'])
    with open(MASTER, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=fields, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for r in rows_sorted:
            w.writerow({f: r.get(f, '') for f in fields})


def _add_ref(row: dict, ref: str):
    cur = (row.get('file_refs') or '').strip()
    parts = [p for p in cur.split(';') if p]
    if ref not in parts:
        parts.append(ref)
    row['file_refs'] = ';'.join(parts)


# ============================================================================
# Main
# ============================================================================
def _ensure_key(text: str, prefix: str, by_tr_text: dict, by_key: dict,
                used_keys: set, fields: list[str], new_rows: list[dict]) -> dict:
    if text in by_tr_text:
        return by_key[by_tr_text[text]]
    key = _make_key(prefix, text, used_keys)
    used_keys.add(key)
    row = {f: '' for f in fields}
    row['key'] = key
    row['tr']  = text
    row['file_refs'] = ''
    by_key[key] = row
    by_tr_text[text] = key
    new_rows.append(row)
    return row


def main():
    apply = '--apply' in sys.argv
    rows, fields = load_master()
    by_key      = {r['key']: r for r in rows}
    by_tr_text  = {r.get('tr', ''): r['key'] for r in rows if r.get('tr')}
    used_keys   = set(by_key)
    new_rows: list[dict] = []
    file_summaries = []

    # ------- JS pass --------------------------------------------------------
    for rel, prefix in JS_TARGETS:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            file_summaries.append((rel, 0, 0)); continue
        src = open(path, encoding='utf-8').read()
        finds = list(find_unwrapped_in_js(src))
        if not finds:
            file_summaries.append((rel, 0, 0)); continue
        new_src = src; replaced = 0; new_for_file = 0
        for start, end, body in sorted(finds, key=lambda x: x[0], reverse=True):
            row = _ensure_key(body, prefix, by_tr_text, by_key,
                              used_keys, fields, new_rows)
            if row in new_rows: new_for_file += 1
            _add_ref(row, f'{rel}:{src.count(chr(10), 0, start) + 1}')
            esc_key  = js_escape(row['key'], "'")
            esc_body = js_escape(body, "'")
            replacement = f"_t('{esc_key}', '{esc_body}')"
            # Add leading space if previous char would otherwise glue to _t
            prev_ch = new_src[start - 1] if start > 0 else ''
            if _IDENT_TAIL.match(prev_ch):
                replacement = ' ' + replacement
            new_src = new_src[:start] + replacement + new_src[end:]
            replaced += 1
        file_summaries.append((rel, replaced, new_for_file))
        if apply:
            with open(path, 'w', encoding='utf-8') as fh: fh.write(new_src)

    # ------- HTML pass ------------------------------------------------------
    for rel, prefix in HTML_TARGETS:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            file_summaries.append((rel, 0, 0)); continue
        src = open(path, encoding='utf-8').read()
        finds = list(find_unwrapped_in_html(src))
        if not finds:
            file_summaries.append((rel, 0, 0)); continue

        # Group all edits by tag-open position; we may inject both
        # data-i18n and data-i18n-attr into the same tag.
        # An "edit" is one of:
        #   ('text', open_start, open_end, key, fallback)
        #   ('attr', tag_start, tag_end, attr_name, key)
        edits = []
        replaced = 0; new_for_file = 0
        for kind, span, p in finds:
            if kind == 'text':
                row = _ensure_key(p['text'], prefix, by_tr_text, by_key,
                                  used_keys, fields, new_rows)
                if row in new_rows: new_for_file += 1
                _add_ref(row, f"{rel}:{_line_of(src, p['open_start'])}")
                edits.append(('text', p['open_start'], p['open_end'],
                              row['key'], p['text']))
                replaced += 1
            else:
                row = _ensure_key(p['value'], prefix, by_tr_text, by_key,
                                  used_keys, fields, new_rows)
                if row in new_rows: new_for_file += 1
                _add_ref(row, f"{rel}:{_line_of(src, p['tag_start'])}")
                edits.append(('attr', p['tag_start'], p['tag_end'],
                              p['attr'], row['key']))
                replaced += 1

        # Apply edits right-to-left, merging text+attr that touch the same tag
        # (we keep them simple: each edit independently rewrites the open tag).
        edits.sort(key=lambda e: e[1], reverse=True)
        new_src = src
        for e in edits:
            if e[0] == 'text':
                _kind, ostart, oend, key, _fb = e
                tag = new_src[ostart:oend]
                if 'data-i18n=' in tag:
                    continue
                # inject before final '>'
                injected = tag[:-1].rstrip() + f' data-i18n="{key}">'
                new_src = new_src[:ostart] + injected + new_src[oend:]
            else:
                _kind, tstart, tend, attr_name, key = e
                tag = new_src[tstart:tend]
                if 'data-i18n-attr=' in tag:
                    # extend existing
                    tag2 = re.sub(
                        r'data-i18n-attr="([^"]*)"',
                        lambda m: f'data-i18n-attr="{m.group(1).rstrip(";")};{attr_name}:{key}"',
                        tag, count=1,
                    )
                else:
                    tag2 = tag[:-1].rstrip() + f' data-i18n-attr="{attr_name}:{key}">'
                new_src = new_src[:tstart] + tag2 + new_src[tend:]

        file_summaries.append((rel, replaced, new_for_file))
        if apply:
            with open(path, 'w', encoding='utf-8') as fh: fh.write(new_src)

    total = sum(n for _, n, _ in file_summaries)
    print('=' * 64)
    print(f'i18n WRAP {"APPLY" if apply else "DRY-RUN"}')
    print('=' * 64)
    for rel, n, k in file_summaries:
        if n == 0 and k == 0: continue
        print(f'  {rel:<46} {n:>4} replacements  ({k} new keys)')
    print(f'  TOTAL                                          {total:>4} replacements  ({len(new_rows)} new keys)')

    if apply and new_rows:
        rows.extend(new_rows)
        save_master(rows, fields)
        print(f'master: appended {len(new_rows)} new keys → {MASTER}')
    elif apply:
        # still resave if we updated file_refs on existing rows
        save_master(rows, fields)
        print(f'master: refreshed file_refs → {MASTER}')


if __name__ == '__main__':
    main()
