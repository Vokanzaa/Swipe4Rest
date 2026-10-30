"""Application-local OFL font fallback, including Cyrillic in offscreen builds."""
from pathlib import Path
from PySide6.QtGui import QFontDatabase

_registered=False


def register():
    global _registered
    if _registered:return
    path=Path(__file__).with_name('assets')/'fonts'/'NotoSans.ttf'
    if path.is_file():
        if QFontDatabase.addApplicationFont(str(path))<0:
            raise RuntimeError('Could not load the bundled Noto Sans font.')
    from .util import _FONT_FAMILY
    _FONT_FAMILY.clear()
    _registered=True
