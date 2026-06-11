import platform
from PyInstaller.utils.hooks import collect_data_files

_win = platform.system() == "Windows"
_ffmpeg = "ffmpeg.exe" if _win else "ffmpeg"

a = Analysis(
    ["src/photos_categorizer/main.py"],
    pathex=["src"],
    binaries=[
        (_ffmpeg, "."),  # static ffmpeg placed next to main.py at build time
    ],
    datas=[
        ("src/photos_categorizer/ui/style.qss", "ui"),
        *collect_data_files("open_clip"),  # BPE vocab + config files
    ],
    hiddenimports=[
        "PySide6.QtSvg",
        "PySide6.QtXml",
        "PySide6.QtPrintSupport",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["runtime-hook-ffmpeg.py"],
    excludes=[
        "tkinter", "_tkinter",
        "matplotlib", "notebook", "IPython",
        "torch.distributed", "torch.testing", "torch.utils.tensorboard",
        "torchaudio",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="photos-categorizer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX causes false-positives with some AV scanners
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
