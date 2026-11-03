#!/bin/bash
# Builds libtailscale, Tailscale's C library (the core of TailscaleKit), for
# the iPhone and the Apple-silicon simulator into ios/Vendor/Tailscale, where
# project.yml links it from. The app runs a Tailscale node of its own with it
# to reach the server away from home without the Tailscale app (decision D16).
#
# Needs Go (any recent one fetches the version libtailscale asks for) and
# Xcode. The result is git-ignored; CI keeps it in its cache.
#
#   ios/scripts/build-tailscale.sh
set -euo pipefail

# github.com/tailscale/libtailscale, main on 2026-10-30.
REV=ac7ed43af14e19e1c1810ee9f8319872c6beb412
MIN_IOS=17.0

ios="$(cd "$(dirname "$0")/.." && pwd)"
out="$ios/Vendor/Tailscale"
if [[ "$(cat "$out/REVISION" 2>/dev/null)" == "$REV" ]]; then
    echo "libtailscale $REV already built in $out"
    exit 0
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
git init -q "$work/src"
git -C "$work/src" fetch -q --depth 1 https://github.com/tailscale/libtailscale.git "$REV"
git -C "$work/src" checkout -q FETCH_HEAD

# cgo's compiler for one SDK: Xcode's clang with that SDK, arm64 only.
compiler() {
    local sdk=$1 min=$2 cc="$work/cc-$1.sh"
    cat >"$cc" <<EOF
#!/bin/sh
exec "$(xcrun --sdk "$sdk" --find clang)" -arch arm64 -isysroot "$(xcrun --sdk "$sdk" --show-sdk-path)" $min "\$@"
EOF
    chmod +x "$cc"
    echo "$cc"
}

build() {
    local sdk=$1 min=$2
    echo "Building libtailscale for $sdk…"
    mkdir -p "$work/$sdk"
    (cd "$work/src" && GOOS=ios GOARCH=arm64 CGO_ENABLED=1 CC="$(compiler "$sdk" "$min")" \
        go build -trimpath -ldflags=-w -tags ios -buildmode=c-archive -o "$work/$sdk/libtailscale.a" .)
}

build iphoneos "-mios-version-min=$MIN_IOS"
build iphonesimulator "-mios-simulator-version-min=$MIN_IOS"

rm -rf "$out"
mkdir -p "$out/include" "$out/iphoneos" "$out/iphonesimulator"
cp "$work/iphoneos/libtailscale.a" "$out/iphoneos/"
cp "$work/iphonesimulator/libtailscale.a" "$out/iphonesimulator/"
cp "$work/src/tailscale.h" "$work/src/LICENSE" "$out/include/"
cat >"$out/include/module.modulemap" <<'EOF'
module Tailscale {
    header "tailscale.h"
    export *
}
EOF
echo "$REV" >"$out/REVISION"
echo "libtailscale $REV built in $out"
