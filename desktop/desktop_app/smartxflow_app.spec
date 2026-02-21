# -*- mode: python ; coding: utf-8 -*-
# SmartXFlow Desktop App - PyInstaller Spec

a = Analysis(
    ['smartxflow_app.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('config.json', '.'),
        ('app_icon.ico', '.'),
    ],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'requests',
        'json',
        'threading',
        'pytz',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SmartXFlowApp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app_icon.ico',
)
