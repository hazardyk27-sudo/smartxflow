# -*- mode: python ; coding: utf-8 -*-
# SmartXFlow Admin Panel PyInstaller Spec

import os
import sys
import certifi

block_cipher = None

# Get certifi path
certifi_path = os.path.dirname(certifi.where())

a = Analysis(
    ['scraper_admin.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('config.json', '.'),
        ('standalone_scraper.py', '.'),
        ('alarm_calculator.py', '.'),
        (certifi_path, 'certifi'),
    ],
    hiddenimports=[
        'standalone_scraper',
        'alarm_calculator',
        'tkinter',
        'tkinter.ttk',
        'tkinter.scrolledtext',
        'tkinter.messagebox',
        'requests',
        'bs4',
        'pytz',
        'certifi',
        'json',
        'threading',
        'queue',
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
    name='SmartXFlowAdmin',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # windowed mode
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
