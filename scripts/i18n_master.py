#!/usr/bin/env python3
"""
Master i18n catalogue manager for SmartXFlow.

The single source of truth is `static/i18n/_master.csv` with columns:
    key, tr, en, de, fr, nl, it, es

Subcommands:
    sync    Read static/i18n/{tr,en,de,fr,nl,it,es}.json and write _master.csv
            (one row per leaf key, preserving every existing translation).
    build   Read _master.csv and (re)generate the seven per-language JSON files.
    add     Add new key(s) to the master CSV interactively / from stdin
            (skipped here — done by direct CSV edits or apply_phaseN scripts).
    stats   Print coverage stats: how many keys, how many empty per language.

The CSV is sorted by key for stable diffs.
"""
from __future__ import annotations
import os, sys, csv, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
I18N_DIR = os.path.join(ROOT, 'static/i18n')
MASTER = os.path.join(I18N_DIR, '_master.csv')
LANGS = ['tr', 'en', 'de', 'fr', 'nl', 'it', 'es']


def _flatten(obj, prefix='') -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            sub = f'{prefix}.{k}' if prefix else k
            out.update(_flatten(v, sub))
    else:
        out[prefix] = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    return out


def _nest(flat: dict[str, str]) -> dict:
    root: dict = {}
    for key, val in flat.items():
        parts = key.split('.')
        cur = root
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
            if not isinstance(cur, dict):
                # collision: a leaf and a branch share a path → keep the leaf untouched
                return _nest({k: v for k, v in flat.items() if k != key})
        cur[parts[-1]] = val
    return root


def cmd_sync():
    """Build _master.csv from existing per-language JSON files."""
    flats: dict[str, dict[str, str]] = {}
    for lang in LANGS:
        fp = os.path.join(I18N_DIR, f'{lang}.json')
        if not os.path.exists(fp):
            flats[lang] = {}
            continue
        flats[lang] = _flatten(json.load(open(fp, encoding='utf-8')))

    # union of all keys
    all_keys = set()
    for lang in LANGS:
        all_keys.update(flats[lang].keys())

    rows = []
    for key in sorted(all_keys):
        rows.append({lang: flats[lang].get(key, '') for lang in LANGS} | {'key': key})

    with open(MASTER, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['key'] + LANGS, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f'sync: wrote {len(rows)} rows → {MASTER}')


def cmd_build():
    """Build per-language JSON files from _master.csv."""
    if not os.path.exists(MASTER):
        sys.exit(f'master csv not found: {MASTER}')
    flats: dict[str, dict[str, str]] = {lang: {} for lang in LANGS}
    with open(MASTER, encoding='utf-8') as fh:
        for row in csv.DictReader(fh):
            key = row['key'].strip()
            if not key:
                continue
            for lang in LANGS:
                val = row.get(lang, '') or ''
                if not val and lang != 'tr':
                    val = row.get('tr', '')  # fallback: TR
                if val:
                    flats[lang][key] = val
    for lang in LANGS:
        nested = _nest(flats[lang])
        out = os.path.join(I18N_DIR, f'{lang}.json')
        with open(out, 'w', encoding='utf-8') as fh:
            json.dump(nested, fh, ensure_ascii=False, indent=2, sort_keys=True)
        print(f'build: wrote {len(flats[lang])} keys → {out}')


def cmd_stats():
    if not os.path.exists(MASTER):
        sys.exit(f'master csv not found: {MASTER}')
    counts = {lang: 0 for lang in LANGS}
    empty = {lang: 0 for lang in LANGS}
    total = 0
    with open(MASTER, encoding='utf-8') as fh:
        for row in csv.DictReader(fh):
            total += 1
            for lang in LANGS:
                v = (row.get(lang) or '').strip()
                if v:
                    counts[lang] += 1
                else:
                    empty[lang] += 1
    print(f'master: {total} keys')
    for lang in LANGS:
        cov = counts[lang] / total * 100 if total else 0
        print(f'  {lang}: {counts[lang]:>4} translated, {empty[lang]:>3} empty  ({cov:5.1f}%)')


COMMANDS = {'sync': cmd_sync, 'build': cmd_build, 'stats': cmd_stats}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f'usage: {sys.argv[0]} {{{"|".join(COMMANDS)}}}')
        sys.exit(2)
    COMMANDS[sys.argv[1]]()


if __name__ == '__main__':
    main()
