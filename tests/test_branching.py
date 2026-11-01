import hashlib
import json
import math
from pathlib import Path
import subprocess

from PIL import Image, ImageSequence
import pytest
from PySide6.QtCore import QMimeData,QPoint,QPointF,Qt,QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtTest import QSignalSpy

from dragshift.branch_model import Context,Step,after,context_for,entries,plan_json,read_plan
from dragshift.branch_gestures import GestureDetector,clamp_center,hit_sector,item_angles
from dragshift.branch_pipeline import execute
from dragshift.util import UserError
from dragshift import video


def image(tmp_path,name='source.png',color=(220,30,10),size=(80,60)):
    path=tmp_path/name
    Image.new('RGB',size,color).save(path)
    return path


def test_context_changes_to_audio_and_rejects_image_edits():
    state=after(Context('video','MOV'),[Step('crop',1.),Step('convert','WAV')])
    assert state.kind=='audio'
    with pytest.raises(UserError):after(state,[Step('crop',1.)])


def test_muted_result_does_not_offer_audio_extraction():
    from dragshift.branch_model import conversion_entries
    state=after(Context('video','MP4'),[Step('mute')])
    assert 'sound' not in [entry.key for entry in conversion_entries(state)]
    with pytest.raises(UserError):after(state,[Step('convert','WAV')])


@pytest.mark.parametrize('step',[Step('resize',True),Step('crop',float('nan')),Step('resize',15),
    Step('rotate',42),Step('shell','touch file'),Step('trim',(3,1))])
def test_invalid_steps(step):
    with pytest.raises(UserError):after(Context('video','MP4'),[step])


def test_maximum_chain_and_recipe_validation():
    with pytest.raises(UserError):after(Context('image','PNG'),[Step('gray')]*17)
    steps=(Step('trim',(0.,2.)),Step('convert','WEBM'),Step('pack','ZIP'))
    assert read_plan(plan_json('Тест',steps))==('Тест',steps,'none')
    payload=json.loads(plan_json('Тест',steps));payload['steps'][0]={'op':'execute','value':'cmd.exe'}
    with pytest.raises(UserError):read_plan(json.dumps(payload))
    with pytest.raises(UserError):read_plan('x'*65537)


def test_root_directions_do_not_move_when_plan_is_added():
    assert [e.key for e in entries(Context('image','PNG'))]==['convert','process']
    assert item_angles(2,root=True)==item_angles(4,root=True)[:2]
    assert [e.terminal for e in entries(Context('image','PNG'),[Step('gray')])][-2:]==['save','review']


def test_image_series_retains_configurable_gif_order_editor():
    choices=entries(Context('image','PNG',160))[0].children
    assert any(entry.tool_key=='convert:GIF' and entry.terminal=='tool' for entry in choices)


def test_advanced_pdf_and_archive_actions_are_retained(qt_session):
    from dragshift.branch_menu import BranchMenu
    instance=BranchMenu(lambda _: {},lambda _:'')
    instance.context=Context('pdf','PDF')
    def keys(nodes):
        return {entry.tool_key for entry in nodes}|{key for entry in nodes for key in keys(entry.children)}
    assert {'tool:Extract','tool:Pack','tool:Protect','tool:Metadata'}<=keys(instance._root_entries(()))
    instance.close()


def test_pause_corner_and_jitter():
    detector=GestureDetector(pause_ms=200)
    detector.reset((0,0))
    assert detector.motion((100,0),0) is None
    assert detector.motion((102,1),.1) is None
    assert detector.poll(.19) is None
    assert detector.poll(.21)==(100,0)
    assert detector.poll(.5) is None
    detector.reset((0,0));detector.motion((100,0),0)
    assert detector.motion((100,30),.1)==(100,0)
    detector.reset((0,0));detector.motion((8,0),0)
    assert detector.poll(1) is None


@pytest.mark.parametrize('point',[(-500,-500),(0,0),(5000,5000),(1000,0)])
def test_edge_layout(point):
    x,y=clamp_center(point,1200,700,190)
    assert 190<=x<=1010 and 190<=y<=510
    assert hit_sector((x,y),(x,y),(0,180))==-2
    assert hit_sector((x+80,y),(x,y),(180,0))==1


def test_fused_image_chain_and_no_intermediates(tmp_path):
    src=image(tmp_path,size=(800,600));digest=hashlib.sha256(src.read_bytes()).hexdigest()
    outs=execute([src],[Step('resize',160),Step('crop',1.),Step('rotate',90),Step('convert','WEBP')])
    assert len(outs)==1 and outs[0].suffix=='.webp'
    with Image.open(outs[0]) as result:assert result.size==(120,120)
    assert hashlib.sha256(src.read_bytes()).hexdigest()==digest
    assert set(tmp_path.iterdir())=={src,outs[0]}


def test_numbered_frames_build_one_animation_in_order(tmp_path):
    paths=[image(tmp_path,f'frame{n}.png',color) for n,color in [(10,(0,0,255)),(1,(255,0,0)),(2,(0,255,0))]]
    out=execute(paths,[Step('resize',40),Step('animate',10)])[0]
    with Image.open(out) as result:
        assert result.n_frames==3
        colors=[frame.convert('RGB').getpixel((10,10)) for frame in ImageSequence.Iterator(result)]
        assert colors==[(255,0,0),(0,255,0),(0,0,255)]


def test_animation_edits_then_extract_all_frames(tmp_path):
    src=tmp_path/'animated.gif'
    frames=[Image.new('RGB',(80,60),c) for c in ('red','green','blue')]
    frames[0].save(src,save_all=True,append_images=frames[1:],duration=[100,200,300],loop=0)
    out=execute([src],[Step('crop',1.),Step('convert','PNG')])[0]
    assert out.is_dir()
    files=sorted(out.iterdir())
    assert len(files)==3
    assert [Image.open(p).size for p in files]==[(60,60)]*3
    assert [Image.open(p).convert('RGB').getpixel((10,10)) for p in files]==[(255,0,0),(0,128,0),(0,0,255)]


def test_frames_from_multiple_animations_remain_grouped_when_reassembled(tmp_path):
    paths=[]
    for name,colors in [('a.gif',('red','green')),('b.gif',('blue','yellow'))]:
        frames=[Image.new('RGB',(32,32),color) for color in colors]
        path=tmp_path/name
        frames[0].save(path,save_all=True,append_images=frames[1:],duration=100,loop=0)
        paths.append(path)
    out=execute(paths,[Step('convert','PNG'),Step('animate',10)])[0]
    with Image.open(out) as result:
        colors=[frame.convert('RGB').getpixel((10,10)) for frame in ImageSequence.Iterator(result)]
    assert colors==[(255,0,0),(0,128,0),(0,0,255),(255,255,0)]


def test_chosen_quality_affects_final_encode(tmp_path):
    import numpy as np
    src=tmp_path/'texture.png'
    Image.fromarray(np.random.default_rng(42).integers(0,256,(256,256,3),dtype=np.uint8)).save(src)
    low=execute([src],[Step('quality',40),Step('convert','WEBP')])[0]
    high=execute([src],[Step('quality',90),Step('convert','WEBP')])[0]
    assert low.stat().st_size<high.stat().st_size*.85


def test_batch_pack_contains_only_final_images(tmp_path):
    import zipfile
    paths=[image(tmp_path,'one.png'),image(tmp_path,'two.png')]
    out=execute(paths,[Step('gray'),Step('convert','JPG'),Step('pack','ZIP')])[0]
    with zipfile.ZipFile(out) as archive:
        assert len(archive.namelist())==2
        assert all(name.endswith('.jpg') for name in archive.namelist())


def test_cancel_before_publication_rolls_back(tmp_path,monkeypatch):
    from dragshift import branch_pipeline
    src=image(tmp_path)
    control=video.Control()
    original=branch_pipeline._images
    def cancel_after_edit(*args):
        outputs=original(*args);control.cancel.set();return outputs
    monkeypatch.setattr(branch_pipeline,'_images',cancel_after_edit)
    with video.job_context(control),pytest.raises(video.Cancelled):execute([src],[Step('gray')])
    assert list(tmp_path.iterdir())==[src]


@pytest.fixture
def movie(tmp_path,media_engines):
    src=tmp_path/'movie.mp4'
    subprocess.run([video.executable('ffmpeg'),'-v','error','-f','lavfi','-i','testsrc2=size=96x64:rate=10:duration=1',
        '-f','lavfi','-i','sine=frequency=400:duration=1','-c:v','libx264','-c:a','aac','-shortest',str(src)],
        capture_output=True,check=True,creationflags=video.CREATION_FLAGS)
    return src


def test_real_video_chain_duration_geometry_and_sound(movie):
    out=execute([movie],[Step('crop',1.),Step('resize',48),Step('mute'),Step('convert','WEBM')])[0]
    info=video.probe(out)
    assert (info.width,info.height)==(48,48) and not info.has_audio
    assert abs(info.duration-1)<.12


def test_real_audio_chain(movie):
    from dragshift import audio
    out=execute([movie],[Step('convert','WAV'),Step('volume',-6.),Step('fade',.1),Step('convert','FLAC')])[0]
    info=audio.probe(out)
    assert out.suffix=='.flac' and abs(info.duration-1)<.12


def test_invert_and_reverse_are_real_ordered_animation_steps(tmp_path):
    source=tmp_path/'animated.gif'
    Image.new('RGB',(32,24),'red').save(source,save_all=True,
        append_images=[Image.new('RGB',(32,24),'blue')],duration=[80,170],loop=2)
    result=execute([source],[Step('invert'),Step('reverse')])[0]
    with Image.open(result) as image:
        assert image.n_frames==2 and image.info['duration']==170
        assert image.convert('RGB').getpixel((10,10))==(255,255,0)
        image.seek(1);assert image.info['duration']==80
        assert image.convert('RGB').getpixel((10,10))==(0,255,255)


def test_file_branch_retains_rename_for_mixed_and_unknown_files():
    for context in (Context('mixed','',2),Context('unknown','BIN'),Context('folder','')):
        process=entries(context)[1].children
        group=next(entry for entry in process if entry.key=='pack')
        assert any(entry.tool_key=='tool:Rename' and entry.terminal=='tool' for entry in group.children)


def menu(qt_session,tmp_path,monkeypatch):
    from dragshift.branch_menu import BranchMenu
    from dragshift import glass
    monkeypatch.setattr(glass,'capture_background',lambda *_:None)
    instance=BranchMenu(lambda _: {},lambda _:'test')
    paths=[str(image(tmp_path))]
    instance.popup(QPoint(600,400),paths)
    instance.frame.stop()
    return instance,paths


def test_navigation_back_restores_plan_and_hover_does_not_execute(qt_session,tmp_path,monkeypatch):
    instance,_=menu(qt_session,tmp_path,monkeypatch)
    spy=QSignalSpy(instance.activated)
    instance.navigate(1) # process
    instance.navigate(0) # resize
    instance.navigate(0) # 640
    assert instance.steps==(Step('resize',640),)
    assert spy.count()==0
    instance.back()
    assert instance.steps==()
    instance.close_menu()


def test_stationary_center_does_not_reverse_new_branch(qt_session,tmp_path,monkeypatch):
    instance,_=menu(qt_session,tmp_path,monkeypatch)
    instance.navigate(1)
    depth=len(instance.levels)
    instance._lock_until=0
    instance.pointer_move(instance.level.center,1)
    instance.pointer_move(instance.level.center,2)
    assert len(instance.levels)==depth
    instance.close_menu()


def test_keyboard_navigation_is_not_undone_by_stationary_pointer(qt_session,tmp_path,monkeypatch):
    from dragshift.branch_menu import QCursor
    instance,paths=menu(qt_session,tmp_path,monkeypatch)
    instance.popup(QPoint(400,400),paths,practice=True);instance.frame.stop()
    position=instance.mapToGlobal(QPoint(400,400))
    monkeypatch.setattr(QCursor,'pos',lambda:position)
    instance.navigate(1)
    depth=len(instance.levels)
    instance._lock_until=0
    clock=[10.]
    monkeypatch.setattr('dragshift.branch_menu.time.monotonic',lambda:clock[0])
    for value in (10.,11.,12.):
        clock[0]=value
        instance._tick()
    assert len(instance.levels)==depth
    instance.close_menu()


def test_non_composited_window_does_not_cover_the_entire_screen(qt_session,tmp_path,monkeypatch):
    from dragshift import glass
    instance,_=menu(qt_session,tmp_path,monkeypatch)
    regions=[]
    monkeypatch.setattr(glass,'no_compositor',lambda:True)
    monkeypatch.setattr(glass,'apply_shape',lambda widget,path:regions.append(path))
    instance._shape()
    assert regions and not regions[-1].contains(QPointF(instance.width()-1,instance.height()/2))
    assert regions[-1].contains(QPointF(*instance.level.center))
    instance.close_menu()


def test_drop_rejects_different_final_files(qt_session,tmp_path,monkeypatch):
    instance,_=menu(qt_session,tmp_path,monkeypatch)
    instance.navigate(1);instance.navigate(0);instance.navigate(0)
    mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(image(tmp_path,'other.png')))])
    x,y=instance.level.center
    event=QDropEvent(QPointF(x,y-110),Qt.CopyAction,mime,Qt.LeftButton,Qt.AltModifier)
    spy=QSignalSpy(instance.activated);instance.dropEvent(event);qt_session.processEvents()
    assert not event.isAccepted() and spy.count()==0


def test_terminal_drop_dispatches_exactly_once(qt_session,tmp_path,monkeypatch):
    instance,paths=menu(qt_session,tmp_path,monkeypatch)
    instance.navigate(1);instance.navigate(0);instance.navigate(0)
    mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(paths[0])])
    x,y=instance.level.center
    event=QDropEvent(QPointF(x,y-110),Qt.CopyAction,mime,Qt.LeftButton,Qt.AltModifier)
    spy=QSignalSpy(instance.activated);instance.dropEvent(event);qt_session.processEvents()
    assert event.isAccepted() and spy.count()==1
    assert spy.at(0)[0].steps==(Step('resize',640),) and spy.at(0)[1]==paths


def test_review_numeric_edit_and_recipe_round_trip(qt_session,tmp_path,monkeypatch):
    from dragshift.branch_tools import FlowReviewWindow,RecipeStore
    from dragshift.settings import Settings
    monkeypatch.setenv('SWIPE4REST_DATA_DIR',str(tmp_path/'profile'))
    src=image(tmp_path)
    settings=Settings()
    store=RecipeStore(settings);store.save('Web',[Step('resize',120),Step('convert','WEBP')],'folder')
    assert store.load()==[('Web',(Step('resize',120),Step('convert','WEBP')),'folder')]
    window=FlowReviewWindow([str(src)],[Step('resize',120)],lambda *_:None,settings)
    window.value.setValue(240)
    assert window.steps==[Step('resize',240)]
    assert window.run_button.isEnabled()
    window.present();qt_session.processEvents();window.close()


def test_practice_launch_forwards_training_request_to_running_instance(qt_session,monkeypatch):
    from dragshift import app
    sent=[]
    class ExistingApplication:
        def __init__(self,*_):pass
        def __getattr__(self,name):return lambda *_:None
    monkeypatch.setattr(app,'Swipe4RestQApplication',ExistingApplication)
    monkeypatch.setattr(app,'setup_logging',lambda:None)
    monkeypatch.setattr(app,'mac_setup',lambda *_:None)
    monkeypatch.setattr('dragshift.branch_fonts.register',lambda:None)
    monkeypatch.setattr('dragshift.i18n.install',lambda *_:None)
    monkeypatch.setattr(app,'make_icon',lambda:None)
    monkeypatch.setattr(app,'send_to_running',lambda payload:sent.append(payload) or True)
    assert app.main(['Swipe4Rest','--practice','--quiet'])==0
    assert sent==[{'show':False,'practice':True}]
