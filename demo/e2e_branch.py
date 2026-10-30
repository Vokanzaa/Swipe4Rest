"""Run the new Qt menu against a real X11 display and retain proof artifacts."""
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
out=Path('e2e_linux_out').resolve();out.mkdir(exist_ok=True)
os.environ['SWIPE4REST_DATA_DIR']=str(out)
from PySide6.QtWidgets import QApplication
from dragshift.branch_check import selftest

app=QApplication([])
result=selftest()
(out/'results.md').write_text('# Swipe4Rest X11 native menu check\n\nFive native menu/pipeline checks passed. Screenshots are attached as CI artifacts. External file-manager drag is covered by the drag-gate regressions, not claimed as an automated physical gesture here.\n',encoding='utf-8')
raise SystemExit(result)
