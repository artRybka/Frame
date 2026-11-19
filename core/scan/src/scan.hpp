// The scan of three: reflections taken out of a photograph of a work by
// two more taken from the sides. One core for the phone and the server:
// `server/src/frame_server/imaging/reflections.py` is what it does and why
// (Mateusz 2026-11-19 00:12 UTC chose "Najpierw próba na iPhonie").
#pragma once

#include <opencv2/core.hpp>

#include <array>
#include <map>
#include <string>
#include <vector>

namespace frame::scan {

struct Merged {
    cv::Mat image;  // RGB, as the first photograph
    int used = 0;  // side photographs that could be laid over the first
    double removed = 0;  // the share of the first's light within the work taken off
    bool doubt = false;  // the photographs do not show one flat work in one light
    std::map<std::string, double> took;  // seconds each part took
};

/// `first` (RGB, 8 bits) without the reflections `sides` do not share,
/// within `corners` (the work: top left, top right, bottom right, bottom
/// left, 0–1 across and down).
Merged merge(const cv::Mat& first, const std::vector<cv::Mat>& sides,
             const std::array<cv::Point2d, 4>& corners, bool anyway = false);

/// A colour chart photographed beside the work, as the server read it:
/// the way from a photograph's 8 bits to the colours the chart gives it
/// (`imaging/colorchecker.py`, whose `tables` writes what `read` reads).
struct Chart {
    float curves[3][256];  // each channel's 8-bit values as true light
    float linear[256];  // each 8-bit value's own light
    float matrix[3][3];  // applied to the light the curves give
    bool top = false;  // the curves end below the photograph's top…
    double start[3] = {1, 1, 1};  // …from this light on, in each channel
    std::vector<uint8_t> lit;  // each true light (of 65536) as it is written

    static Chart read(const std::string& path);
};

/// `photo` (RGB, 8 bits) in the colours `chart` gives it, in place: the
/// server's `colorchecker.apply`.
void put(cv::Mat& photo, const Chart& chart);

/// How a lens bends what it draws, as the server says it
/// (`imaging/lens.py` `Bend`): the one measured term `k1` about the
/// photograph's middle, or the camera's own `table` (the share at radii
/// evenly from the lens's middle, `centre` 0–1 across and down the
/// photograph, to the photograph's farthest corner from it).
struct Bend {
    double k1 = 0;
    std::vector<double> table;
    double centre[2] = {0.5, 0.5};
};

/// `photo` (8 bits) as a lens without `bend` would have drawn it, the
/// same size and middle: the server's `lens.straight`.
void straight(cv::Mat& photo, const Bend& bend);

/// Where `points` (0–1 across and down a photograph `width` by `height`)
/// set on the photograph as taken are on it straightened (`lens.moved`);
/// `back`: set on it straightened, where they are on it as taken
/// (`lens.bent`).
std::vector<cv::Point2d> moved(const std::vector<cv::Point2d>& points, int width, int height, const Bend& bend,
                               bool back = false);

}  // namespace frame::scan
