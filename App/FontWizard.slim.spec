# -*- mode: python ; coding: utf-8 -*-
#
# Conservative slim build for Font Wizard 6.0.
# - PySide6-Essentials only (no Addons/PDF/WebEngine)
# - README screenshots are not bundled into the EXE
# - brotli is not bundled (the app does not generate WOFF2)
# - Qt QML/Quick/PDF/VirtualKeyboard/OpenGL wrappers are not bundled
# - opengl32sw.dll is intentionally KEPT (rendering safety net)

import os

a = Analysis(
    ['src/main.py'],
    pathex=[],
    binaries=[],
    datas=[('src/assets', 'assets')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['brotli'],
    noarchive=False,
    optimize=0,
)

# Screenshots are README-only; never loaded by the application.
a.datas = [
    d for d in a.datas
    if not d[0].replace('\\', '/').startswith('assets/screenshots/')
]

# Safety net for Qt libraries that the app never imports.
_drop_prefixes = (
    'qt6qml',
    'qt6quick',
    'qt6pdf',
    'qt6virtualkeyboard',
    'qt6opengl',
    'qpdf',
    'qtvirtualkeyboard',
    '_brotli',
)
a.binaries = [
    b for b in a.binaries
    if not any(os.path.basename(b[0]).lower().startswith(p) for p in _drop_prefixes)
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='FontWizard',
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
    version='fontwizard_version_info.txt',
    uac_admin=True,
    icon=['src/assets/font-wizard.ico'],
    manifest='fontwizard.manifest',
)
