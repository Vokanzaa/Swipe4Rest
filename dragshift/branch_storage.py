"""An independent portable profile; never write Swipe4Rest's registry/settings."""
import os
from pathlib import Path
import sys


def data_dir():
    override=os.environ.get('SWIPE4REST_DATA_DIR')
    if override:
        path=Path(override)
    elif not getattr(sys,'frozen',False):
        path=Path(__file__).resolve().parents[2]/'data'
    elif sys.platform=='win32':
        path=Path(sys.executable).parent/'data'
    elif sys.platform=='darwin':
        path=Path.home()/'Library'/'Application Support'/'Swipe4Rest'
    else:
        path=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local'/'share'))/'Swipe4Rest'
    path.mkdir(parents=True,exist_ok=True)
    return path
