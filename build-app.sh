#!/bin/zsh
# Builds ~/Applications/Salty Rec.app, a thin launcher around this folder's venv.
set -e
ROOT="${0:A:h}"
APP="$HOME/Applications/Salty Rec.app"
mkdir -p "$ROOT/saltyrec/bin"
command -v ffmpeg >/dev/null || { echo "Install ffmpeg first:  brew install ffmpeg"; exit 1; }
MODEL="$ROOT/models/ggml-small-q5_1.bin"
if [ ! -f "$MODEL" ]; then
  mkdir -p "$ROOT/models"
  echo "Fetching the speech model (190 MB, once)…"
  curl -fL -o "$MODEL" https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small-q5_1.bin
fi
swiftc -O -swift-version 5 "$ROOT/helper/main.swift" -o "$ROOT/saltyrec/bin/saltyrec-helper"
(cd "$ROOT" && uv sync -q)
rm -rf "$APP"; mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
ICON=$(mktemp -d)/icon.iconset; mkdir -p "$ICON"
for s in 16 32 128 256 512; do
  sips -z $s $s "$ROOT/saltyrec/assets/icon.png" --out "$ICON/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) "$ROOT/saltyrec/assets/icon.png" --out "$ICON/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICON" -o "$APP/Contents/Resources/icon.icns"
clang -O2 -DROOT="\"$ROOT\"" "$ROOT/helper/launcher.c" -o "$APP/Contents/MacOS/SaltyRec"
cat > "$APP/Contents/Info.plist" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Salty Rec</string>
  <key>CFBundleDisplayName</key><string>Salty Rec</string>
  <key>CFBundleIdentifier</key><string>com.saltycodestudio.saltyrec</string>
  <key>CFBundleExecutable</key><string>SaltyRec</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSCameraUsageDescription</key><string>Salty Rec shows your camera bubble and records it.</string>
  <key>NSMicrophoneUsageDescription</key><string>Salty Rec records your voice.</string>
</dict></plist>
PL
codesign --force --sign - --identifier com.saltycodestudio.saltyrec "$APP"
echo "Built $APP"
