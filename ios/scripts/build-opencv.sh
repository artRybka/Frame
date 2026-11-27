#!/bin/bash
# Builds OpenCV for the iPhone and the Apple-silicon simulator into
# ios/Vendor/OpenCV, for the scan's core to stand on (scripts/build-scan.sh):
# the phone merges the scan of three itself with it (the trial Mateusz chose
# 2026-11-19, "Najpierw próba na iPhonie").
#
# The very sources the server's wheel was built of (opencv-python-headless on
# PyPI, which carries them), only the five modules the merge uses, and no
# acceleration library of anyone's (KleidiCV, Accelerate's LAPACK): the phone
# is to count as the server does (nor the font it would fetch for putText).
# Nor OpenCV's own way with numbers on an iPhone: its iOS platform asks the
# compiler for -ffast-math, and the compiler by itself makes a*b+c one step
# on arm64 (the trial on his phone, 2026-11-19: 8% of a scan's values a
# level off the server's, 0.8% four and more; the same sources built for
# arm64 without either: 0.2% a level off, none four).
# Built the way OpenCV's own
# platforms/ios/build_framework.py builds it (APPLE_FRAMEWORK: the modules in
# one library, for arm64 alone), without the framework put around it after.
#
# Needs Xcode and CMake. Some ten minutes for each of the two; the result is
# git-ignored and CI keeps it in its cache.
#
#   ios/scripts/build-opencv.sh
set -euo pipefail

# What server/uv.lock has: the two are to be one OpenCV.
WHEEL=5.0.0.93
SDIST=https://files.pythonhosted.org/packages/1d/99/76b7c80252aa83c1af16393454aafd125a0287101afe8deb0a6821af0e30/opencv_python_headless-5.0.0.93.tar.gz
SHA256=b82f9831daab90b725c7c1ee1b36cb5732c367096ac76d119e64e14eb70d5f3c
MIN_IOS=17.0
# Raised when what is built of those sources changes.
BUILD=3

ios="$(cd "$(dirname "$0")/.." && pwd)"
out="$ios/Vendor/OpenCV"
revision="$WHEEL-$MIN_IOS-$BUILD"
if [[ "$(cat "$out/REVISION" 2>/dev/null)" == "$revision" ]]; then
    echo "OpenCV $revision already built in $out"
    exit 0
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
echo "Fetching the sources of OpenCV ($WHEEL)..."
curl -fsSL --retry 3 -o "$work/sdist.tar.gz" "$SDIST"
echo "$SHA256  $work/sdist.tar.gz" | shasum -a 256 -c -
tar -xzf "$work/sdist.tar.gz" -C "$work" "opencv_python_headless-$WHEEL/opencv"
src="$work/opencv_python_headless-$WHEEL/opencv"
# Numbers as the server's OpenCV counts them (see above).
sed -i '' 's/ -ffast-math//' "$src/platforms/ios/cmake/Modules/Platform/iOS.cmake"
exact="-ffp-contract=off"

build() {
    local sdk=$1 toolchain=$2
    shift 2
    local dir="$work/$sdk"
    echo "Building OpenCV for ${sdk}..."
    mkdir -p "$dir"
    (
        cd "$dir"
        export IPHONEOS_DEPLOYMENT_TARGET=$MIN_IOS
        cmake -GXcode "$src" \
            -DCMAKE_TOOLCHAIN_FILE="$src/platforms/ios/cmake/Toolchains/Toolchain-${toolchain}_Xcode.cmake" \
            -DIOS_ARCH=arm64 "$@" \
            -DCMAKE_C_FLAGS="$exact" -DCMAKE_CXX_FLAGS="$exact" \
            -DAPPLE_FRAMEWORK=ON -DFRAMEWORK_NAME=opencv2 \
            -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$dir/install" \
            -DOPENCV_INCLUDE_INSTALL_PATH=include -DOPENCV_3P_LIB_INSTALL_PATH=lib/3rdparty \
            -DBUILD_LIST=core,imgproc,flann,geometry,features,video -DBUILD_SHARED_LIBS=OFF \
            -DBUILD_TESTS=OFF -DBUILD_PERF_TESTS=OFF -DBUILD_EXAMPLES=OFF -DBUILD_DOCS=OFF \
            -DBUILD_opencv_apps=OFF -DBUILD_JAVA=OFF -DBUILD_OBJC=OFF \
            -DBUILD_opencv_python2=OFF -DBUILD_opencv_python3=OFF \
            -DBUILD_opencv_imgcodecs=OFF -DBUILD_opencv_highgui=OFF -DWITH_UNIFONT=OFF \
            -DWITH_IPP=OFF -DWITH_ITT=OFF -DWITH_OPENCL=OFF -DWITH_EIGEN=OFF -DWITH_PROTOBUF=OFF \
            -DWITH_OPENMP=OFF -DWITH_TBB=OFF -DWITH_KLEIDICV=OFF -DWITH_CAROTENE=OFF \
            -DWITH_JPEG=OFF -DWITH_PNG=OFF -DWITH_TIFF=OFF -DWITH_WEBP=OFF -DWITH_OPENJPEG=OFF \
            -DWITH_JASPER=OFF -DWITH_OPENEXR=OFF -DWITH_AVIF=OFF -DWITH_JPEGXL=OFF \
            -DBUILD_ZLIB=ON -DBUILD_CLAPACK=ON -DENABLE_CCACHE=OFF >"$dir/configure.log" ||
            { tail -n 60 "$dir/configure.log"; exit 1; }
        grep -E "Baseline|Dispatched|Lapack|Parallel framework|Custom HAL|C\+\+ flags \(Release\)" \
            "$dir/configure.log" || true
        flags="$(grep -E "C\+\+ flags \(Release\)" "$dir/configure.log" || true)"
        if [[ "$flags" == *fast-math* || "$flags" != *"$exact"* ]]; then
            echo "OpenCV would not count as the server does: $flags" >&2
            exit 1
        fi
        xcodebuild IPHONEOS_DEPLOYMENT_TARGET=$MIN_IOS ARCHS=arm64 -sdk "$sdk" -configuration Release \
            -parallelizeTargets -jobs "$(sysctl -n hw.ncpu)" -target ALL_BUILD build >"$dir/build.log" ||
            { grep -E "error:|\*\* BUILD FAILED" -B 2 -A 8 "$dir/build.log" | tail -n 120; exit 1; }
        cmake -DBUILD_TYPE=Release -P cmake_install.cmake >"$dir/install.log" ||
            { tail -n 40 "$dir/install.log"; exit 1; }
    )
    mkdir -p "$out/$sdk"
    # One library of the six modules and what they stand on (zlib, LAPACK).
    libtool -static -o "$out/$sdk/libopencv.a" "$dir"/install/lib/*.a "$dir"/install/lib/3rdparty/*.a
}

rm -rf "$out"
mkdir -p "$out"
# The phone's own processor is asked what it can do, as OpenCV's script asks.
build iphoneos iPhoneOS -DCPU_BASELINE=DETECT
build iphonesimulator iPhoneSimulator
cp -R "$work/iphoneos/install/include" "$out/include"
cp "$src/LICENSE" "$out/LICENSE"
echo "$revision" >"$out/REVISION"
echo "OpenCV $revision built in $out"
