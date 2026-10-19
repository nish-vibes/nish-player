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
  loads the result straight into the player. The first split downloads the AI model once.

Keyboard: **Space** play/pause, **Home** back to the start.

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
