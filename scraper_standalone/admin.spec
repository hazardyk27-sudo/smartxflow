# -*- mode: python ; coding: utf-8 -*-
# SmartXFlow Admin Panel v1.25 - PyInstaller Spec
# Web Admin (pywebview + Flask) + Background Scraper

import os
import sys
import certifi

block_cipher = None

# Get certifi path
certifi_path = os.path.dirname(certifi.where())

a = Analysis(
    ['scraper_admin.py'],
    pathex=['.', '..'],
    binaries=[],
    datas=[
        ('config.json', '.'),
        ('BUILD_INFO.txt', '.'),
        ('standalone_scraper.py', '.'),
        ('alarm_calculator.py', '.'),
        (certifi_path, 'certifi'),
        # Flask app and dependencies
        ('../app.py', '.'),
        ('../templates', 'templates'),
        ('../static', 'static'),
        ('../services', 'services'),
        ('../core', 'core'),
    ],
    hiddenimports=[
        # Scraper modules
        'standalone_scraper',
        'alarm_calculator',
        # Flask & Web
        'flask',
        'flask.json',
        'jinja2',
        'werkzeug',
        'markupsafe',
        'itsdangerous',
        'click',
        # Pywebview
        'webview',
        'webview.platforms.edgechromium',
        'clr_loader',
        'pythonnet',
        # Database & HTTP
        'requests',
        'httpx',
        'bs4',
        'pytz',
        'certifi',
        # Standard
        'json',
        'threading',
        'socket',
        'logging',
        'datetime',
        # Windows
        'ctypes',
        'winreg',
        # Tkinter for setup dialog
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SmartXFlowAdminV1.25',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # windowed mode - no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
