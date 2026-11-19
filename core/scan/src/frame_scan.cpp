// The core as C: `include/frame_scan.h`.
#include "../include/frame_scan.h"

#include "npy.hpp"
#include "scan.hpp"

#include <opencv2/core/utility.hpp>
#include <opencv2/geometry.hpp>
#include <opencv2/imgproc.hpp>

#include <chrono>
#include <cmath>
#include <cstdio>
#include <exception>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using Clock = std::chrono::steady_clock;

double since(Clock::time_point began) { return std::chrono::duration<double>(Clock::now() - began).count(); }

void noted(const frame::scan::Merged& merged, frame_scan_note* note) {
    if (!note) return;
    auto took = [&](const char* part) {
        auto at = merged.took.find(part);
        return at == merged.took.end() ? 0.0 : at->second;
    };
    note->used = merged.used;
    note->removed = merged.removed;
    note->doubt = merged.doubt ? 1 : 0;
    note->laid = took("laid");
    note->own = took("own");
    note->layer = took("layer");
    note->mended = took("mended");
    note->whole = took("whole");
}

int failed(const char* what, char* error, int error_size) {
    if (error && error_size > 0) std::snprintf(error, static_cast<size_t>(error_size), "%s", what);
    return 1;
}

// Linear light as the 8 bits of a photograph (sRGB).
cv::Mat coded(const cv::Mat& light) {
    cv::Mat out(light.rows, light.cols, CV_8UC3);
    for (int y = 0; y < light.rows; y++) {
        const float* in = light.ptr<float>(y);
        uint8_t* o = out.ptr<uint8_t>(y);
        for (int x = 0; x < light.cols * 3; x++) {
            float v = std::min(std::max(in[x], 0.f), 1.f);
            v = v <= 0.0031308f ? v * 12.92f : 1.055f * std::pow(v, 1 / 2.4f) - 0.055f;
            o[x] = static_cast<uint8_t>(v * 255 + 0.5f);
        }
    }
    return out;
}

// A lens's bend as C says it (`frame_scan.h`).
frame::scan::Bend bend_of(double k1, const double* table, int count, double centre_x, double centre_y) {
    frame::scan::Bend bend;
    bend.k1 = k1;
    if (table && count > 0) {
        if (count < 2) throw std::runtime_error("a table of one value is none");
        bend.table.assign(table, table + count);
        bend.centre[0] = centre_x;
        bend.centre[1] = centre_y;
    }
    return bend;
}

}  // namespace

extern "C" {

int frame_scan_merge_files(const char* first, const char* const* sides, int count, const double* corners,
                           int anyway, const char* into, frame_scan_note* note, char* error, int error_size) {
    try {
        if (note) *note = frame_scan_note{};
        auto began = Clock::now();
        cv::Mat photo = npy::load(first).mat();
        std::vector<cv::Mat> others;
        for (int n = 0; n < count; n++) others.push_back(npy::load(sides[n]).mat());
        if (photo.type() != CV_8UC3) return failed("the first photograph is not rows × columns × 3 of 8 bits", error, error_size);
        for (const cv::Mat& side : others)
            if (side.type() != CV_8UC3) return failed("a side photograph is not rows × columns × 3 of 8 bits", error, error_size);
        double read = since(began);
        std::array<cv::Point2d, 4> quad;
        for (int i = 0; i < 4; i++) quad[i] = cv::Point2d(corners[2 * i], corners[2 * i + 1]);
        frame::scan::Merged merged = frame::scan::merge(photo, others, quad, anyway != 0);
        noted(merged, note);
        began = Clock::now();
        npy::save(into, merged.image);
        if (note) {
            note->read = read;
            note->written = since(began);
        }
        return 0;
    } catch (const std::exception& err) {
        return failed(err.what(), error, error_size);
    } catch (...) {
        return failed("the merge failed", error, error_size);
    }
}

int frame_scan_chart_file(const char* path, const char* tables, char* error, int error_size) {
    try {
        frame::scan::Chart chart = frame::scan::Chart::read(tables);
        npy::Array read = npy::load(path);
        if (read.depth != CV_8U || read.shape.size() != 3 || read.shape[2] != 3)
            return failed("the photograph is not rows × columns × 3 of 8 bits", error, error_size);
        // On the file's own bytes: a first photograph is 144 MB of them.
        cv::Mat photo(read.shape[0], read.shape[1], CV_8UC3, read.data.data());
        frame::scan::put(photo, chart);
        npy::save(std::string(path) + ".part", photo);
        if (std::rename((std::string(path) + ".part").c_str(), path) != 0)
            return failed("the photograph could not be written", error, error_size);
        return 0;
    } catch (const std::exception& err) {
        return failed(err.what(), error, error_size);
    } catch (...) {
        return failed("the chart's colours could not be put", error, error_size);
    }
}

int frame_scan_straight_file(const char* path, double k1, const double* table, int count, double centre_x,
                             double centre_y, char* error, int error_size) {
    try {
        npy::Array read = npy::load(path);
        if (read.depth != CV_8U || read.shape.size() != 3 || read.shape[2] != 3)
            return failed("the photograph is not rows × columns × 3 of 8 bits", error, error_size);
        // Off the file's own bytes: a first photograph is 144 MB of them.
        cv::Mat photo(read.shape[0], read.shape[1], CV_8UC3, read.data.data());
        frame::scan::straight(photo, bend_of(k1, table, count, centre_x, centre_y));
        npy::save(std::string(path) + ".part", photo);
        if (std::rename((std::string(path) + ".part").c_str(), path) != 0)
            return failed("the photograph could not be written", error, error_size);
        return 0;
    } catch (const std::exception& err) {
        return failed(err.what(), error, error_size);
    } catch (...) {
        return failed("the lens's bend could not be taken out", error, error_size);
    }
}

int frame_scan_straight_pixels(unsigned char* pixels, int rows, int columns, double k1, const double* table,
                               int count, double centre_x, double centre_y, char* error, int error_size) {
    try {
        if (!pixels || rows <= 0 || columns <= 0) return failed("no picture", error, error_size);
        cv::Mat photo(rows, columns, CV_8UC3, pixels);
        cv::Mat made = photo;
        frame::scan::straight(made, bend_of(k1, table, count, centre_x, centre_y));
        made.copyTo(photo);
        return 0;
    } catch (const std::exception& err) {
        return failed(err.what(), error, error_size);
    } catch (...) {
        return failed("the lens's bend could not be taken out", error, error_size);
    }
}

int frame_scan_lens_points(double* points, int many, int columns, int rows, double k1, const double* table,
                           int count, double centre_x, double centre_y, int back, char* error, int error_size) {
    try {
        if (!points || many < 0 || rows <= 0 || columns <= 0) return failed("no points", error, error_size);
        std::vector<cv::Point2d> given;
        for (int n = 0; n < many; n++) given.emplace_back(points[2 * n], points[2 * n + 1]);
        std::vector<cv::Point2d> there =
            frame::scan::moved(given, columns, rows, bend_of(k1, table, count, centre_x, centre_y), back != 0);
        for (int n = 0; n < many; n++) {
            points[2 * n] = there[n].x;
            points[2 * n + 1] = there[n].y;
        }
        return 0;
    } catch (const std::exception& err) {
        return failed(err.what(), error, error_size);
    } catch (...) {
        return failed("the corners could not be moved", error, error_size);
    }
}

int frame_scan_made_up(int side, frame_scan_note* note, char* error, int error_size) {
    try {
        if (note) *note = frame_scan_note{};
        // `tests/test_reflections.py` `_three`: a wall with a work of
        // blocks of colour on it under glass; a lamp in the glass in the
        // first photograph, a window in the one from the left, a lamp
        // elsewhere in the one from the right.
        const int h = std::max(side, 700), w = h * 11 / 14;
        const double by = h / 1400.0;
        auto at = [&](int v) { return static_cast<int>(std::lround(v * by)); };
        const cv::Rect work(at(200), at(250), at(700), at(900));
        cv::RNG rng(7);
        cv::Mat scene(h, w, CV_32FC3), grain(h, w, CV_32FC3);
        rng.fill(grain, cv::RNG::NORMAL, 0.0, 0.01);
        scene = cv::Scalar::all(0.35);
        scene += grain;
        cv::Mat blocks(30, 24, CV_32FC3), painted;
        rng.fill(blocks, cv::RNG::UNIFORM, 0.02, 0.55);
        cv::resize(blocks, painted, work.size(), 0, 0, cv::INTER_CUBIC);
        cv::Mat rough(painted.size(), CV_32FC3);
        rng.fill(rough, cv::RNG::NORMAL, 0.0, 0.03);
        painted += rough;
        cv::max(painted, 0.01, painted);
        cv::min(painted, 0.7, painted);
        painted.copyTo(scene(work));

        auto glass = [&](float veil, const cv::Rect* window, const cv::Point* lamp) {
            cv::Mat light = cv::Mat::zeros(h, w, CV_32FC3);
            light(work) = cv::Scalar::all(veil);
            if (window) light(*window) += cv::Scalar(0.30, 0.33, 0.38);
            if (lamp)
                for (int y = work.y; y < work.y + work.height; y++) {
                    cv::Vec3f* row = light.ptr<cv::Vec3f>(y);
                    for (int x = work.x; x < work.x + work.width; x++) {
                        double dx = (x - lamp->x) / (120 * by), dy = (y - lamp->y) / (90 * by);
                        float blob = static_cast<float>(std::exp(-(dx * dx + dy * dy)) * 0.45);
                        row[x] += cv::Vec3f(blob, blob, blob);
                    }
                }
            return light;
        };
        auto from_side = [&](const cv::Mat& light, int lean, float gain) {
            cv::Point2f src[4] = {{0, 0}, {float(w), 0}, {float(w), float(h)}, {0, float(h)}};
            float a = float(at(60)), b = float(at(160)), c = float(at(90));
            cv::Point2f left[4] = {{a, 0}, {w - b, c}, {w - b, h - c}, {a, float(h)}};
            cv::Point2f right[4] = {{b, c}, {w - a, 0}, {w - a, float(h)}, {b, h - c}};
            cv::Mat seen;
            cv::warpPerspective(light, seen, cv::getPerspectiveTransform(src, lean < 0 ? left : right),
                                cv::Size(w, h), cv::INTER_LINEAR, cv::BORDER_CONSTANT, cv::Scalar::all(0.3));
            return cv::Mat(seen * gain);
        };
        cv::Point lamp(at(520), at(600)), other(at(300), at(950));
        cv::Rect window(at(560), at(300), at(300), at(320));
        cv::Mat first = coded(scene + glass(0.14f, nullptr, &lamp));
        std::vector<cv::Mat> sides = {
            coded(from_side(scene + glass(0.03f, &window, nullptr), -1, 0.9f)),
            coded(from_side(scene + glass(0.04f, nullptr, &other), 1, 1.1f)),
        };
        std::array<cv::Point2d, 4> quad = {
            cv::Point2d(double(work.x) / w, double(work.y) / h),
            cv::Point2d(double(work.x + work.width) / w, double(work.y) / h),
            cv::Point2d(double(work.x + work.width) / w, double(work.y + work.height) / h),
            cv::Point2d(double(work.x) / w, double(work.y + work.height) / h),
        };
        noted(frame::scan::merge(first, sides, quad, false), note);
        return 0;
    } catch (const std::exception& err) {
        return failed(err.what(), error, error_size);
    } catch (...) {
        return failed("the merge failed", error, error_size);
    }
}

void frame_scan_threads(int threads) { cv::setNumThreads(threads > 0 ? threads : -1); }

const char* frame_scan_built(void) {
    static const std::string said = std::string("OpenCV ") + CV_VERSION + ", " +
                                    std::to_string(cv::getNumThreads()) + " thread(s) of " +
                                    std::to_string(cv::getNumberOfCPUs()) + " core(s)";
    return said.c_str();
}

}  // extern "C"
