"""Frozen/native smoke check for the new menu and a real local file chain."""
import json
from pathlib import Path
import tempfile

from PIL import Image,ImageSequence
from PySide6.QtCore import QPoint,Qt,QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from .branch_menu import BranchMenu
from .branch_model import Step
from .branch_pipeline import execute
from .branch_storage import data_dir


def selftest():
    from .branch_fonts import register
    register()
    app=QApplication.instance()
    assert app is not None
    checks=[]
    with tempfile.TemporaryDirectory(prefix='branch-smoke-',dir=data_dir()) as folder:
        paths=[]
        for index,color in [(10,'blue'),(1,'red'),(2,'green')]:
            path=Path(folder)/f'frame{index}.png';Image.new('RGB',(160,100),color).save(path);paths.append(str(path))
        output=execute(paths,[Step('crop',1.),Step('resize',64),Step('animate',10)])[0]
        with Image.open(output) as image:
            assert image.size==(64,64) and image.n_frames==3
            colors=[frame.convert('RGB').getpixel((20,20)) for frame in ImageSequence.Iterator(image)]
            assert colors==[(255,0,0),(0,128,0),(0,0,255)]
        checks.append('real ordered GIF pipeline')
        menu=BranchMenu(lambda _: {},lambda _:'smoke')
        menu.popup(QPoint(600,400),paths)
        menu.frame.stop()
        app.processEvents()
        assert menu.isVisible() and len(menu.level.choices)==2
        assert menu.grab().save(str(data_dir()/'menu-light.png'))
        menu.keyPressEvent(QKeyEvent(QEvent.KeyPress,Qt.Key_2,Qt.NoModifier))
        assert menu.level.label=='Обработать'
        menu.navigate(0);menu.navigate(0)
        assert menu.steps==(Step('resize',640),)
        app.processEvents()
        assert menu.grab().save(str(data_dir()/'menu-branches.png'))
        menu.back();assert menu.steps==()
        menu.close_menu();menu.deleteLater();app.processEvents()
        checks+=['visible root','keyboard branch','plan staging','snapshot backtracking']
    (data_dir()/'branch-selftest.json').write_text(json.dumps({'checks':checks,'passed':len(checks)},ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Branch self-test: {len(checks)} checks passed',flush=True)
    return 0
