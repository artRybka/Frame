#!/usr/bin/env bash
# Assemble a self-contained add-on folder (add-on files + server source).
#
#   scripts/bundle-addon.sh [OUT_DIR]          default: dist/frame
#
# Copy the result to the Home Assistant "addons" share (Samba or SSH add-on),
# e.g.  scp -r dist/frame root@homeassistant.local:/addons/
# then Settings -> Add-ons -> Add-on Store -> ⋮ -> Check for updates; it shows
# up under "Local add-ons" and is built on the HA box from this copy.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${1:-$root/dist/frame}"

rm -rf "$out"
mkdir -p "$out/server"
cp -r "$root/ha-addon/." "$out/"
cp -r "$root/server/pyproject.toml" "$root/server/README.md" "$root/server/src" "$out/server/"
# Local add-ons need a distinct slug from the repository one.
sed -i.bak 's/^slug: frame$/slug: frame_local/; s/^name: Frame$/name: Frame (local)/' "$out/config.yaml"
rm -f "$out/config.yaml.bak"
echo "add-on bundled in $out"
