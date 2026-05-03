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
# ASCII-Turkish words (no diacritics) commonly used in this codebase.
# Reviewer-required: catch literals like 'Toplam', 'Kaybetti', 'Tumu'.
ASCII_TR_WORDS = {
    # Existing
    'toplam', 'kazanan', 'kaybeden', 'kaybetti', 'kazandi', 'analizci',
    'analist', 'oran', 'para', 'akis', 'tumu', 'buyuk', 'hacim', 'soku',
    'lider', 'degisti', 'yukleniyor', 'kisi', 'takip', 'ediyor', 'mac',
    'lig', 'tarih', 'snapshot', 'ev', 'sahibi', 'deplasman', 'beraberlik',
    'gelen', 'sonuc', 'guven', 'iade', 'iptal', 'ortalama', 'esik', 'yok',
    'aktif', 'sinyal', 'onceki', 'sonraki', 'goster', 'gizle', 'yeni',
    'eski', 'sonra', 'once', 'saat', 'dakika', 'gun', 'hafta', 'ay', 'yil',
    # UI vocabulary expansion (rev6)
    'ara', 'arama', 'aranan', 'alarm', 'alarmlar', 'favori', 'favoriler',
    'kaydet', 'kaydedildi', 'sil', 'silindi', 'ayar', 'ayarlar', 'bildirim',
    'bildirimler', 'hesap', 'profil', 'cikis', 'giris', 'gonder', 'gonderildi',
    'yardim', 'hakkinda', 'tarihce', 'gecmis', 'paylas', 'indir', 'yukle',
    'kapat', 'baslat', 'bitir', 'devam', 'geri', 'ileri', 'bul', 'listele',
    'filtrele', 'filtreler', 'sirala', 'sec', 'secili', 'temizle', 'yenile',
    'guncelle', 'guncellendi', 'ekle', 'eklendi', 'kaldir', 'kaldirildi',
    'duzenle', 'goruntule', 'aciklama', 'baslik', 'olustur', 'olusturuldu',
    'yorum', 'yorumlar', 'begeni', 'begeniler', 'mesaj', 'mesajlar',
    'bildiri', 'duyuru', 'duyurular', 'haber', 'haberler', 'rapor', 'raporlar',
    'istatistik', 'istatistikler', 'detay', 'detaylar', 'ozet', 'ozetler',
    'liste', 'listeler', 'kategori', 'kategoriler', 'paket', 'paketler',
    'urun', 'urunler', 'fiyat', 'fiyatlar', 'odeme', 'odemeler', 'fatura',
    'faturalar', 'siparis', 'siparisler', 'sepet', 'kullanici', 'kullanicilar',
    'uye', 'uyelik', 'uyelikler', 'kayit', 'kayitlar', 'oturum', 'parola',
    'sifre', 'eposta', 'telefon', 'adres', 'sehir', 'ulke', 'tum', 'bos',
    'hata', 'hatalar', 'basarili', 'basarisiz', 'bekleniyor', 'tamamlandi',
    'islem', 'islemler', 'durum', 'turu', 'tur', 'sayfa', 'sayfalar',
    'oncelik', 'oncelikli', 'yuksek', 'dusuk', 'orta', 'normal', 'kritik',
    'tehlikeli', 'guvenli', 'belirsiz', 'tahmin', 'tahminler', 'sonuclar',
    'baglanti', 'bagli', 'baglaniyor', 'koparildi', 'tekrar', 'tekrarla',
    'kapali', 'acik', 'cevrimici', 'cevrimdisi', 'erisim', 'engellendi',
    'izinli', 'reddedildi', 'onaylandi', 'beklemede', 'tamamlanan',
    'kalan', 'gecen', 'kalmis', 'gecmiyor', 'doldur', 'dolu', 'mevcut',
    'mevcutlar', 'mevcutsuz', 'baska', 'diger', 'digerleri', 'oran', 'orani',
    'oranlar', 'oranlari', 'oransal', 'orandaki',
}
ASCII_TR_RE = re.compile(
    r'\b(?:' + '|'.join(sorted(ASCII_TR_WORDS, key=len, reverse=True)) + r')\b',
    re.IGNORECASE,
)
# Heuristic: standalone Title-cased words ending in distinctive TR suffixes.
# Catches inflected forms not in the static word list (e.g. "Maçlar", "Periyot").
# Only flags when full text is short label-like (<=40 chars, no obvious English).
_TR_SUFFIX_RE = re.compile(
    r'^\s*[A-ZÇĞİÖŞÜ][a-zçğıöşü]{1,20}'
    r'(?:lar|ler|ları|leri|larım|lerim|ım|im|um|üm|sın|sin|sun|sün'
    r'|dı|di|du|dü|tı|ti|tu|tü|mış|miş|muş|müş'
    r'|ıyor|iyor|uyor|üyor|acak|ecek|mak|mek|nın|nin|nun|nün'
    r'|dan|den|tan|ten|nda|nde|ndan|nden)\s*$',
)
_EN_COMMON = {  # words that look TR-suffixed but are English
    'order', 'under', 'over', 'header', 'footer', 'leader', 'banner',
    'tracker', 'manager', 'filter', 'counter', 'pointer', 'partner',
    'after', 'before', 'enter', 'render', 'border', 'corner', 'matter',
    'monster', 'silver', 'better', 'master', 'monitor', 'iframe',
    'live', 'time', 'data', 'team', 'home', 'away', 'name', 'date',
    'cancel', 'panel', 'level', 'goal', 'final', 'total', 'normal',
}
def _looks_turkish_suffix(text: str) -> bool:
    s = text.strip()
    if not (3 <= len(s) <= 40): return False
    if s.lower() in _EN_COMMON: return False
    return bool(_TR_SUFFIX_RE.match(s))
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
    """TR-diacritic OR ASCII-TR-word OR TR-suffix heuristic."""
    if any(c in TR_CHARS for c in text):
        return True
    if ASCII_TR_RE.search(text):
        return True
    if _looks_turkish_suffix(text):
        return True
    return False


_CSS_IDENT_RE = re.compile(r'^[a-z][a-z0-9_-]*$')
_URL_RE = re.compile(r'^https?://|^/api/|^/static/')
_ESCAPE_LEFTOVER_RE = re.compile(r'u[0-9a-f]{4}')  # broken \u escapes after str scan
_CSS_SELECTOR_RE = re.compile(r'^\s*[.#\[][\w\-\[\]"\'*=:>+~,\s.#]+$')  # CSS selectors
_CAMEL_IDENT_RE = re.compile(r'^[a-z][a-zA-Z0-9_]*$')  # JS identifiers like 'countMim'

def needs_translation(text: str) -> bool:
    """True if the text actually contains TR letters AFTER stripping brands."""
    if not has_tr(text):
        return False
    s = text.strip()
    # Filter false positives
    if _CSS_IDENT_RE.match(s):  # 'moneyway-oran', 'dropping-para'
        return False
    if _URL_RE.match(s):  # API paths, full URLs
        return False
    if _ESCAPE_LEFTOVER_RE.search(s):  # 'saat u00f6nce' = broken \u00f6 fragment
        return False
    if _CSS_SELECTOR_RE.match(s):  # '.mobile-alarm-btn[onclick*="moves"]'
        return False
    if _CAMEL_IDENT_RE.match(s):  # 'countMim' — JS identifier, not user text
        return False
    if "_t('" in s or '_t("' in s:  # already-wrapped fragment leaking through
        return False
    stripped = _BRANDS_RE.sub(' ', text)
    return has_tr(stripped)


# Extract user-visible text segments from an HTML-fragment string literal
# (e.g. `'<span>X</span>kişi takip ediyor'`).  Returns list of segment strings.
_TAG_RE = re.compile(r'<[^>]*>|&[a-zA-Z#0-9]+;|\$\{\.\.\.\}')

def _html_text_segments(body: str) -> list[str]:
    parts = _TAG_RE.split(body)
    return [p.strip() for p in parts if p and p.strip()]


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


# DOM-aware text-node finder.  Uses html.parser to walk the tree and yield
# (line_number, text) for every text node whose nearest ancestor element does
# NOT carry a data-i18n / data-i18n-html attribute (i.e. still untranslated).
# Skips <script>/<style>/<svg> contents and Jinja `{{ ... }}` / `{% ... %}`.
from html.parser import HTMLParser as _HTMLParser

class _TextNodeFinder(_HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, bool]] = []  # (tag, has_i18n)
        self.skip_depth = 0
        self.results: list[tuple[int, str]] = []

    def _has_i18n(self, attrs):
        for k, _v in attrs:
            if k in ('data-i18n', 'data-i18n-html'):
                return True
        return False

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'svg'):
            self.skip_depth += 1
        has = self._has_i18n(attrs) or any(p[1] for p in self.stack)
        self.stack.append((tag, has))

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'svg') and self.skip_depth > 0:
            self.skip_depth -= 1
        # pop matching tag
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.skip_depth > 0:
            return
        if not data.strip():
            return
        # ancestor i18n?
        if any(p[1] for p in self.stack):
            return
        ln, _col = self.getpos()
        self.results.append((ln, data))


def _dom_text_nodes(src: str):
    p = _TextNodeFinder()
    try:
        p.feed(src)
        p.close()
    except Exception:
        pass
    return p.results


def scan_html(path: str) -> list[dict]:
    src = open(path, encoding='utf-8').read()
    masked = _mask_blocks(src)
    findings = []
    seen_keys = set()  # (line, text) — dedup between regex + DOM scanner
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
        key = (ln, stripped[:120])
        if key in seen_keys: continue
        seen_keys.add(key)
        findings.append({
            'file': path, 'line': ln, 'kind': 'html-text',
            'text': stripped[:200],
        })
    # DOM-aware scanner: catches text nodes inside elements with nested children
    # (e.g. `<a><svg>...</svg>TEXT</a>`) that the regex above misses.
    for ln, text in _dom_text_nodes(masked):
        stripped = text.strip()
        if not stripped or not needs_translation(stripped): continue
        if stripped in BRANDS: continue
        if '{{' in stripped or '{%' in stripped: continue
        key = (ln, stripped[:120])
        if key in seen_keys: continue
        seen_keys.add(key)
        findings.append({
            'file': path, 'line': ln, 'kind': 'html-text-nested',
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
_INDEXOF_RE = re.compile(r'\.\s*indexOf\s*\($')


def _inside_indexof_call(src: str, pos: int) -> bool:
    """Skip strings used as .indexOf('...') arguments — backwards-compat lookups."""
    i = pos - 1
    while i >= 0 and src[i] in ' \t':
        i -= 1
    j = i + 1
    return bool(_INDEXOF_RE.search(src[max(0, i - 40):j]))


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
        if _inside_indexof_call(src, start):
            continue
        # Bracket-prefixed log tags like '[AutoRefresh] foo' / '[Live] bar'
        if body.lstrip().startswith('[') and ']' in body[:40]:
            continue
        ln = src.count('\n', 0, start) + 1
        # Inline HTML fragments — extract user-visible text segments.
        if '<' in body or '>' in body or '&#' in body:
            for seg in _html_text_segments(body):
                if needs_translation(seg) and seg not in BRANDS:
                    findings.append({
                        'file': path, 'line': ln, 'kind': f'js-{q}-frag',
                        'text': seg[:200],
                    })
            continue
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
