"""Typed, side-effect-free file workflows for the isolated Swipe4Rest experiment."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
import math
from pathlib import Path

from .util import UserError, category

MAX_STEPS = 16
IMAGE_FORMATS = ('PNG', 'JPG', 'WEBP', 'AVIF', 'TIFF', 'BMP', 'HEIC', 'ICO', 'GIF', 'PDF')
VIDEO_FORMATS = ('MP4', 'WEBM', 'MKV', 'MOV', 'AVI', 'GIF', 'MP3', 'WAV')
AUDIO_FORMATS = ('MP3', 'WAV', 'FLAC', 'M4A', 'AAC', 'OGG', 'OPUS', 'AIFF')
FORMATS = {'image': IMAGE_FORMATS, 'video': VIDEO_FORMATS, 'audio': AUDIO_FORMATS,
           'pdf': ('PNG', 'JPG', 'TXT', 'DOCX'), 'docx': ('PDF', 'TXT'),
           'text': ('PDF', 'DOCX'), 'archive': ('ZIP', '7Z', 'TAR')}


@dataclass(frozen=True)
class Step:
    op: str
    value: object = None


@dataclass(frozen=True)
class Context:
    kind: str
    ext: str
    count: int = 1  # -1: output count is not known until decoding pages/frames.
    animated: bool = False
    sound: bool | None = None


@dataclass(frozen=True)
class Entry:
    key: str
    label: str
    children: tuple[Entry, ...] = ()
    step: Step | None = None
    terminal: str = ''
    tool_key: str = ''
    hint: str = ''


@dataclass(frozen=True)
class FlowRequest:
    steps: tuple[Step, ...]
    terminal: str = 'save'
    tool_key: str = ''


def context_for(paths) -> Context:
    if not paths:
        raise UserError('Выберите файлы для цепочки.')
    types = {category(p) if not Path(p).is_dir() else 'folder' for p in paths}
    kind = next(iter(types)) if len(types) == 1 else 'mixed'
    exts = {Path(p).suffix[1:].upper() for p in paths}
    ext = next(iter(exts)) if len(exts) == 1 else ''
    ext = {'JPEG': 'JPG', 'TIF': 'TIFF', 'HEIF': 'HEIC', 'AIF': 'AIFF'}.get(ext, ext)
    if all(str(p).endswith('.dshift-print') for p in paths):
        return Context('print', ext, len(paths))
    animated=kind=='image' and ext in ('GIF','WEBP','PNG','AVIF')
    if kind=='image' and Path(paths[0]).is_file():
        from .animation import is_animated
        try:animated=is_animated(paths[0])
        except (OSError,ValueError):pass
    return Context(kind or 'unknown', ext, len(paths), animated)


def _number(value, lo, hi):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
        raise UserError(f'Значение должно быть от {lo:g} до {hi:g}.')


def after(context: Context, steps) -> Context:
    steps = tuple(steps)
    if len(steps) > MAX_STEPS:
        raise UserError(f'В одной цепочке допускается до {MAX_STEPS} действий.')
    state = context
    for step in steps:
        if not isinstance(step, Step):
            raise UserError('Неизвестное действие цепочки.')
        op, value = step.op, step.value
        if op == 'convert':
            available = FORMATS.get(state.kind, ()) + (('MP4','WEBM','MOV','MKV','AVI') if state.kind=='image' and state.ext=='GIF' else ())
            if value not in available:
                raise UserError(f'Формат {value} недоступен после предыдущего шага.')
            kind = ('audio' if value in AUDIO_FORMATS else 'video' if value in ('MP4','WEBM','MKV','MOV','AVI') else
                    'pdf' if value == 'PDF' else 'docx' if value == 'DOCX' else 'text' if value == 'TXT' else
                    'archive' if value in ('ZIP','7Z','TAR') else 'image')
            if kind=='audio' and state.sound is False:
                raise UserError('После удаления звука извлекать аудио уже нельзя. Вернитесь к шагу перед «Без звука».')
            count = state.count
            if value in ('PDF', 'GIF') and state.kind == 'image':
                count = 1
            elif state.kind == 'pdf' and kind == 'image' or state.animated and value in IMAGE_FORMATS and value not in ('GIF', 'PDF'):
                count = -1
            state = Context(kind, value, count, value == 'GIF',state.sound if kind=='video' else True if kind=='audio' else False)
        elif op == 'animate':
            if state.kind != 'image' or state.count == 1:
                raise UserError('Для анимации выберите несколько кадров.')
            _number(value, 1, 100)
            state = Context('image','GIF',1,True)
        elif op == 'pack':
            if value not in ('ZIP', '7Z'):
                raise UserError('Выберите ZIP или 7Z.')
            state = Context('archive', value)
        elif op in ('resize', 'crop', 'rotate', 'gray'):
            if state.kind not in ('image', 'video'):
                raise UserError('Геометрия доступна для изображений и видео.')
            if op == 'resize':
                _number(value, 16, 7680)
                if int(value) != value:
                    raise UserError('Размер должен быть целым числом пикселей.')
            elif op == 'crop':
                _number(value, .1, 10)
            elif op == 'rotate' and value not in (90, 180, 270):
                raise UserError('Поворот: 90, 180 или 270 градусов.')
            elif op == 'gray' and value is not None:
                raise UserError('У этого действия нет параметра.')
        elif op == 'invert':
            if state.kind!='image' or value is not None:
                raise UserError('Инверсия цветов доступна для изображений и анимаций.')
        elif op in ('mute', 'trim', 'frame'):
            if state.kind != 'video':
                raise UserError('Действие доступно для видео.')
            if op == 'trim':
                if not isinstance(value, (tuple, list)) or len(value) != 2:
                    raise UserError('Задайте начало и конец участка.')
                _number(value[0], 0, 864000)
                _number(value[1], .04, 864000)
                if value[1] - value[0] < .04:
                    raise UserError('Конец участка должен быть позже начала.')
            elif op == 'frame':
                _number(value, 0, 864000)
                state = Context('image', 'PNG', state.count)
            elif value is not None:
                raise UserError('У этого действия нет параметра.')
            if op=='mute':
                state=replace(state,sound=False)
        elif op == 'reverse':
            if state.kind not in ('image','video','audio') or value is not None:
                raise UserError('Реверс доступен для анимации, видео и звука.')
        elif op in ('normalize', 'fade', 'volume'):
            if state.kind != 'audio':
                raise UserError('Действие доступно для аудио.')
            if op == 'fade':
                _number(value, .01, 60)
            elif op == 'volume':
                _number(value, -60, 20)
            elif value is not None:
                raise UserError('У этого действия нет параметра.')
        elif op == 'quality':
            if state.kind not in ('image', 'video'):
                raise UserError('Качество доступно для изображений и видео.')
            _number(value, 40, 100)
        elif op in ('clean', 'compress_pdf', 'rotate_pdf', 'split_pdf'):
            allowed = ('pdf',) if op.endswith('_pdf') else ('image', 'video', 'audio', 'pdf')
            if state.kind not in allowed or value is not None:
                raise UserError('Действие недоступно для результата предыдущего шага.')
            if op == 'split_pdf':
                state = Context('pdf', 'PDF', -1)
        else:
            raise UserError(f'Неизвестное действие: {op}')
    return state


def step_text(step):
    names = {'resize': 'Большая сторона', 'crop': 'Кроп по центру', 'rotate': 'Поворот', 'gray': 'Чёрно-белое', 'invert':'Инверсия цветов',
             'quality': 'Качество', 'mute': 'Без звука', 'trim': 'Участок', 'frame': 'Кадр', 'normalize': 'Нормализация',
             'fade': 'Плавное начало/конец', 'volume': 'Громкость', 'reverse': 'Задом наперёд',
             'clean': 'Убрать метаданные', 'compress_pdf': 'Сжать PDF', 'rotate_pdf': 'Повернуть страницы', 'split_pdf': 'Разделить PDF'}
    if step.op == 'convert':
        return str(step.value)
    if step.op == 'pack':
        return f'Архив {step.value}'
    if step.op == 'animate':
        return f'GIF: {step.value:g} кадров/с'
    label = names.get(step.op, step.op)
    if step.op == 'trim':
        return f'{label}: {step.value[0]:g}–{step.value[1]:g} с'
    if step.value is not None:
        unit = {'resize': ' пикс.', 'rotate': '°', 'quality': '%', 'fade': ' с', 'volume': ' дБ', 'frame': ' с'}.get(step.op, '')
        return f'{label}: {step.value:g}{unit}'
    return label


def _action(op, value=None, label=''):
    step = Step(op, value)
    return Entry(f'{op}:{value}', label or step_text(step), step=step)


def _group(key, label, children, hint=''):
    return Entry(key, label, tuple(children), hint=hint)


def conversion_entries(state):
    formats = FORMATS.get(state.kind, ())
    groups = []
    if state.kind == 'image':
        groups = [_group('web', 'Для экрана', [_action('convert', v, v) for v in ('JPG','WEBP','AVIF','PNG')]),
                  _group('print', 'Печать / без потерь', [_action('convert', v, v) for v in ('TIFF','BMP','HEIC','ICO')]),
                  _action('convert', 'PDF', 'Один PDF из серии')]
        groups.append(_group('gif','Одна GIF из кадров',[_action('animate',v) for v in (10,15,24,30)]) if state.count != 1 else _action('convert','GIF','GIF'))
        if state.count!=1:
            groups.append(Entry('gif-order','GIF: порядок кадров / FPS',terminal='tool',tool_key='convert:GIF',
                                hint='Отпустите: порядок по имени, дате или вручную; частота кадров'))
        if state.ext == 'GIF':
            groups[0] = _group('frames', 'Извлечь все кадры', [_action('convert', v, v) for v in ('PNG','JPG','WEBP','BMP')])
            groups.append(_group('video', 'Видео из анимации', [_action('convert',v,v) for v in ('MP4','WEBM','MOV','MKV','AVI')]))
    elif state.kind == 'video':
        groups = [_group('movie','Видео',[_action('convert',v,v) for v in ('MP4','WEBM','MKV','MOV','AVI')]),
                  _action('convert','GIF','Анимированная GIF'), _action('frame',0.,'PNG: первый кадр')]
        if state.sound is not False:
            groups.insert(1,_group('sound','Извлечь звук',[_action('convert',v,v) for v in ('MP3','WAV')]))
    else:
        groups = [_action('convert',v,v) for v in formats]
    if state.kind == 'video' or state.kind == 'image' and state.ext == 'GIF':
        groups.append(Entry('emoji','Telegram эмодзи',terminal='tool',tool_key='tool:Telegram emoji',hint='100 × 100 · VP9 · до 3 с'))
    return tuple(groups)


def processing_entries(state):
    entries = []
    if state.kind in ('image','video'):
        entries += [_group('size','Размер',[_action('resize',v) for v in (640,1280,1920,2560)]),
                    _group('crop','Обрезать бока',[_action('crop',v,label) for v,label in ((1.,'Квадрат 1:1'),(16/9,'Горизонталь 16:9'),(9/16,'Вертикаль 9:16'),(4/3,'4:3'))]),
                    _group('look','Вид',[_action('rotate',90),_action('rotate',180),_action('rotate',270),_action('gray')]+([_action('invert')]+([_action('reverse',label='Реверс кадров')] if state.animated else []) if state.kind=='image' else [])),
                    _group('quality','Качество экспорта',[_action('quality',v) for v in (65,80,90,100)],'Для видео и сжатых JPG / WebP / AVIF')]
        if state.kind == 'video':
            entries.append(_group('time','Время / звук',[_action('mute'),_action('trim',(0.,3.),'Первые 3 секунды'),_action('frame',0.,'Сохранить кадр'),_action('reverse',label='Реверс кадров')]))
    elif state.kind == 'audio':
        entries += [_action('normalize'),_group('fade','Плавные края',[_action('fade',v) for v in (.1,.5,1.,2.)]),
                    _group('volume','Громкость',[_action('volume',v) for v in (-12.,-6.,3.,6.)]),_action('reverse')]
    elif state.kind == 'pdf':
        entries += [_action('compress_pdf'),_action('rotate_pdf'),_action('split_pdf')]
    if state.kind in ('image','video','audio','pdf'):
        entries.append(_action('clean'))
    # Packing is valid even for mixed types and folders. No files are silently omitted.
    entries.append(_group('pack','Файлы',[Entry('rename','Переименовать',terminal='tool',tool_key='tool:Rename',hint='Правила · предпросмотр имён · отмена'),*[_action('pack',v,v) for v in ('ZIP','7Z')]]))
    return tuple(entries)


def entries(context, steps=()):
    state = after(context, steps)
    convert = conversion_entries(state)
    process = processing_entries(state)
    root = [Entry('convert','Конвертировать',convert,hint='Выбрать формат результата'),
            Entry('process','Обработать',process,hint='Добавить действие к цепочке')]
    if steps:
        root += [Entry('save','Сохранить результат',terminal='save',hint='Отпустите файл здесь: выполнить цепочку'),
                 Entry('review','Настроить цепочку',terminal='review',hint='Числа · порядок · сохранить пресет')]
    return tuple(root)


def plan_json(name, steps, finish='none'):
    if not isinstance(name,str) or not 1 <= len(name.strip()) <= 80 or finish not in ('none','folder','clipboard'):
        raise UserError('Задайте название цепочки до 80 символов.')
    return json.dumps({'schema':'swipe4rest.recipe.v1','name':name.strip(),'steps':[asdict(s) for s in steps],
                       'finish':finish}, ensure_ascii=False, indent=2)


def read_plan(text):
    if len(text) > 65536:
        raise UserError('Файл цепочки слишком большой.')
    try:
        obj = json.loads(text)
        if set(obj) != {'schema','name','steps','finish'} or obj['schema'] != 'swipe4rest.recipe.v1':
            raise ValueError()
        if not isinstance(obj['steps'],list) or not 1 <= len(obj['steps']) <= MAX_STEPS:
            raise ValueError()
        steps = []
        for item in obj['steps']:
            if not isinstance(item,dict) or set(item) != {'op','value'} or not isinstance(item['op'],str):
                raise ValueError()
            value = tuple(item['value']) if item['op']=='trim' and isinstance(item['value'],list) else item['value']
            steps.append(Step(item['op'],value))
        # Validate against at least one supported input context; imported recipes
        # contain data only, never executable commands or file-system paths.
        valid = False
        for kind in FORMATS | {'mixed':()}:
            try:
                after(Context(kind,'',2),steps)
                valid = True
                break
            except (UserError,TypeError):
                pass
        if not valid:
            raise ValueError()
        plan_json(obj['name'],steps,obj['finish'])
        return obj['name'], tuple(steps), obj['finish']
    except (ValueError, TypeError, KeyError, AttributeError, UserError) as error:
        raise UserError('Это не поддерживаемая цепочка Swipe4Rest.') from error
