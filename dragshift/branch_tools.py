"""Plan review, action search, reusable recipes and isolated menu preferences."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox,QComboBox,QDoubleSpinBox,QFileDialog,QFormLayout,
    QHBoxLayout,QInputDialog,QLabel,QLineEdit,QListWidget,QPushButton,QSpinBox,QVBoxLayout)

from .branch_model import Entry,FlowRequest,Step,after,context_for,entries,plan_json,read_plan,step_text
from .util import UserError
from .window import GlassWindow


def all_actions(context,steps):
    result=[]
    def walk(nodes,prefix=''):
        for entry in nodes:
            label=f'{prefix} / {entry.label}' if prefix else entry.label
            if entry.step:
                result.append((label,entry.step))
            walk(entry.children,label)
    walk(entries(context,steps))
    return result


class RecipeStore:
    def __init__(self,settings):
        self.settings=settings

    def load(self):
        try:
            values=json.loads(self.settings.q.value('recipes','[]'))
            return [read_plan(value) for value in values[:80]]
        except (TypeError,ValueError,UserError):
            return []

    def save(self,name,steps,finish='none'):
        encoded=plan_json(name,steps,finish)
        # Round-trip validates operations, values, size and interchange schema.
        read_plan(encoded)
        values=[plan_json(n,s,f) for n,s,f in self.load() if n!=name]
        values.append(encoded)
        self.settings.q.setValue('recipes',json.dumps(values[-80:],ensure_ascii=False))
        self.settings.q.sync()


class FlowReviewWindow(GlassWindow):
    def __init__(self,paths,steps,on_run,settings,*,search=False,recipes=False):
        super().__init__('Цепочка действий',size=(820,760))
        self.paths=list(paths)
        self.context=context_for(paths)
        self.steps=list(steps)
        self.on_run=on_run
        self.store=RecipeStore(settings)
        self._loading=False
        note=QLabel('Каждый шаг получает результат предыдущего. Исходники остаются без изменений. Числа можно вводить с клавиатуры.')
        note.setWordWrap(True)
        self.body.addWidget(note)
        self.list=QListWidget()
        self.list.setAccessibleName('Шаги цепочки')
        self.list.currentRowChanged.connect(self._select)
        self.body.addWidget(self.list,1)
        row=QHBoxLayout()
        for text,callback in [('↑',lambda:self._move(-1)),('↓',lambda:self._move(1)),('Удалить шаг',self._remove)]:
            button=QPushButton(text);button.clicked.connect(callback);row.addWidget(button)
        self.body.addLayout(row)
        form=QFormLayout()
        self.value=QDoubleSpinBox();self.value.setDecimals(3);self.value.setRange(-60,864000)
        self.value.setAccessibleName('Значение выбранного шага')
        self.value.valueChanged.connect(self._value_changed)
        self.end=QDoubleSpinBox();self.end.setDecimals(3);self.end.setRange(.04,864000)
        self.end.setAccessibleName('Конец участка, секунды');self.end.valueChanged.connect(self._value_changed)
        form.addRow('Значение / начало, с',self.value);form.addRow('Конец участка, с',self.end)
        self.body.addLayout(form)
        self.query=QLineEdit();self.query.setPlaceholderText('Поиск действия: размер, GIF, звук, архив…')
        self.query.setAccessibleName('Поиск доступных действий');self.query.textChanged.connect(self._search)
        self.body.addWidget(self.query)
        self.actions=QComboBox();self.actions.setAccessibleName('Доступное действие')
        self.add_button=QPushButton('Добавить действие');self.add_button.clicked.connect(self._add)
        row=QHBoxLayout();row.addWidget(self.actions,1);row.addWidget(self.add_button);self.body.addLayout(row)
        self.recipes=QComboBox();self.recipes.setAccessibleName('Сохранённые цепочки')
        row=QHBoxLayout();row.addWidget(self.recipes,1)
        for text,callback in [('Загрузить',self._load_recipe),('Сохранить как…',self._save_recipe),('Импорт',self._import),('Экспорт',self._export)]:
            button=QPushButton(text);button.clicked.connect(callback);row.addWidget(button)
        self.body.addLayout(row)
        self.finish=QComboBox()
        for label,key in [('Просто сохранить','none'),('Открыть папку результата','folder'),('Скопировать пути результатов','clipboard')]:
            self.finish.addItem(label,key)
        form=QFormLayout();form.addRow('После выполнения',self.finish);self.body.addLayout(form)
        self.error=QLabel();self.error.setWordWrap(True);self.body.addWidget(self.error)
        row=QHBoxLayout();row.addStretch()
        close=QPushButton('Отмена');close.clicked.connect(self.close);row.addWidget(close)
        self.run_button=QPushButton('Выполнить цепочку');self.run_button.setObjectName('primary')
        self.run_button.clicked.connect(self._run);row.addWidget(self.run_button);self.body.addLayout(row)
        self._refresh_recipes()
        self._refresh()
        if search:self.query.setFocus()
        if recipes:self.recipes.setFocus()

    def _refresh(self):
        selected=max(0,self.list.currentRow())
        self._loading=True
        self.list.clear()
        for i,step in enumerate(self.steps):self.list.addItem(f'{i+1}. {step_text(step)}')
        self.list.setCurrentRow(min(selected,len(self.steps)-1))
        self._loading=False
        self._select(self.list.currentRow())
        try:
            after(self.context,self.steps)
            self.error.setText('')
            self.run_button.setEnabled(bool(self.steps))
        except UserError as error:
            self.error.setText(str(error));self.run_button.setEnabled(False)
        self._search()

    def _select(self,row):
        if self._loading:return
        self._loading=True
        step=self.steps[row] if 0<=row<len(self.steps) else None
        numeric=step is not None and (isinstance(step.value,(int,float)) or step.op=='trim')
        self.value.setEnabled(numeric);self.end.setEnabled(bool(step and step.op=='trim'))
        if numeric:
            value=step.value[0] if step.op=='trim' else step.value
            self.value.setValue(value)
            if step.op=='trim':self.end.setValue(step.value[1])
        self._loading=False

    def _value_changed(self):
        if self._loading:return
        row=self.list.currentRow()
        if not 0<=row<len(self.steps):return
        old=self.steps[row]
        value=(self.value.value(),self.end.value()) if old.op=='trim' else self.value.value()
        if old.op in ('resize','rotate','quality'):value=round(value)
        self.steps[row]=Step(old.op,value)
        self._refresh()

    def _move(self,delta):
        row=self.list.currentRow();other=row+delta
        if 0<=row<len(self.steps) and 0<=other<len(self.steps):
            self.steps[row],self.steps[other]=self.steps[other],self.steps[row]
            self._refresh();self.list.setCurrentRow(other)

    def _remove(self):
        row=self.list.currentRow()
        if 0<=row<len(self.steps):self.steps.pop(row);self._refresh()

    def _search(self,*_):
        self.actions.clear()
        try:choices=all_actions(self.context,self.steps)
        except UserError:choices=[]
        query=self.query.text().casefold().strip()
        # Token/subsequence matching is independently implemented, inspired by
        # launchers' action search, not a copied C# search backend.
        def matches(label):
            hay=iter(label.casefold())
            return all(any(char==candidate for candidate in hay) for char in query)
        for label,step in choices:
            if not query or all(word in label.casefold() for word in query.split()) or matches(label):
                self.actions.addItem(label,step)
        self.add_button.setEnabled(self.actions.count()>0)

    def _add(self):
        step=self.actions.currentData()
        if step is not None:
            self.steps.append(step);self._refresh();self.list.setCurrentRow(len(self.steps)-1)

    def _refresh_recipes(self):
        self.recipes.clear()
        presets=[('Для сайта: 1920 → WebP',(Step('resize',1920),Step('convert','WEBP')),'none'),
                 ('Кадры → GIF → ZIP',(Step('animate',10),Step('pack','ZIP')),'none'),
                 ('Видео без звука → WebM',(Step('mute'),Step('convert','WEBM')),'none')]+self.store.load()
        for name,steps,finish in presets:
            try:after(self.context,steps)
            except UserError:continue
            self.recipes.addItem(name,(steps,finish))

    def _load_recipe(self):
        value=self.recipes.currentData()
        if value:
            self.steps=list(value[0]);self.finish.setCurrentIndex(max(0,self.finish.findData(value[1])));self._refresh()

    def _save_recipe(self):
        name,ok=QInputDialog.getText(self,'Сохранить цепочку','Название')
        if ok:
            try:self.store.save(name,self.steps,self.finish.currentData());self._refresh_recipes()
            except UserError as error:self.error.setText(str(error))

    def _import(self):
        path,_=QFileDialog.getOpenFileName(self,'Импорт цепочки','','Цепочка (*.json)')
        if not path:return
        try:
            if Path(path).stat().st_size>65536:raise UserError('Файл цепочки слишком большой.')
            name,steps,finish=read_plan(Path(path).read_text(encoding='utf-8'))
            after(self.context,steps)
            self.store.save(name,steps,finish)
            self.steps=list(steps);self.finish.setCurrentIndex(max(0,self.finish.findData(finish)))
            self._refresh_recipes();self._refresh()
        except (UserError,OSError,UnicodeError) as error:self.error.setText(str(error))

    def _export(self):
        if not self.steps:return
        path,_=QFileDialog.getSaveFileName(self,'Экспорт цепочки','chain.json','Цепочка (*.json)')
        if not path:return
        try:
            after(self.context,self.steps)
            Path(path).write_text(plan_json('Моя цепочка',self.steps,self.finish.currentData()),encoding='utf-8')
        except (UserError,OSError) as error:self.error.setText(str(error))

    def _run(self):
        try:after(self.context,self.steps)
        except UserError as error:self.error.setText(str(error));return
        self.on_run(FlowRequest(tuple(self.steps)),self.paths,self.finish.currentData())
        self.close()


class BranchSettingsWindow(GlassWindow):
    changed=Signal()

    def __init__(self,settings):
        super().__init__('Настройки',size=(640,470))
        self.settings=settings
        note=QLabel('Это отдельная тестовая программа. По умолчанию: Alt при переносе файла, чтобы не пересекаться с Shift в DragShift. Автозапуск и обновление DragShift здесь не меняются.')
        note.setWordWrap(True);self.body.addWidget(note)
        form=QFormLayout()
        self.trigger=QComboBox()
        for text,key in [('Alt / Option','alt'),('Shift','shift'),('Ctrl / Control','ctrl')]:self.trigger.addItem(text,key)
        self.trigger.setCurrentIndex(max(0,self.trigger.findData(settings.get('trigger'))))
        self.trigger.currentIndexChanged.connect(lambda:self._save('trigger',self.trigger.currentData()))
        form.addRow('Клавиша при переносе',self.trigger)
        self.pause=QSpinBox();self.pause.setRange(120,800);self.pause.setSuffix(' мс')
        self.pause.setValue(int(settings.q.value('branch_pause',240)))
        self.pause.valueChanged.connect(lambda v:self._save('branch_pause',v));form.addRow('Пауза для раскрытия ветки',self.pause)
        self.scale=QDoubleSpinBox();self.scale.setRange(.8,1.3);self.scale.setSingleStep(.1)
        self.scale.setValue(float(settings.q.value('branch_scale',1.)))
        self.scale.valueChanged.connect(lambda v:self._save('branch_scale',v));form.addRow('Масштаб меню',self.scale)
        self.theme=QComboBox();self.theme.addItem('Светлое матовое стекло','light');self.theme.addItem('Тёмное матовое стекло','dark')
        self.theme.setCurrentIndex(max(0,self.theme.findData(settings.q.value('branch_theme','light'))))
        self.theme.currentIndexChanged.connect(lambda:self._save('branch_theme',self.theme.currentData()))
        form.addRow('Вид дерева',self.theme);self.body.addLayout(form);self.body.addStretch()
        close=QPushButton('Готово');close.clicked.connect(self.close);self.body.addWidget(close)

    def _save(self,key,value):
        self.settings.q.setValue(key,value);self.settings.q.sync();self.changed.emit()
