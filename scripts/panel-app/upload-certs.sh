#!/usr/bin/env bash
# Upload the Samsung certificates the frame's app is signed with to the
# server, once (and again when they are renewed). The server keeps them in
# its data directory only and builds and signs the app itself (docs/WAKE.md).
#
#   scripts/panel-app/upload-certs.sh [TOKEN] [--server URL] [--dir DIR]
#
# DIR (default ~/SamsungCertificate/frame) holds the profile from Tizen
# Studio's Certificate Manager, author.p12 and distributor.p12, and a
# `.password` file with their password. TOKEN is the server's API token
# (FRAME_API_TOKEN), if it has one. Never commit these files.
set -euo pipefail

token=""
server=${FRAME_SERVER:-http://192.100.3.185:8099}
dir=$HOME/SamsungCertificate/frame
while [ $# -gt 0 ]; do
  case $1 in
    --server) server=$2; shift 2 ;;
    --dir) dir=$2; shift 2 ;;
    -*) echo "unknown option $1" >&2; exit 2 ;;
    *) token=$1; shift ;;
  esac
done
server=${server%/}

for file in author.p12 distributor.p12 .password; do
  if [ ! -f "$dir/$file" ]; then
    echo "missing $dir/$file" >&2
    exit 1
  fi
done

auth=()
if [ -n "$token" ]; then
  auth=(-H "Authorization: Bearer $token")
fi
if ! reply=$(curl -sS --fail-with-body -X PUT ${auth[@]+"${auth[@]}"} \
  -F "author=@$dir/author.p12" \
  -F "distributor=@$dir/distributor.p12" \
  -F "password=<$dir/.password" \
  "$server/api/device/app/certificates"); then
  echo "$reply" >&2
  exit 1
fi
printf '%s' "$reply" |
  python3 -c "$(cat <<'PY'
import json, sys
app = json.load(sys.stdin)
for cert in app["certificates"]:
    print(cert["role"].ljust(12), "valid until", cert["expires_at"])
package = app.get("package")
print(f"app {package['version']} built and signed on the server" if package else "no app built")
PY
)"
