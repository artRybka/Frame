#!/usr/bin/env bash
# Build and sign WakeProbe with the Samsung certificate profile, then write
# sssp_config.xml next to the package for the panel's Custom App launcher.
#
#   scripts/wakeprobe/pack.sh VERSION [OUT_DIR]    default OUT_DIR: dist/wakeprobe
#
# Needs Tizen Studio with the "frame" Samsung certificate profile (Partner,
# DUID of the panel); see docs/WAKE.md.
set -euo pipefail

version=${1:?usage: pack.sh VERSION [OUT_DIR]}
out=${2:-dist/wakeprobe}
src=$(cd "$(dirname "$0")" && pwd)
tizen=${TIZEN:-$HOME/tizen-studio/tools/ide/bin/tizen}

build=$(mktemp -d)
trap 'rm -rf "$build"' EXIT
cp "$src/index.html" "$src/main.js" "$build/"
sed "s/version=\"[^\"]*\" viewmodes/version=\"$version\" viewmodes/" "$src/config.xml" > "$build/config.xml"
sed -i '' "s/__BUILD__/$version/g" "$build/index.html" "$build/main.js" 2>/dev/null \
  || sed -i "s/__BUILD__/$version/g" "$build/index.html" "$build/main.js"
# The panel needs an icon; any small PNG will do.
python3 -c 'import base64,sys; open(sys.argv[1],"wb").write(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC"))' "$build/icon.png"

"$tizen" package -t wgt -s frame -- "$build" >/dev/null
mkdir -p "$out"
cp "$build/WakeProbe.wgt" "$out/"
# Loaded at run time from the server, so it changes without re-signing.
cp "$src/remote.js" "$out/"
size=$(wc -c < "$out/WakeProbe.wgt" | tr -d ' ')
cat > "$out/sssp_config.xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<widget>
<ver>$version</ver>
<size>$size</size>
<widgetname>WakeProbe</widgetname>
</widget>
EOF
echo "$out/WakeProbe.wgt ($size bytes), $out/sssp_config.xml"
