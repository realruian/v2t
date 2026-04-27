"""py2app config — builds V2T.app

Usage:
    bash build_app.sh           # alias mode (fast, links to project dir)
    bash build_app.sh standalone # full standalone bundle (slow, large)
"""
from setuptools import setup
from pathlib import Path

HERE = Path(__file__).parent.resolve()

APP = ['app.py']

# Bundle the web/ directory so the .app finds index.html via __file__.
DATA_FILES = [
    ('web', [
        str(HERE / 'web' / 'index.html'),
        str(HERE / 'web' / 'style.css'),
        str(HERE / 'web' / 'app.js'),
    ]),
]

PLIST = {
    'CFBundleName': 'V2T',
    'CFBundleDisplayName': 'V2T',
    'CFBundleIdentifier': 'com.v2t.app',
    'CFBundleVersion': '1.0.0',
    'CFBundleShortVersionString': '1.0.0',
    'CFBundleIconFile': 'icon.icns',
    'LSMinimumSystemVersion': '11.0',
    'LSMultipleInstancesProhibited': True,
    'NSHighResolutionCapable': True,
    'NSHumanReadableCopyright': 'V2T — local transcription',
    'NSAppleEventsUsageDescription': 'V2T 在转写完成时发送系统通知。',
}

OPTIONS = {
    'argv_emulation': False,
    'plist': PLIST,
    'iconfile': str(HERE / 'icon.icns'),
    'packages': ['webview', 'faster_whisper'],
    'includes': ['transcribe'],
    'excludes': ['tkinter'],
}

setup(
    name='V2T',
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
