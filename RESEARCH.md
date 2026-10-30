# Swipe4Rest: gesture menus and file workflows

Reviewed 30 October 2026. Swipe4Rest is an independent project developed from the extended DragShift codebase; original MIT attribution is retained in LICENSE.

| Reference | Applicable capability | Integration |
|---|---|---|
| [Kando](https://github.com/kando-menu/kando) | Nested marking menus; pause/corner recognition; jitter/dead zone; parent anchors; fixed directions | Detector math ported from commit `63c2502c11d31ca709c6496642745c75dc37e8a2`, MIT. Full permission in `dragshift/assets/kando-MIT.txt`. Tree navigation and Qt rendering implemented for file workflows. |
| [Kando workflow editor](https://kando.menu/creating-menus/) | Ordered workflows, configurable behavior and styles | Typed plans, numerical review/reordering, separate pause/scale/trigger settings, light/dark tree. Kando CSS themes and external macro definitions are not compatible imports. |
| [Fly-Pie](https://github.com/Schneegans/Fly-Pie) | Click/gesture alternatives and interactive learning | Practice with a dummy context and no processing. Implemented independently; no Fly-Pie source or assets copied. |
| [File Converter](https://file-converter.io/) | Context-sensitive batch presets | Compatible action filtering, named JSON recipes and one plan for a series. Existing conversion engines reused; GPL application source not incorporated. |
| [Flow Launcher](https://github.com/Flow-Launcher/Flow.Launcher) | Search instead of memorizing gestures | Token/subsequence action search, independently implemented. No system indexing or plugin backend bundled. |
| [Shutter Encoder](https://www.shutterencoder.com/documentation/) | Encode settings, image sequences, batches, output handling | Existing media engines retained; adjacent video edits share an encode; naturally ordered frames, cancellation and final-only publication; optional folder/path completion. No Shutter Encoder code copied. |

The first root stays stable: conversion left, processing right. Save later appears above, numerical review below. Navigation edits a plan; a terminal drop/click executes it. Intermediates remain private until the full chain succeeds. Backtracking restores the former plan snapshot.

## Useful follow-up paths

| Result | Suitable next steps |
|---|---|
| Image / images | resize → crop → rotate/gray → WebP/JPG/AVIF → ZIP; frames → one GIF; images → one PDF; Interlace/annotation as configured final editors |
| GIF | crop/resize preserving frames → video; or extract every frame → edit the series → GIF/PDF/ZIP; Telegram emoji as configured final export |
| Video | crop/resize/gray/trim/mute → MP4/WebM; extract audio → normalize/fade/volume → FLAC/MP3; save a frame → image actions |
| Audio | volume/normalize/fade/reverse → WAV/FLAC/MP3/Opus → ZIP; glitch and multi-file transition editors |
| PDF | rotate/compress/split → page images → image actions or animation; password protection as final editor |
| Archive / mixed files | ZIP/7Z; existing contents/extraction. Extracted executables are never run. |

Datamosh, Distort, sound distortion, Interlace and Telegram exports remain explicit editor endpoints. Parameters are not guessed during a drag. Precise drawing, print calibration, audiovisual timelines and passwords need interactive controls.

Further candidates: recipes directly in tree sectors, pen/touch layouts, per-application menus, thumbnails/waveforms, GPU previews and saved numerical defaults. Clipboard-history collection, arbitrary shell macros, window switching, gamepads, achievements and sound themes are not in this release. This is a file utility and does not claim to contain all of Kando.

The user chose **Swipe4Rest**: “swipe forest” and “swipe for rest”. Exact-name web searches returned no results on the review date; this is preliminary screening, not trademark clearance.
