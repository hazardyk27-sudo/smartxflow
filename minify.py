#!/usr/bin/env python3
"""Minify CSS and JS files. Run after editing .src files."""
import csscompressor
import rjsmin

pairs = [
    ('static/css/style.css.src', 'static/css/style.css'),
    ('static/css/alert_band.css.src', 'static/css/alert_band.css'),
    ('static/js/app.js.src', 'static/js/app.js'),
    ('static/js/inline.js.src', 'static/js/inline.js'),
]

for src, dest in pairs:
    try:
        with open(src, 'r') as f:
            raw = f.read()
        if src.endswith('.css.src'):
            minified = csscompressor.compress(raw)
        else:
            minified = rjsmin.jsmin(raw)
        with open(dest, 'w') as f:
            f.write(minified)
        saving = (1 - len(minified)/len(raw)) * 100
        print(f'{dest}: {len(raw)//1024}KB -> {len(minified)//1024}KB ({saving:.0f}%)')
    except FileNotFoundError:
        print(f'SKIP: {src} not found')
