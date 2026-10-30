# Swipe4Rest

**Swipe forest. Swipe for rest.** A local file converter/editor whose tools unfold as branches under a dragged file.

Independent experimental application by [Vokanzaa](https://github.com/Vokanzaa), with separate releases, executable, settings and integration. It can coexist with DragShift. Original source attribution is retained in [CREDITS.md](CREDITS.md) and [LICENSE](LICENSE).

## Download

Get the native package from [Releases](https://github.com/Vokanzaa/Swipe4Rest/releases). Windows: `Swipe4Rest-Setup.exe` (installer) or `Swipe4Rest.exe` (portable). macOS: Apple Silicon / Intel DMG. Linux: Debian/Ubuntu x64 DEB. Packages include local engines. Source ZIP/TAR downloads contain source, not an installed application.

First release: **0.1.0**, an interface experiment. It does not replace DragShift or install its updates. Releases require successful Windows, both Mac and Linux jobs. macOS is ad-hoc signed unless a Developer ID is configured. Native drag on Linux requires X11; Wayland users can explicitly open files with the app.

## Use

1. Start the app; it stays in the notification area/menu bar.
2. Drag files and hold **Alt / Option**. This avoids competing with DragShift's Shift trigger. Choose Shift or Ctrl in Swipe4Rest settings if desired.
3. Move left to **Convert**, right to **Process**. A pause or deliberate turn unfolds a branch. Example: Process → Size → 1920 → Convert → For screen → WebP.
4. Add more steps, then release on **Save result** to run the chain. Only final results are saved beside the first source; multiple outputs get one dedicated folder. Originals are unchanged.
5. Release on **Configure chain** for numerical values, reordering, search and recipes. Advanced editors are explicit final branches.

The center returns one level; returning after an action removes that action. Escape or releasing outside an endpoint cancels. Click mode supports 1–8 / arrows / Enter, Backspace, F for search, R for recipes, F1 for practice. Open files with Swipe4Rest or pass file paths on its command line for click mode. `--practice` opens training without processing files.

## Tools

- Images: resize, crop, colour, annotation, redaction, conversion and one plan for a series.
- Animation: numbered frames → one GIF; retain animated frames/timing; extract every frame; GIF/video conversion.
- Media: trim, crop/resize, rotate, mute, compression, audio extraction/editing, normalization and fades.
- Creative: Melt Datamosh, Distort with strength controls/sound distortion, Telegram emoji.
- Lenticular: input fitting, interlacing, projects and native print, including streamed large rasters.
- Documents/archives: PDF operations, ZIP/7Z packing, contents/extraction.
- Workflows: compatible branches, numerical review, named JSON recipes, optional folder/path completion, light/dark frosted tree, adjustable gesture pause/scale.

[RESEARCH.md](RESEARCH.md) distinguishes implemented features, source reuse and future ideas. File gestures complement the interactive controls needed for timelines, drawing, print calibration and passwords.

## Build

Python 3.12+: `pip install -r requirements.txt pyinstaller pytest`. Stage engines with `python packaging/media_engines.py --stage` (Unix prerequisites in that script). Run `python -m pytest`, then `pyinstaller Swipe4Rest.spec --noconfirm`. Windows `ONEFILE=1` builds the portable EXE; Inno Setup compiles `installer/Swipe4Rest.iss`. All native targets are in `.github/workflows/build.yml`.

The internal Python package remains `dragshift` for tested engine imports. Product settings/IPC are independent. Windows portable profile: `data/` beside the EXE; source runs: experiment `data/`; Mac/Linux: their own Swipe4Rest app-data directory. Processing needs no uploads or cloud account.

## License

MIT for application source with inherited attribution. Third-party components retain their licenses: [THIRD_PARTY.md](THIRD_PARTY.md).
