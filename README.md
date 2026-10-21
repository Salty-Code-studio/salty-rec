# Salty Rec

A free, open-source screen and camera recorder in the spirit of Loom. Record your screen with your face in a bubble, draw on the screen, then trim, cut silences and ums, and get a transcript. Speech recognition runs on your own device and nothing gets uploaded.

Made by [Salty Code Studio](https://saltycodestudio.com). MIT licensed.

## Pick your version

| | Browser | Windows app | Mac app |
|---|---|---|---|
| Install | None, open the link | Download, unzip, run | Build script |
| Screen + camera bubble | Yes | Yes | Yes |
| Bubble shapes and sizes | Yes | Yes | Yes |
| Draw on screen | On the preview | Anywhere on screen | Anywhere on screen |
| Computer sound | Tab or screen sound when the browser offers it | Yes | Yes |
| Shortcuts from any app | No | Alt+Shift+R / P / D / X | ⌥⇧R / P / D / X |
| Transcript, remove ums, remove silences, trim | No | Yes, on your PC | Yes, on your Mac |
| Phones | Camera only | | |

### Browser
Open **https://salty-code-studio.github.io/salty-rec/** in Chrome or Edge. On a phone you can record your camera. Phones don't let websites record the screen, so use the phone's own screen recorder for that. You can add the page to your home screen.

### Windows
1. Go to [Releases](../../releases/latest) and download `SaltyRec-Windows.zip`.
2. Unzip it anywhere, open the folder and run `SaltyRec.exe`.
3. Windows SmartScreen may warn because the app isn't signed. Choose **More info**, then **Run anyway**.

Everything is inside the zip, including ffmpeg and the speech model. Recordings go to `Videos\Salty Rec`.

### Mac (Apple Silicon)
You need [Homebrew](https://brew.sh), then:
```sh
brew install ffmpeg uv
git clone https://github.com/Salty-Code-studio/salty-rec.git
cd salty-rec && ./build-app.sh
```
This builds `~/Applications/Salty Rec.app` and fetches the speech model once (190 MB). On first use, macOS asks for Camera, Microphone and Screen Recording access. Allow all three. Recordings go to `Movies/Salty Rec`.

## Using it
- **Bubble:** drag it anywhere. Double-click to change its size, or right-click for Round, Square, Wide or Tall. You see yourself in it before and during the recording.
- **Recording:** a 3-2-1 countdown, then a small control bar with Pause, Draw, Restart, Cancel and Stop. The control bar stays out of the video.
- **Drawing:** coral pen. Strokes fade after a few seconds. Right-click clears them and Esc stops drawing.
- **Library:** search across titles and transcripts, play at any speed, rename, copy the file, export with captions.
- **Edits:** Trim, Remove silences, Remove ums and Undo edits. The original take is kept until you undo.

## Transcripts
Salty Rec has [whisper.cpp](https://github.com/ggml-org/whisper.cpp) built in, through [pywhispercpp](https://github.com/absadiki/pywhispercpp), with the multilingual `small` model. It works offline and picks the language on its own. Word timing is what powers Remove ums. If you have a bigger `ggml-*.bin` model, set `SALTYREC_WHISPER_MODELS` to its folder and it will be used instead.

## Share links (optional, self-hosted)
Salty Rec can upload a light copy to your own Cloudflare account and give you a private link with a player, captions and a view count. This is off until you set it up:
1. `cd worker`, then create an R2 bucket called `salty-rec` and run `npx wrangler deploy`.
2. Pick a long random token and run `npx wrangler secret put UPLOAD_TOKEN`.
3. Create a `config.json` with `{"share_base": "https://<your-worker>.workers.dev", "token": "<your token>"}` in:
   - Mac: `~/Library/Application Support/Salty Rec/`
   - Windows: `%APPDATA%\Salty Rec\`

The Share buttons appear once that file exists. Never commit the token.

## Developing
```sh
uv sync
uv run python -m saltyrec              # run the app
uv run python -m saltyrec --selftest   # checks ffmpeg, capture and speech
```
- `saltyrec/`: the app (PySide6). `recorder.py` holds the capture engines. On a Mac it uses ScreenCaptureKit through `helper/main.swift`. On Windows it uses ffmpeg gdigrab and dshow, with WASAPI loopback (`loopback.py`) for computer sound.
- `web/`: the browser version, deployed to GitHub Pages by `.github/workflows/pages.yml`.
- `packaging/` and `.github/workflows/windows.yml`: the Windows build. Push a tag like `v1.0.1` to publish a release.
- `worker/`: the optional share-link server (Cloudflare Workers + R2).

## Credits
Built with Qt for Python, FFmpeg (the Windows zip ships an LGPL/GPL build from gyan.dev, and its license is included), whisper.cpp and OpenAI's Whisper models (MIT), and SoundCard. The idea of shipping the speech engine inside the app comes from [OpenWhispr](https://github.com/OpenWhispr/openwhispr) (MIT).
