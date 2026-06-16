# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules  # <-- Add this import

block_cipher = None

# Automatically discover and collect all submodules for the main packages
hidden_imports = [
    'sqlite3',
    'json',
    're',
    'requests',
    'hashlib',
    'runpy',
    'datetime',
    'time',
    'random',
    'keyboard',
    'groq',
    'pyperclip'
] + collect_submodules('keyboard') + collect_submodules('groq') + collect_submodules('pyperclip')

excluded_modules = [
    'tkinter', 'unittest', 'pydoc',
    'matplotlib', 'numpy', 'pandas', 'scipy', 'PIL', 'cv2',
    'PyQt6.QtWebEngine', 'PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngineWidgets',
    'PyQt6.QtQml', 'PyQt6.QtQuick', 'PyQt6.QtSql',
    'PyQt6.QtTest', 'PyQt6.QtBluetooth', 'PyQt6.QtDBus',
    'PyQt6.QtDesigner', 'PyQt6.QtHelp', 'PyQt6.QtMultimedia',
    'PyQt6.QtMultimediaWidgets', 'PyQt6.QtNetworkAuth', 'PyQt6.QtNfc',
    'PyQt6.QtOpenGL', 'PyQt6.QtOpenGLWidgets', 'PyQt6.QtPdf',
    'PyQt6.QtPdfWidgets', 'PyQt6.QtPositioning', 'PyQt6.QtPrintSupport',
    'PyQt6.QtQuick3D', 'PyQt6.QtQuickWidgets', 'PyQt6.QtRemoteObjects',
    'PyQt6.QtSensors', 'PyQt6.QtSerialPort', 'PyQt6.QtSpatialAudio',
    'PyQt6.QtSvg', 'PyQt6.QtSvgWidgets', 'PyQt6.QtTextToSpeech',
    'PyQt6.QtWebChannel', 'PyQt6.QtWebSockets', 'PyQt6.Qt3DAnimation',
    'PyQt6.Qt3DCore', 'PyQt6.Qt3DExtras', 'PyQt6.Qt3DInput',
    'PyQt6.Qt3DLogic', 'PyQt6.Qt3DRender'
]

a = Analysis(
    ['vocab_loader.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_modules,
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
    name='VocabMaster',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,  
    upx=True,    # UPX compression is enabled here
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False, 
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='vocabmasterlogo.ico' # <--- ADD YOUR EXACT ICON FILENAME HERE
)