# NiSH Player

A small Windows player for songs and stems. Drop in a full song, a karaoke track or a set
of stems (for example from [Stem Splitter](https://github.com/nish-vibes/stem-splitter)),
then change the speed and pitch of everything at once and export the result.

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

- **From YouTube…**: paste a link and NiSH Player saves the best-quality audio exactly as
  YouTube delivers it (no re-encoding, no suffix) in its own folder. Optionally it also makes a
  **karaoke version** (`_NoVox`) and **6 stems** (`_VOX`, `_DRM`, `_BASS`, `_GTR`, `_KEYS`, `_MISC`,
  in a `<name> stems` folder) with the same AI as NiSH Stem Splitter, and can **tune them to
  A = 440 Hz (beta, varispeed)** – plus an extra tuned copy of the original (`_440hz`) if you like. Name the
  file yourself or leave it blank to use the video title. The cogwheel sets the suffixes, the stems
  folder name and the format (FLAC by default; WAV, MP3 320 or Opus 256). **Add to workspace**
  loads the result straight into the player: the stems when you made stems (the karaoke version is
  saved but not loaded with them), otherwise the karaoke version. A **project** (`<name>.nish`) is
  saved next to the stems (or next to the karaoke file), so the song is easy to find and open again.
  The first split downloads the AI model once.

- **Projects**: **Save…** (Ctrl+S; Ctrl+Shift+S saves a copy under a new name) writes a small
  `.nish` file with the tracks, their names, order, volume, mute and solo, speed, pitch, fine-tune,
  Auto 440, the loop area and the master fader. The audio isn't copied: the project points to the
  files next to it, so a song folder with its project can be moved or copied and still opens.
  **Open…** opens audio files or a project, and the **▾** next to it lists your recent projects.
  Double-clicking a `.nish` file opens it in NiSH Player (in the running one, if it's open). If a
  saved project has changes, NiSH Player asks before closing it.

- **Export folder**: exports go to your Desktop until you pick another folder with **Change…**;
  that folder then becomes your default.
- **Updates** are always manual: the cogwheel in the top right shows your version and has
  **Check for updates** → **Download**. When the download is done it says so, and **Close and update**
  closes the app, swaps in the new version and starts it again; your settings (export folder, track names, YouTube settings) are kept
  in `%LOCALAPPDATA%\NiSH Player` and are never touched. If YouTube downloads fail five times on
  one day, the cogwheel turns amber and suggests checking for an update.

Keyboard: **Space** play/pause, **Home** back to the start, **Ctrl+S** save the project,
**S** / **M** solo / mute the selected track (**Ctrl+click** on S: solo only that track).

## Building it yourself

The GitHub workflow builds the Windows app: it runs the engine tests, builds the `.exe`
with PyInstaller (bundling ffmpeg with Rubber Band), starts the app and clicks through every
control, then zips it. Raising the number in `VERSION` publishes a new release.

Local run (needs Python 3.12 and ffmpeg on PATH):

```
pip install -r requirements.txt
python app.py
python tests/test_engine.py
python tests/test_splitter.py
```

The YouTube/stems part also needs PyTorch (`pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu`).
The build runs every Monday as well, so new YouTube fixes in yt-dlp get published automatically.

Track names, YouTube settings and the log file are stored in `%LOCALAPPDATA%\NiSH Player`.
