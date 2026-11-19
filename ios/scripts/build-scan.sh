#!/bin/bash
# Builds the scan's core (core/scan: the merge of three photographs of a
# work, as the server's imaging/reflections.py does it) for the iPhone and
# the Apple-silicon simulator into ios/Vendor/Scan, where project.yml links
# it from, with the OpenCV it stands on (scripts/build-opencv.sh, built
# first if it is not there). The trial Mateusz chose 2026-11-19: "Najpierw
# próba na iPhonie".
#
# Needs Xcode (and CMake for OpenCV). The result is git-ignored; CI keeps it
# in its cache until the core or either script changes.
#
#   ios/scripts/build-scan.sh
set -euo pipefail

MIN_IOS=17.0

ios="$(cd "$(dirname "$0")/.." && pwd)"
core="$(cd "$ios/../core/scan" && pwd)"
opencv="$ios/Vendor/OpenCV"
out="$ios/Vendor/Scan"

"$ios/scripts/build-opencv.sh"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

build() {
    local sdk=$1 min=$2
    echo "Building the scan's core for ${sdk}..."
    mkdir -p "$work/$sdk" "$out/$sdk"
    # No a*b+c in one step (-ffp-contract=off): the sums are to come out as
    # NumPy's do on the server.
    for source in "$core"/src/*.cpp; do
        echo "$source"
    done | xargs -P "$(sysctl -n hw.ncpu)" -I{} sh -c '
        xcrun --sdk "$1" clang++ -arch arm64 "$2" -std=c++17 -O2 -ffp-contract=off -Wall \
            -I "$3/include" -I "$4/include" -c "$5" -o "$6/$(basename "$5" .cpp).o"
    ' sh "$sdk" "$min" "$opencv" "$core" {} "$work/$sdk"
    # One library: the core and the OpenCV under it.
    libtool -static -o "$out/$sdk/libframescan.a" "$work/$sdk"/*.o "$opencv/$sdk/libopencv.a"
}

rm -rf "$out"
mkdir -p "$out/include"
build iphoneos "-mios-version-min=$MIN_IOS"
build iphonesimulator "-mios-simulator-version-min=$MIN_IOS"
cp "$core/include/frame_scan.h" "$out/include/"
cp "$opencv/LICENSE" "$out/include/OpenCV-LICENSE"
cat >"$out/include/module.modulemap" <<'EOF'
module FrameScan {
    header "frame_scan.h"
    export *
}
EOF
echo "The scan's core built in $out"
