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
  changing the other. Changes are applied in high quality (Rubber Band) about a second after
  you let go of the slider; playback keeps going at the same spot.
- **Fine tune** (±50 cents) and **Auto 440 (beta)**: Auto 440 measures how far the song is
  from A = 440 Hz and sets the fine tune slider for you (it turns green and locks while Auto 440
  is on). Turn it off and your own fine tune value comes back.
- **Master fader** with L/R level meters and a **CLIP** light that stays on until you click it.
  A gentle safety limiter keeps the sound from distorting.
- **Export** the mix as you hear it (mute, solo and volume applied) or each track separately,
  as WAV (24-bit), FLAC or MP3 320 kbps, with speed, pitch and tuning included. Export always
  renders from the original files at full quality. If pitch shift and Auto 440 are both on,
  the export window points out that combining them can cost a little sound quality.

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
```

Track names and the log file are stored in `%LOCALAPPDATA%\NiSH Player`.
