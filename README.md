# NiSH Player

A small Windows player for songs and stems. Drop in a full song, a karaoke track or a set
of stems, change the speed and pitch of everything at once and export the result. **Split**
makes the stems for you: from a YouTube link or a file on your computer.

No installer and no admin rights: unzip and run `NiSHPlayer.exe`.

## Download

Get `NiSHPlayer-windows.zip` from the [latest release](https://github.com/nish-vibes/nish-player/releases/latest),
unzip it anywhere (Desktop, Documents, a USB stick) and double-click `NiSHPlayer.exe`.
Windows may show "Windows protected your PC" the first time because the app isn't signed:
click **More info → Run anyway**.

## What it does

- **Drag and drop** audio files (WAV, FLAC, MP3, M4A, OGG, …) or a whole folder onto the window.
- **One lane per track** with a waveform, a shared playhead, **M**ute, **S**olo and volume.
  Click a waveform to jump there.
- **Rename tracks** by clicking the name. The file itself is never renamed; the app just
  remembers the name you gave it.
- **Speed** (0.5×–1.5×) and **Pitch** (±6 semitones) for all tracks together, without one
  changing the other. You hear the change straight away while you drag; a moment after you
  let go, a high-quality version (Rubber Band) takes over seamlessly at the same spot.
- **Ctrl+click** any slider (or the master fader) to put it back to its default.
- **Fine-tune** (±50 cents) and **Auto 440 (beta)**: Auto 440 measures how far the song is
  from A = 440 Hz and sets the fine-tuning slider for you (it turns green and locks while Auto 440
  is on); if it can't detect the tuning it tells you and turns itself off. Fine-tuning works like a
  turntable (varispeed), so it slightly changes the length of the track. Speed and Pitch use Rubber Band.
- **Master fader** with L/R level meters and a **CLIP** light that stays on until you click it.
  A gentle safety limiter keeps the sound from distorting.
- **Export** the mix as you hear it (mute, solo and volume applied) or each track separately,
  as WAV (24-bit), FLAC or MP3 320 kbps, with speed, pitch and tuning included. Export always
  renders from the original files at full quality.

- **Split** (top right): choose **YouTube** (paste a link) or **File on computer** (Browse, or
  drop an audio file onto the window), then what to make:
  - **Original**: the audio as it is. From YouTube it is always kept, saved exactly as YouTube
    delivers it (usually Opus, not re-encoded); a file of yours is copied into the song folder.
  - **Karaoke**: the song without vocals, as MP3 320.
  - **4 Stems** (vocals, drums, bass, other: the best quality) or **6 Stems** (also guitar and
    keys/piano).
  - **Auto 440** under each choice tunes those files to A = 440 Hz (varispeed). Under Original it
    adds a tuned copy next to the original.

  Everything goes into one song folder (on the Desktop unless you pick another place with
  **Change project location…**):

  ```
  My Song\
    ~My Song.nish                      the project (sorts to the top)
    My Song Original.opus
    My Song Auto440.flac
    My Song KARAOKE Auto440.mp3
    Separated Stems - My Song\
      My Song VOX Auto440.flac   (DRM, BASS, GTR, KEYS, MISC)
  ```

  Name the song yourself or leave the name blank to use the video title or file name. The
  cogwheel sets the file format (FLAC by default; WAV, MP3 320 or Opus), the name tags and the
  stems folder name. **Add to workspace** loads the result straight into the player: the stems
  if you made stems, otherwise the karaoke file, otherwise the (tuned) original. The AI models
  (Demucs) come with the app, so splitting works on the first try, even offline.

- **Projects**: **Save project** (Ctrl+S; Ctrl+Shift+S saves a copy under a new name) writes a small
  `.nish` file with the tracks, their names, order, volume, mute and solo, speed, pitch, fine-tune,
  Auto 440, volume automation, the loop area and the master fader. The audio isn't copied: the
  project points to the files next to it, so a song folder with its project can be moved or
  copied and still opens.
  **Open project** opens audio files or a project, and the **▾** next to it lists your recent projects.
  Double-clicking a `.nish` file opens it in NiSH Player (in the running one, if it's open). If a
  saved project has changes, NiSH Player asks before closing it.

- **Loop area**: drag on the time ruler above the tracks to mark an area; the loop button (next
  to play) plays it over and over, with a short **Fade** at both ends (0–2 s). A click on the
  ruler still jumps there, and **×** clears the area. With loop on, Export writes only the area.
- **Volume automation**: **A** on a track draws its volume as a line. Click to add a point, drag
  to move it, double-click to delete it. Export follows the line.
- **Track height**: drag the bottom edge of a track to make all tracks taller or lower; the
  compact button makes them as small as possible (**V** then opens a small volume slider).
  Double-click the edge for the normal height.
- **Export folder**: exports of a project go to its song folder. Otherwise they go to your
  Desktop until you pick another folder with **Change…**; that folder then becomes your default.
- **Theme**: dark by default. The cogwheel menu has a **Theme** button that switches between dark
  and light; the app remembers your choice.
- **Updates** are always manual: the cogwheel in the top right shows your version and has
  **Check for updates** → **Download**. When the download is done it says so, and **Close and update**
  closes the app, swaps in the new version and starts it again; your settings (export folder, track names, Split settings) are kept
  in `%LOCALAPPDATA%\NiSH Player` and are never touched. If YouTube downloads fail five times on
  one day, the cogwheel turns amber and suggests checking for an update.

Keyboard: **Space** play/pause, **Home** back to the start, **Ctrl+S** save the project,
**S** / **M** solo / mute the selected track (**Ctrl+click** on S: solo only that track).

## Building it yourself

The GitHub workflow builds the Windows app. It runs the style check (`ruff check .`) and the
tests, builds the `.exe` with PyInstaller (bundling ffmpeg with Rubber Band and the AI models),
starts the app and clicks through every control, then zips it.

- `main` is what users get: raising the number in `VERSION` there publishes a new release.
- `release/<version>` branches (e.g. `release/1.6`) are for fixes to an older version; they
  publish too when `VERSION` is raised.
- Other branches (e.g. `v2`) are built and tested but never published; the zip is kept as a
  build artifact for 14 days.
- The build runs every Monday as well, so new YouTube fixes in yt-dlp get published automatically.

Local run (needs Python 3.12 and ffmpeg with Rubber Band on PATH):

```
pip install -r requirements.txt
python app.py
python tests/test_engine.py
python tests/test_splitter.py
python tests/test_updater.py
python tests/test_colors.py
python app.py --gui-smoketest <folder>
```

The Split part also needs PyTorch (`pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu`).

**Colours** come from the design canvas: `design/colors.css` is its colour file. After changing
colours there, save it over `design/colors.css` and run `python tools/sync_colors.py`, which
updates `theme.py` (`tests/test_colors.py` fails if they don't match).

**Code map**: `app.py` (start-up and main window core), `layout.py` (building the window),
`tracks.py` (tracks, ruler, automation), `speed_pitch.py` (speed, pitch, Auto 440), `project_ui.py`
(projects), `lane.py` (one track), `widgets.py` (fader, switches, field hints), `export_dialog.py`,
`split_ui.py` + `split_choices.py` (the Split dialog), `settings_menu.py` (cogwheel menu),
`engine.py` (audio: decoding, playback, speed/pitch, export), `splitter.py` (download and AI split),
`tuning.py` (Auto 440), `project.py` (.nish files), `settings.py`, `updater.py`, `instance.py`
(one running app), `theme.py` (colours, fonts, icons), `smoketest.py` (the click-through test).

Track names, settings, Split settings and the log file are stored in `%LOCALAPPDATA%\NiSH Player`.
