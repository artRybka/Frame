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

}  // namespace frame::scan
