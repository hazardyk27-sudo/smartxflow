# -*- mode: python ; coding: utf-8 -*-
# SmartXFlow Desktop V1.01 - PyInstaller Spec
# pywebview + Flask backend

import os
import sys
import certifi

block_cipher = None

certifi_path = os.path.dirname(certifi.where())

a = Analysis(
    ['desktop_app.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('smartxflow.ico', '.'),
        (certifi_path, 'certifi'),
        ('app.py', '.'),
        ('templates', 'templates'),
        ('static', 'static'),
        ('services', 'services'),
        ('core', 'core'),
    ],
    hiddenimports=[
        'flask',
        'flask.json',
        'jinja2',
        'werkzeug',
        'markupsafe',
        'itsdangerous',
        'click',
        'webview',
        'webview.platforms.edgechromium',
        'clr_loader',
        'pythonnet',
        'requests',
        'httpx',
        'bs4',
        'pytz',
        'certifi',
        'json',
        'threading',
        'socket',
        'logging',
        'datetime',
        'ctypes',
        'winreg',
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
    name='SmartXFlowDesktopV1.01',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='smartxflow.ico',
)
