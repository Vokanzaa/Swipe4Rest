"""Private staging and final-only publication of typed Swipe4Rest workflows."""
from __future__ import annotations

from contextlib import suppress
import os
from pathlib import Path
import shutil
import tempfile

from PIL import Image, ImageOps

from . import animation, audio, convert, imaging, video
from .branch_model import Context, Step, after, context_for
from .util import UserError, unique_path

IMAGE_EDITS = {'resize','crop','rotate','gray','quality','clean'}
VIDEO_EDITS = IMAGE_EDITS | {'mute','trim'}


def _edit_image(image, steps):
    for step in steps:
        video.check_cancel()
        if step.op == 'resize':
            image.thumbnail((int(step.value),int(step.value)),Image.Resampling.LANCZOS)
        elif step.op == 'crop':
            ratio=float(step.value)
            w,h=image.size
            cw,ch=(min(w,round(h*ratio)),min(h,round(w/ratio)))
            image=image.crop(((w-cw)//2,(h-ch)//2,(w-cw)//2+cw,(h-ch)//2+ch))
        elif step.op == 'rotate':
            image=image.rotate(-int(step.value),expand=True)
        elif step.op == 'gray':
            alpha=image.getchannel('A') if 'A' in image.getbands() else None
            image=ImageOps.grayscale(image).convert('RGBA' if alpha is not None else 'RGB')
            if alpha is not None:
                image.putalpha(alpha)
        elif step.op == 'clean':
            clean=Image.new(image.mode,image.size)
            clean.paste(image)
            image=clean
    return image


def _images(paths, steps):
    quality=next((int(s.value) for s in reversed(steps) if s.op=='quality'),90)
    def edit(path):
        animated=animation.is_animated(path)
        target=imaging.target_for(path) if animated else 'PNG'
        # Preserve alpha, composited frame order, durations and looping. Static
        # intermediate frames stay lossless until the requested final encoding.
        return [animation.transform_image(path,'Flow',lambda im:_edit_image(im,steps),target=target,quality=quality)]
    return video.batch(paths,edit)


def _video_edits(src, steps, target='MP4', lossless=False):
    info=video.probe(src)
    video.require_precise_timing()
    vf=[video.square_pixels_filter()]
    af=[]
    duration=info.duration
    mute=any(s.op=='mute' for s in steps)
    clean=any(s.op=='clean' for s in steps)
    crf=23
    for step in steps:
        if step.op=='resize':
            side=int(step.value)
            vf.append(f"scale=w='max(2,trunc(iw*min(1,{side}/max(iw,ih))/2)*2)':h='max(2,trunc(ih*min(1,{side}/max(iw,ih))/2)*2)':flags=lanczos")
        elif step.op=='crop':
            ratio=float(step.value)
            vf.append(f"crop=w='max(2,trunc(min(iw,ih*{ratio})/2)*2)':h='max(2,trunc(min(ih,iw/{ratio})/2)*2)'")
        elif step.op=='rotate':
            vf.extend({90:['transpose=1'],180:['hflip','vflip'],270:['transpose=2']}[step.value])
        elif step.op=='gray':
            vf.append('hue=s=0')
        elif step.op=='quality':
            crf=round(40-(float(step.value)-40)*.4)
        elif step.op=='trim':
            start,end=float(step.value[0]),min(float(step.value[1]),duration)
            if start>=end-.04:
                raise UserError('Выбранный участок находится за концом видео.')
            vf += [f'trim=start={start}:end={end}','setpts=PTS-STARTPTS']
            af += [f'atrim=start={start}:end={end}','asetpts=PTS-STARTPTS']
            duration=end-start
    if Path(src).suffix.lower()=='.gif':
        vf.append(f'fps={animation.gif_rate(src):.8f}')
    with video.export_path(src,'Flow','.'+target.lower()) as (tmp,outs):
        args=video.ffmpeg_args()+[*video.input_options(src),'-i',str(video.local_file(src)),
             '-map',f'0:{info.video_index}','-vf',','.join(vf),'-fps_mode','passthrough',
             '-enc_time_base:v','1:1000000','-bsf:v','setts=duration=DURATION']
        if mute or not info.has_audio:
            args+=['-an']
        else:
            args+=['-map','0:a:0?']
            if af:
                args+=['-af',','.join(af)]
        if lossless:
            args+=['-c:v','ffv1','-level','3','-c:a','pcm_s24le']
        else:
            args+=video._video_codec(target,crf)+['-bf','0']
        if clean:
            args+=['-map_metadata','-1']
        args += [str(tmp)]
        video.run_process(args,duration,'Цепочка: обработка видео…')
    return outs


def _flatten_outputs(outputs):
    files=[]
    for output in outputs:
        path=Path(output)
        if path.is_dir():
            files.extend(sorted((p for p in path.rglob('*') if p.is_file()),key=lambda p:p.as_posix()))
        else:
            files.append(path)
    return files


def _step(paths, state, step, quality=90):
    if step.op=='pack':
        from .archives import pack
        return pack(paths,step.value)
    if step.op in ('convert','animate'):
        if step.op=='animate' or state.kind=='image' and step.value=='GIF' and len(paths)>1:
            from .gif_sequence import export, ordered_paths
            return export(ordered_paths(paths),fps=float(step.value) if step.op=='animate' else 10)
        if state.kind=='image' and step.value=='PDF' and len(paths)>1:
            return convert.images_to_single_pdf(paths)
        if state.kind=='image' and step.value in convert.IMAGE_TARGETS:
            def image_export(path):
                with Image.open(path) as source:
                    extract=source.format=='GIF' and getattr(source,'is_animated',False) and step.value in animation.FRAME_TARGETS
                return convert.convert(path,'image',step.value) if extract else [animation.transform_image(path,'',target=step.value,quality=quality)]
            return video.batch(paths,image_export)
        return video.batch(paths,lambda p:convert.convert(p,state.kind,step.value))
    if step.op=='frame':
        return video.batch(paths,lambda p:video.snapshot(p,float(step.value)))
    if state.kind=='audio':
        options={'target':'WAV','label':'Flow'}
        if step.op=='normalize': options['normalize']=True
        elif step.op=='fade': options.update(fade_in=step.value,fade_out=step.value)
        elif step.op=='volume': options['volume_db']=step.value
        elif step.op=='reverse': options['reverse']=True
        elif step.op=='clean': options['strip_metadata']=True
        return video.batch(paths,lambda p:audio.transform(p,**options))
    if state.kind=='pdf':
        fn={'compress_pdf':lambda p:[imaging.compress_pdf(p)],'rotate_pdf':lambda p:[imaging.rotate_pdf(p)],
            'split_pdf':imaging.split_pdf,'clean':lambda p:[imaging.strip_pdf_metadata(p)]}[step.op]
        return video.batch(paths,fn)
    raise UserError('Это действие пока доступно через отдельный редактор.')


def execute(paths, steps):
    """Run a plan locally. Nothing is published until the whole plan succeeds.

    Sources are hard-linked when possible (read-only inputs), copied otherwise.
    Only the final file/folder is renamed into place, under the shared publication
    lock. The temporary directory owns every intermediate and failed output.
    """
    steps=tuple(steps)
    initial=context_for(paths)
    final=after(initial,steps)
    if not steps:
        return [Path(p) for p in paths]
    originals=[Path(p).resolve(strict=True) for p in paths]
    parent=originals[0].parent
    video.check_cancel()
    with tempfile.TemporaryDirectory(prefix='.~swipe4rest-',dir=parent) as temporary:
        stage=Path(temporary)
        current=[]
        for index,src in enumerate(originals):
            video.check_cancel()
            folder=stage/f'input-{index:06d}'
            folder.mkdir()
            dest=folder/src.name
            if src.is_dir():
                # Do not follow directory reparse points into unrelated trees.
                from .archives import packing_sources
                packing_sources([src])
                shutil.copytree(src,dest,symlinks=True)
            else:
                try:
                    os.link(src,dest)
                except OSError:
                    shutil.copy2(src,dest)
            current.append(dest)
        state=initial
        index=0
        quality=90
        while index<len(steps):
            video.check_cancel()
            step=steps[index]
            if state.kind=='image' and step.op in IMAGE_EDITS:
                stop=index
                while stop<len(steps) and steps[stop].op in IMAGE_EDITS:
                    if steps[stop].op=='quality': quality=int(steps[stop].value)
                    stop+=1
                current=_images(current,steps[index:stop])
                state=after(state,steps[index:stop])
                index=stop
                continue
            if state.kind=='video' and step.op in VIDEO_EDITS:
                stop=index
                while stop<len(steps) and steps[stop].op in VIDEO_EDITS:
                    stop+=1
                target=state.ext if state.ext in ('MP4','MKV','MOV','AVI','WEBM') else 'MP4'
                edits=steps[index:stop]
                consume=stop<len(steps) and steps[stop].op=='convert' and steps[stop].value in ('MP4','MKV','MOV','AVI','WEBM')
                if consume:
                    target=steps[stop].value
                # Finish contiguous geometry/colour edits in one encode. A later
                # non-video operation receives lossless video/audio intermediates.
                lossless=stop<len(steps) and not consume and steps[stop].op!='pack'
                current=video.batch(current,lambda p:_video_edits(p,edits,'MKV' if lossless else target,lossless))
                state=after(state,edits)
                if consume:
                    state=after(state,[steps[stop]])
                    stop+=1
                index=stop
                continue
            current=_flatten_outputs(_step(current,state,step,quality))
            state=after(state,[step])
            index+=1
        # Restore the requested output container after lossless image/audio edits.
        if final.kind in ('image','audio') and final.ext and all(p.suffix[1:].upper()!=final.ext for p in current):
            if final.kind=='image':
                current=video.batch(current,lambda p:[animation.transform_image(p,'',target=final.ext,quality=quality)])
            else:
                current=video.batch(current,lambda p:audio.convert_audio(p,final.ext))
        if not current:
            raise UserError('Цепочка не создала файлов.')
        bundle=stage/'result'
        bundle.mkdir()
        for index,path in enumerate(current):
            video.check_cancel()
            if not path.resolve().is_relative_to(stage.resolve()):
                raise UserError('Результат вышел за пределы временной папки.')
            dest=unique_path(bundle/path.name)
            shutil.move(str(path),str(dest))
        video.check_cancel()
        with video._publish_lock:
            video.check_cancel()
            files=list(bundle.iterdir())
            if len(files)==1 and files[0].is_file():
                out=unique_path(parent/f'{originals[0].stem} Swipe4Rest{files[0].suffix}')
                files[0].rename(out)
            else:
                out=unique_path(parent/f'{originals[0].stem} Swipe4Rest')
                bundle.rename(out)
        # Publication is the commit point. Never turn a completed result into a
        # cancellation error or let a completion callback orphan this output.
        return [out]
