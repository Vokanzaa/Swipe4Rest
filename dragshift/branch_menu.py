"""A branching marking menu: navigation builds a plan, explicit endpoints run it."""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
import time

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from . import glass
from .branch_gestures import GestureDetector, clamp_center, hit_sector, item_angles
from .branch_model import Context, Entry, FlowRequest, after, context_for, entries, step_text
from .i18n import tr
from .radial import Item
from .util import resolve_shortcuts, ui_family


@dataclass(frozen=True)
class Level:
    label: str
    choices: tuple[Entry, ...]
    center: tuple[float, float]
    steps: tuple
    incoming: float | None = None
    root: bool = False


LEGACY = {
    'image': ('Crop','Resize','Edit','Annotate','Redact','Add BG','Compress','Distort','Interlace','Metadata'),
    'video': ('Trim','Resize','Edit','Compress','Distort','Datamosh','Frame','Audio','Metadata'),
    'audio': ('Trim','Edit','Normalize','Fade','Compress','Reverse','Datamosh','Transition','Metadata'),
    'pdf': ('Protect','Metadata','Merge'), 'archive': ('Extract archive','Contents'), 'print': ('Interlace',),
}


class BranchMenu(QWidget):
    activated = Signal(object,list)
    dismissed = Signal()
    search_requested = Signal(object,list)
    recipes_requested = Signal(object,list)
    settings_requested = Signal()

    def __init__(self, build_rings, describe):
        super().__init__()
        self.build_rings,self.describe=build_rings,describe
        self.setWindowTitle('Swipe4Rest — дерево действий')
        self.setWindowFlags(Qt.Tool|Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.paths=[]
        self.levels=[]
        self.context=Context('unknown','')
        self.got_drag=False
        self.click_mode=False
        self.practice=False
        self.hover=-1
        self.scale=1.
        self.dark=False
        self.backdrop=None
        self.pointer=(0.,0.)
        self.recognizer=GestureDetector()
        self.frame=QTimer(self,interval=25,timeout=self._tick)
        self._back_since=None
        self._lock_until=0.
        self._keyboard=-1
        self._center_departed=False
        self.footer_hits={}
        self.message=''
        self.preferences=None

    @property
    def level(self):
        return self.levels[-1]

    @property
    def steps(self):
        return self.level.steps if self.levels else ()

    def _root_entries(self, steps):
        root=list(entries(self.context,steps))
        state=after(self.context,steps)
        advanced=[]
        for name in LEGACY.get(state.kind,()):
            if name=='Merge' and state.count==1:
                continue
            advanced.append(Entry('editor:'+name,tr(name),terminal='tool',tool_key='tool:'+name,
                                  hint='Отпустите: открыть редактор после цепочки'))
        if advanced:
            # Nested groups stay readable on narrow screens.
            groups=tuple(Entry('editors:'+str(i),'Ещё редакторы' if i else 'Редакторы',tuple(advanced[i:i+6]))
                         for i in range(0,len(advanced),6))
            process=root[1]
            root[1]=Entry(process.key,process.label,process.children+(Entry('advanced','Точные настройки',groups),))
        return tuple(root)

    def popup(self,pos=None,paths=None,*,drag_paths=None,practice=False):
        pos=pos or QCursor.pos()
        screen=QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        geometry=screen.availableGeometry()
        self.practice=practice
        self.click_mode=paths is not None or practice
        self.got_drag=bool(drag_paths)
        self.setWindowFlags((Qt.Window if practice else Qt.Tool)|Qt.FramelessWindowHint|
                            Qt.WindowStaysOnTopHint|Qt.NoDropShadowWindowHint)
        self.setWindowFlag(Qt.WindowDoesNotAcceptFocus,not self.click_mode)
        self.setGeometry(geometry)
        self.paths=resolve_shortcuts(paths if paths is not None else drag_paths or [])
        if not self.paths and not practice:
            return
        self.context=context_for(self.paths) if self.paths else Context('image','JPG',3)
        self.message='Тренировка: файлы не обрабатываются' if practice else ''
        if self.preferences:
            self.scale=float(self.preferences.q.value('branch_scale',1.))
            self.dark=self.preferences.q.value('branch_theme','light')=='dark'
            self.recognizer.pause_ms=int(self.preferences.q.value('branch_pause',240))
        self.scale=max(.8,min(1.3,self.scale))
        self.recognizer.minimum=74*self.scale
        self.recognizer.jitter=7*self.scale
        local=pos-geometry.topLeft()
        center=self._clamp((local.x(),local.y()))
        self.levels=[Level('Swipe4Rest',self._root_entries(()),center,(),root=True)]
        self.pointer=(local.x(),local.y())
        self.recognizer.reset(self.pointer)
        self.hover=self._keyboard=-1
        self._lock_until=time.monotonic()+.22
        self._back_since=None
        self._center_departed=False
        self.backdrop=None
        try:
            with glass.hidden_drag_images():
                raw=glass.capture_background(self,geometry)
            if raw is not None:
                self.backdrop=glass.blur_pixmap(QPixmap.fromImage(glass.qimage_from_pil(raw)),10)
        except Exception:
            pass
        self.show()
        self._shape()
        glass.allow_capture(int(self.winId()))
        self.raise_()
        self.frame.start()
        if self.click_mode:
            self.activateWindow()
            self.setFocus()
        self.update()

    def close_menu(self):
        if self.isVisible():
            self.hide()
            self.frame.stop()
            self.dismissed.emit()

    def hideEvent(self,event):
        self.frame.stop()
        self.recognizer.reset()
        super().hideEvent(event)

    def next_ring(self):
        # Repeated trigger presses do not mutate a partially drawn workflow.
        pass

    def _clamp(self,point):
        usable=max(300,self.height()-230)
        x,y=clamp_center((point[0],point[1]-120),self.width(),usable,190*self.scale)
        return x,y+120

    def _shape(self):
        if not glass.no_compositor():
            return
        # X11 without compositing cannot display a transparent full-screen
        # QWidget. Restrict the native window to its actual working regions.
        path=QPainterPath()
        path.addEllipse(QPointF(*self.level.center),192*self.scale,192*self.scale)
        for level in self.levels[-5:-1]:
            item=QPainterPath();item.addEllipse(QPointF(*level.center),27*self.scale,27*self.scale)
            path=path.united(item)
        for rect in (QRectF(24,20,min(self.width()-48,960),94),
                     QRectF(24,self.height()-102,min(self.width()-48,960),78)):
            item=QPainterPath();item.addRoundedRect(rect,14,14);path=path.united(item)
        glass.apply_shape(self,path)

    def angles(self):
        return item_angles(len(self.level.choices),self.level.incoming,self.level.root)

    def hit(self,point):
        point=(point.x(),point.y()) if isinstance(point,QPointF) else point
        return hit_sector(point,self.level.center,self.angles(),36*self.scale,190*self.scale,self.level.incoming)

    def navigate(self,index,point=None):
        if not 0<=index<len(self.level.choices):
            return
        entry=self.level.choices[index]
        if entry.terminal or not (entry.children or entry.step):
            return
        previous=self.level
        angle=self.angles()[index]
        rad=math.radians(angle)
        desired=point or (previous.center[0]+math.cos(rad)*142*self.scale,
                          previous.center[1]+math.sin(rad)*142*self.scale)
        center=self._clamp(desired)
        steps=previous.steps+(entry.step,) if entry.step else previous.steps
        try:
            after(self.context,steps)
            choices=self._root_entries(steps) if entry.step else entry.children
        except Exception as error:
            self.message=str(error)
            self.update()
            return
        # Backtracking restores the complete previous level, including plan.
        self.levels.append(Level(entry.label,choices,center,steps,None if entry.step else angle,root=bool(entry.step)))
        if len(self.levels)>40:
            self.levels=self.levels[-40:]
        self.hover=self._keyboard=-1
        self.recognizer.reset(center)
        self._lock_until=time.monotonic()+.22
        self._back_since=None
        self._center_departed=False
        self._shape()
        self.update()

    def back(self):
        if len(self.levels)>1:
            self.levels.pop()
            self.hover=self._keyboard=-1
            self.recognizer.reset(self.pointer)
            self._lock_until=time.monotonic()+.3
            self._back_since=None
            self._center_departed=False
            self._shape()
            self.update()
        else:
            self.close_menu()

    def pointer_move(self,point,now=None):
        now=time.monotonic() if now is None else now
        self.pointer=tuple(point)
        hit=self.hit(point)
        if hit!=self.hover:
            self.hover=hit
            self.update()
        if now<self._lock_until:
            return
        if math.dist(point,self.level.center)>50*self.scale:
            self._center_departed=True
        # Parent hubs are generous stable targets; a pause prevents a child
        # opening on top of an old anchor from immediately jumping backwards.
        parent_hit=hit in (-2,-3) and len(self.levels)>1 and self._center_departed
        if parent_hit:
            if self._back_since is None:
                self._back_since=now
            if now-self._back_since>=.38:
                self.back()
            return
        self._back_since=None
        chosen=self.recognizer.motion(point,now)
        if chosen is not None:
            index=self.hit(chosen)
            self.navigate(index,chosen)

    def _tick(self):
        if not self.levels:
            return
        now=time.monotonic()
        if not self.click_mode or self.practice:
            # Qt may suppress dragMove events while a pointer is stationary.
            local=self.mapFromGlobal(QCursor.pos())
            self.pointer_move((local.x(),local.y()),now)
        selected=self.recognizer.poll(now)
        if selected is not None and now>=self._lock_until:
            self.navigate(self.hit(selected),selected)

    @staticmethod
    def _local_paths(mime):
        return [url.toLocalFile() for url in mime.urls() if url.isLocalFile() and url.toLocalFile()] if mime.hasUrls() else []

    @staticmethod
    def _same_paths(first,second):
        # Native Windows payloads and Qt URLs disagree on slash direction and
        # drive-letter casing. Normalize spelling, never selection/order/count.
        normalize=lambda paths:[os.path.normcase(os.path.abspath(p)) for p in paths]
        return normalize(first)==normalize(second)

    def dragEnterEvent(self,event):
        paths=resolve_shortcuts(self._local_paths(event.mimeData()))
        if not paths or not self._same_paths(paths,self.paths):
            event.ignore()
            return
        self.got_drag=True
        event.setDropAction(Qt.CopyAction)
        event.accept()

    def dragMoveEvent(self,event):
        if not self._same_paths(resolve_shortcuts(self._local_paths(event.mimeData())),self.paths):
            event.ignore()
            return
        self.pointer_move((event.position().x(),event.position().y()))
        event.setDropAction(Qt.CopyAction)
        event.accept()

    def dragLeaveEvent(self,event):
        self.hover=-1
        self.recognizer.reset(self.pointer)
        self.update()

    def _dispatch(self,entry):
        if not entry.terminal:
            return False
        request=FlowRequest(tuple(self.steps),entry.terminal,entry.tool_key)
        if self.practice:
            self.message='Готово! Жест построил цепочку. Файлы не изменены.'
            self.levels=[Level('Swipe4Rest',self._root_entries(()),self.level.center,(),root=True)]
            self.update()
            return True
        paths=list(self.paths)
        self.hide()
        QTimer.singleShot(0,lambda:self.activated.emit(request,paths))
        return True

    def dropEvent(self,event):
        # The final OLE payload is authoritative, including order and count.
        paths=resolve_shortcuts(self._local_paths(event.mimeData()))
        if self._same_paths(paths,self.paths):
            for key,rect in self.footer_hits.items():
                if rect.contains(event.position()):
                    event.setDropAction(Qt.CopyAction)
                    event.accept()
                    self._footer(key)
                    return
        index=self.hit((event.position().x(),event.position().y()))
        if not self._same_paths(paths,self.paths) or not 0<=index<len(self.level.choices) or not self.level.choices[index].terminal:
            event.ignore()
            self.close_menu()
            return
        event.setDropAction(Qt.CopyAction)
        event.accept()
        self._dispatch(self.level.choices[index])

    def mouseMoveEvent(self,event):
        if self.click_mode:
            point=(event.position().x(),event.position().y())
            if self.practice or event.buttons() & Qt.LeftButton:
                self.pointer_move(point)
            else:
                self.pointer=point
                self.hover=self.hit(point)
                self.update()

    def mouseReleaseEvent(self,event):
        if not self.click_mode:
            return
        if event.button()==Qt.RightButton:
            self.back()
            return
        point=event.position()
        for key,rect in self.footer_hits.items():
            if rect.contains(point):
                self._footer(key)
                return
        hit=self.hit((point.x(),point.y()))
        if hit in (-2,-3):
            self.back()
        elif 0<=hit<len(self.level.choices):
            if not self._dispatch(self.level.choices[hit]):
                self.navigate(hit)
        else:
            self.close_menu()

    def _footer(self,key):
        if key=='practice':
            self.practice=not self.practice
            self.message='Тренировка: файлы не обрабатываются' if self.practice else ''
            self.update()
        elif key=='settings':
            self.close_menu()
            self.settings_requested.emit()
        else:
            request,paths=FlowRequest(tuple(self.steps),'review'),list(self.paths)
            self.close_menu()
            (self.search_requested if key=='search' else self.recipes_requested).emit(request,paths)

    def keyPressEvent(self,event):
        key=event.key()
        if key==Qt.Key_Escape:
            self.close_menu()
        elif key in (Qt.Key_Backspace,Qt.Key_Left):
            self.back()
        elif key in (Qt.Key_Down,Qt.Key_Up,Qt.Key_Tab):
            delta=-1 if key==Qt.Key_Up else 1
            self._keyboard=(self._keyboard+delta)%len(self.level.choices)
            self.hover=self._keyboard
            self.update()
        elif Qt.Key_1<=key<=Qt.Key_8:
            index=key-Qt.Key_1
            if index<len(self.level.choices):
                if not self._dispatch(self.level.choices[index]): self.navigate(index)
        elif key in (Qt.Key_Return,Qt.Key_Enter,Qt.Key_Right) and self.hover>=0:
            if not self._dispatch(self.level.choices[self.hover]): self.navigate(self.hover)
        elif key==Qt.Key_F:
            self._footer('search')
        elif key==Qt.Key_R:
            self._footer('recipes')
        elif key==Qt.Key_F1:
            self._footer('practice')

    def _panel(self,p,path,*,selected=False,alpha=220):
        if self.backdrop is not None:
            p.save()
            p.setClipPath(path)
            p.drawPixmap(0,0,self.backdrop)
            p.restore()
        background=QColor('#252927' if self.dark else '#f4f5f2')
        background.setAlpha(alpha)
        p.fillPath(path,background)
        if selected:
            p.fillPath(path,QColor(255,255,255,36) if self.dark else QColor(20,30,20,22))
        p.setPen(QPen(QColor('#747b76' if self.dark else '#b4bbb4'),1.4 if selected else .7))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

    def paintEvent(self,event):
        if not self.levels:
            return
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(),QColor(0,0,0,1))
        if glass.no_compositor() and self.backdrop is not None:
            p.drawPixmap(0,0,self.backdrop)
        foreground=QColor('#f1f4ef' if self.dark else '#202720')
        muted=QColor('#c0c8bf' if self.dark else '#50594f')
        font=QFont(ui_family())
        font.setPixelSize(round(13*self.scale))
        p.setFont(font)
        # Retain a short visible branch history; the complete back stack is kept.
        visible=self.levels[-5:]
        for before,current in zip(visible,visible[1:]):
            p.setPen(QPen(QColor('#899488'),2,Qt.SolidLine,Qt.RoundCap))
            p.drawLine(QPointF(*before.center),QPointF(*current.center))
        for level in visible[:-1]:
            path=QPainterPath()
            path.addEllipse(QPointF(*level.center),25*self.scale,25*self.scale)
            self._panel(p,path,alpha=240)
            # Draw the back chevron rather than depending on a symbol font.
            p.setPen(QPen(muted,2.2,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
            x,y=level.center
            p.drawLine(QPointF(x+5,y-8),QPointF(x-4,y))
            p.drawLine(QPointF(x-4,y),QPointF(x+5,y+8))
        center=self.level.center
        angles=self.angles()
        radius=111*self.scale
        # The circle describes broad hit wedges. Labels are solid readable pills,
        # not tiny targets: the entire directional sector belongs to each action.
        p.setPen(QPen(QColor('#8d978b' if self.dark else '#c7cfc3'),1))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(*center),radius,radius)
        for index,(entry,angle) in enumerate(zip(self.level.choices,angles)):
            rad=math.radians(angle)
            x,y=center[0]+math.cos(rad)*radius,center[1]+math.sin(rad)*radius
            width=146*self.scale
            rect=QRectF(x-width/2,y-25*self.scale,width,50*self.scale)
            path=QPainterPath()
            path.addRoundedRect(rect,14*self.scale,14*self.scale)
            selected=index==self.hover
            self._panel(p,path,selected=selected,alpha=236 if selected else 222)
            p.setPen(foreground)
            text=entry.label+('  ›' if entry.children or entry.step else '')
            p.drawText(rect.adjusted(8,4,-8,-4),Qt.AlignCenter|Qt.TextWordWrap,text)
        hub=QPainterPath()
        hub.addEllipse(QPointF(*center),34*self.scale,34*self.scale)
        self._panel(p,hub,alpha=235)
        p.setPen(foreground)
        p.drawText(QRectF(center[0]-34*self.scale,center[1]-24*self.scale,68*self.scale,48*self.scale),Qt.AlignCenter,
                   'Назад' if len(self.levels)>1 else str(len(self.steps))+'\nшагов')
        # Compact, stable plan strip; never let labels disappear into the desktop.
        strip=QRectF(24,20,min(self.width()-48,960),94)
        panel=QPainterPath();panel.addRoundedRect(strip,14,14)
        self._panel(p,panel,alpha=244)
        p.setPen(foreground)
        title='Swipe4Rest  /  '+('ТРЕНИРОВКА' if self.practice else f'{len(self.paths)} файл(а)')
        p.drawText(strip.adjusted(16,7,-16,-54),Qt.AlignVCenter,title)
        chain='  →  '.join(step_text(s) for s in self.steps) or 'Влево — конвертировать · вправо — обработать'
        p.drawText(strip.adjusted(16,33,-16,-12),Qt.AlignLeft|Qt.AlignVCenter|Qt.TextWordWrap,chain)
        bottom=QRectF(24,self.height()-102,min(self.width()-48,960),78)
        panel=QPainterPath();panel.addRoundedRect(bottom,14,14)
        self._panel(p,panel,alpha=244)
        p.setPen(muted)
        help_text=self.message or ('Пауза / поворот — открыть ветвь. Отпустить на «Сохранить результат» — выполнить. Центр — назад. Esc — отмена.')
        p.drawText(bottom.adjusted(16,7,-16,-34),Qt.AlignLeft|Qt.AlignVCenter|Qt.TextWordWrap,help_text)
        self.footer_hits={}
        x=bottom.left()+12
        for key,label,width in [('search','F  Поиск',112),('recipes','R  Цепочки',132),('practice','F1  Тренировка',160),('settings','Настройки',132)]:
            rect=QRectF(x,bottom.bottom()-31,width,25)
            self.footer_hits[key]=rect
            p.setPen(foreground)
            p.drawText(rect,Qt.AlignCenter,label)
            x+=width
