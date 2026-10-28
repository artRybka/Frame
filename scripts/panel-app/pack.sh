#!/usr/bin/env bash
# Build and sign the Frame app for the panel (Samsung "Custom" source, see
# docs/WAKE.md) and optionally upload it to the server, which serves it to
# the panel together with sssp_config.xml.
#
#   scripts/panel-app/pack.sh VERSION [--server URL] [--upload TOKEN]
#
# The package must be signed with the Samsung certificate profile "frame"
# (Tizen Studio, Partner level, the panel's DUID), which lives on Mateusz's
# Mac. The app's logic is loaded from the server at every start, so a new
# package is only needed for changes to config.xml or index.html.
set -euo pipefail

version=${1:?usage: pack.sh VERSION [--server URL] [--upload TOKEN]}
shift
server=${FRAME_SERVER:-http://192.100.3.185:8099}
token=""
while [ $# -gt 0 ]; do
  case $1 in
    --server) server=$2; shift 2 ;;
    --upload) token=$2; shift 2 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
server=${server%/}

root=$(cd "$(dirname "$0")/../.." && pwd)
src=$root/server/src/frame_server/web/panel_app
out=$root/dist/panel-app
tizen=${TIZEN:-$HOME/tizen-studio/tools/ide/bin/tizen}

build=$(mktemp -d)
trap 'rm -rf "$build"' EXIT
cp "$src/index.html" "$src/app.js" "$build/"
sed "s/version=\"[^\"]*\" viewmodes/version=\"$version\" viewmodes/" "$src/config.xml" > "$build/config.xml"
cat > "$build/config.js" <<JS
window.FRAME_SERVER = "$server";
window.FRAME_BUILD = "$version";
JS
# The panel needs an icon; any small PNG will do.
python3 -c 'import base64,sys; open(sys.argv[1],"wb").write(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC"))' "$build/icon.png"

"$tizen" package -t wgt -s frame -- "$build" >/dev/null
mkdir -p "$out"
cp "$build/Frame.wgt" "$out/"
size=$(wc -c < "$out/Frame.wgt" | tr -d ' ')
echo "$out/Frame.wgt ($size bytes), version $version, server $server"

if [ -n "$token" ]; then
  curl -fsS -X PUT -H "Authorization: Bearer $token" \
    -H "Content-Type: application/octet-stream" \
    --data-binary "@$out/Frame.wgt" \
    "$server/api/device/app/package?version=$version"
  echo
fi
