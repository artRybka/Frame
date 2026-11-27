// Our restorer's steps around its model, on the phone (Mateusz 2026-11-27: „Wszystko.”, the restorer
// on the iPhone when a work's card opens): a printed screen taken out of the picture before it is drawn
// (`imaging/descreen.py`'s `descreened`), and the drawing brought to 2K and put in the picture's colours
// after (`restorer.py`'s `draw`, `fit`, `recoloured` and `_laid`), written a second time. The Python is
// the truth: a change there is made here by hand, and checked with `tools/restore.py`.
#include "../include/frame_scan.h"
#include "constants.hpp"

#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/video/tracking.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <functional>
#include <numeric>
#include <stdexcept>
#include <utility>
#include <vector>

namespace frame::restore {

namespace {

using Point = std::pair<double, double>;  // (cycles a pixel down, across)
using Keep = std::function<cv::Mat(int, int)>;

/// Python's round(): halves to the even one.
int pyround(double v) { return static_cast<int>(std::nearbyint(v)); }

/// Python's `x % 1.0`.
double mod1(double x) { return x - std::floor(x); }

/// Pillow's "L" of an RGB picture, 0–1 (`_gray`).
cv::Mat gray(const cv::Mat& rgb) {
    cv::Mat out(rgb.rows, rgb.cols, CV_32F);
    for (int y = 0; y < rgb.rows; y++) {
        const auto* p = rgb.ptr<cv::Vec3b>(y);
        auto* o = out.ptr<float>(y);
        for (int x = 0; x < rgb.cols; x++) {
            int l = (p[x][0] * 19595 + p[x][1] * 38470 + p[x][2] * 7471 + 0x8000) >> 16;
            o[x] = static_cast<float>(l) / 255.0f;
        }
    }
    return out;
}

/// `np.fft.fftfreq(n)`.
std::vector<double> fftfreq(int n) {
    std::vector<double> f(static_cast<size_t>(n));
    int half = (n - 1) / 2 + 1;
    for (int i = 0; i < n; i++) f[static_cast<size_t>(i)] = (i < half ? i : i - n) / static_cast<double>(n);
    return f;
}

/// `fftshift` of a single-channel picture.
cv::Mat shifted(const cv::Mat& m) {
    cv::Mat out(m.size(), m.type());
    int h = m.rows, w = m.cols, cy = h / 2, cx = w / 2;
    for (int y = 0; y < h; y++)
        for (int x = 0; x < w; x++) out.at<float>((y + cy) % h, (x + cx) % w) = m.at<float>(y, x);
    return out;
}

bool across(const std::vector<Point>& points) {
    const Point& first = points[0];
    for (size_t i = 1; i < points.size(); i++)
        if (std::abs(first.first * points[i].second - first.second * points[i].first) > 1e-4) return true;
    return false;
}

/// `screen`: the points of a printed screen in the picture's spectrum, none when it has none.
std::vector<Point> screen(const cv::Mat& rgb, double stands, int fewest) {
    cv::Mat g = gray(rgb);
    int h = g.rows, w = g.cols;
    if (std::min(h, w) < 64) return {};
    int side = std::min({LOOKED, h, w});
    int top = (h - side) / 2, left = (w - side) / 2;
    cv::Mat part = g(cv::Rect(left, top, side, side)).clone();
    float mean = static_cast<float>(cv::mean(part)[0]);
    part -= mean;
    std::vector<double> hann(static_cast<size_t>(side));
    for (int i = 0; i < side; i++)
        hann[static_cast<size_t>(i)] = side == 1 ? 1.0 : 0.5 - 0.5 * std::cos(2.0 * CV_PI * i / (side - 1));
    for (int y = 0; y < side; y++) {
        auto* p = part.ptr<float>(y);
        for (int x = 0; x < side; x++)
            p[x] *= static_cast<float>(hann[static_cast<size_t>(y)] * hann[static_cast<size_t>(x)]);
    }
    cv::Mat spectrum;
    cv::dft(part, spectrum, cv::DFT_COMPLEX_OUTPUT);
    std::vector<cv::Mat> parts;
    cv::split(spectrum, parts);
    cv::Mat magnitude;
    cv::magnitude(parts[0], parts[1], magnitude);
    magnitude = shifted(magnitude);
    cv::Mat level;
    cv::log(magnitude + 1e-6f, level);
    cv::Mat ground;
    cv::GaussianBlur(level, ground, cv::Size(0, 0), std::max(3.0, side / 96.0));
    cv::Mat rise = level - ground;
    cv::Mat biggest;
    cv::dilate(rise, biggest, cv::Mat::ones(5, 5, CV_8U));

    struct Found {
        float rise;
        double fy, fx;
    };
    std::vector<Found> found;
    for (int i = 0; i < side; i++) {
        double fy = (i - side / 2) / static_cast<double>(side);
        for (int j = 0; j < side; j++) {
            double fx = (j - side / 2) / static_cast<double>(side);
            float r = rise.at<float>(i, j);
            if (!(r >= biggest.at<float>(i, j)) || !(r > stands)) continue;
            double radius = std::hypot(fy, fx);
            if (radius <= 1.0 / COARSEST || radius >= 1.0 / FINEST) continue;
            bool block = std::abs(fy * 8 - std::nearbyint(fy * 8)) < BLOCKS * 8 &&
                         std::abs(fx * 8 - std::nearbyint(fx * 8)) < BLOCKS * 8;
            if (block) continue;
            found.push_back({r, fy, fx});
        }
    }
    if (static_cast<int>(found.size()) < fewest) return {};
    std::stable_sort(found.begin(), found.end(), [](const Found& a, const Found& b) { return a.rise > b.rise; });
    std::vector<Point> points;
    for (size_t i = 0; i < found.size() && static_cast<int>(i) < MOST; i++) points.emplace_back(found[i].fy, found[i].fx);
    // Lines all one way (a drawing's hatching, a sheet's laid lines): no printer's dots.
    if (fewest >= FEWEST && !across(points)) return {};
    return points;
}

/// `lattice`: every point of the lattice the screen's points lie on, folded back into the spectrum.
std::vector<Point> lattice(const std::vector<Point>& points) {
    const Point& first = points[0];
    const Point* second = nullptr;
    for (size_t i = 1; i < points.size(); i++)
        if (std::abs(first.first * points[i].second - first.second * points[i].first) > 1e-4) {
            second = &points[i];
            break;
        }
    if (second == nullptr) return points;
    double near = INFINITY;
    for (const auto& p : points) near = std::min(near, std::hypot(p.first, p.second));
    std::vector<Point> out;
    for (int i = -HARMONICS; i <= HARMONICS; i++)
        for (int j = -HARMONICS; j <= HARMONICS; j++) {
            if (i == 0 && j == 0) continue;
            double py = mod1(i * first.first + j * second->first + 0.5) - 0.5;
            double px = mod1(i * first.second + j * second->second + 0.5) - 0.5;
            if (std::hypot(py, px) > NEAREST * NOTCH * near) out.emplace_back(py, px);
        }
    return out;
}

/// `_filtered`: the picture (float, 3 channels) through a filter of its spectrum, mirrored at its edges first.
cv::Mat filtered(const cv::Mat& rgb, const Keep& keep) {
    int h = rgb.rows, w = rgb.cols;
    int pad = std::max(8, pyround(PAD * std::max(h, w)));
    int bh = cv::getOptimalDFTSize(h + 2 * pad), bw = cv::getOptimalDFTSize(w + 2 * pad);
    int top = (bh - h) / 2, left = (bw - w) / 2;
    cv::Mat big;
    cv::copyMakeBorder(rgb, big, top, bh - h - top, left, bw - w - left, cv::BORDER_REFLECT);
    cv::Mat mask = keep(bh, bw);
    std::vector<cv::Mat> channels;
    cv::split(big, channels);
    std::vector<cv::Mat> out(3);
    for (int c = 0; c < 3; c++) {
        cv::Mat spectrum;
        cv::dft(channels[static_cast<size_t>(c)], spectrum, cv::DFT_COMPLEX_OUTPUT);
        std::vector<cv::Mat> ri;
        cv::split(spectrum, ri);
        ri[0] = ri[0].mul(mask);
        ri[1] = ri[1].mul(mask);
        cv::merge(ri, spectrum);
        cv::Mat back;
        cv::idft(spectrum, back, cv::DFT_SCALE | cv::DFT_REAL_OUTPUT);
        out[static_cast<size_t>(c)] = back(cv::Rect(left, top, w, h)).clone();
    }
    cv::Mat merged;
    cv::merge(out, merged);
    return merged;
}

/// `_notches`: a dip round each of `points` (and its mirror) in the spectrum.
Keep notches(std::vector<Point> points, double notch) {
    return [points = std::move(points), notch](int h, int w) {
        cv::Mat mask(h, w, CV_32F, cv::Scalar(1.0f));
        int ry = std::max(1, static_cast<int>(4 * notch * h)), rx = std::max(1, static_cast<int>(4 * notch * w));
        for (const auto& p : points) {
            for (int sign : {1, -1}) {
                double sy = sign * p.first, sx = sign * p.second;
                int cy = pyround(sy * h), cx = pyround(sx * w);
                for (int a = -ry; a <= ry; a++) {
                    double gy = a / static_cast<double>(h) + cy / static_cast<double>(h) - sy;
                    gy *= gy;
                    int row = ((cy + a) % h + h) % h;
                    auto* m = mask.ptr<float>(row);
                    for (int b = -rx; b <= rx; b++) {
                        double gx = b / static_cast<double>(w) + cx / static_cast<double>(w) - sx;
                        gx *= gx;
                        auto dip = static_cast<float>(std::exp(-(gy + gx) / (2 * notch * notch)));
                        int col = ((cx + b) % w + w) % w;
                        m[col] *= 1.0f - dip;
                    }
                }
            }
        }
        return mask;
    };
}

/// `_finest_off`: the finest grain let go of, gently, up to none at the corner of the spectrum.
cv::Mat finest_off(int h, int w) {
    std::vector<double> fy = fftfreq(h), fx = fftfreq(w);
    cv::Mat mask(h, w, CV_32F);
    for (int y = 0; y < h; y++) {
        auto ay = static_cast<float>(fy[static_cast<size_t>(y)]);
        auto* m = mask.ptr<float>(y);
        for (int x = 0; x < w; x++) {
            auto ax = static_cast<float>(fx[static_cast<size_t>(x)]);
            float radius = std::sqrt(ay * ay + ax * ax);
            float t = std::clamp((radius - static_cast<float>(SOFT)) / static_cast<float>(0.5 - SOFT), 0.0f, 1.0f);
            m[x] = 0.5f + 0.5f * std::cos(static_cast<float>(CV_PI) * t);
        }
    }
    return mask;
}

/// `_image`: the floats back to bytes.
cv::Mat image(const cv::Mat& rgb) {
    cv::Mat out(rgb.size(), CV_8UC3);
    for (int y = 0; y < rgb.rows; y++) {
        const auto* p = rgb.ptr<cv::Vec3f>(y);
        auto* o = out.ptr<cv::Vec3b>(y);
        for (int x = 0; x < rgb.cols; x++)
            for (int c = 0; c < 3; c++)
                o[x][c] = static_cast<unsigned char>(std::clamp(p[x][c] + 0.5f, 0.0f, 255.0f));
    }
    return out;
}

double nearest(const std::vector<Point>& points) {
    double near = INFINITY;
    for (const auto& p : points) near = std::min(near, std::hypot(p.first, p.second));
    return near;
}

// -- the colours (`restorer.recoloured`), OKLab as `imaging/color.py` has it --------------------------

struct Lab {
    float linear[256];
    float m1[3][3], m2[3][3], m1_inv[3][3], m2_inv[3][3];

    Lab() {
        const double M1[3][3] = {{0.4122214708, 0.5363325363, 0.0514459929},
                                 {0.2119034982, 0.6806995451, 0.1073969566},
                                 {0.0883024619, 0.2817188376, 0.6299787005}};
        const double M2[3][3] = {{0.2104542553, 0.7936177850, -0.0040720468},
                                 {1.9779984951, -2.4285922050, 0.4505937099},
                                 {0.0259040371, 0.7827717662, -0.8086757660}};
        // As NumPy: the matrices float32, their inverses of those in double, then float32.
        cv::Mat a(3, 3, CV_64F), b(3, 3, CV_64F);
        for (int i = 0; i < 3; i++)
            for (int j = 0; j < 3; j++) {
                m1[i][j] = static_cast<float>(M1[i][j]);
                m2[i][j] = static_cast<float>(M2[i][j]);
                a.at<double>(i, j) = m1[i][j];
                b.at<double>(i, j) = m2[i][j];
            }
        cv::Mat ai = a.inv(), bi = b.inv();
        for (int i = 0; i < 3; i++)
            for (int j = 0; j < 3; j++) {
                m1_inv[i][j] = static_cast<float>(ai.at<double>(i, j));
                m2_inv[i][j] = static_cast<float>(bi.at<double>(i, j));
            }
        for (int v = 0; v < 256; v++) {
            float x = static_cast<float>(v) / 255.0f;
            linear[v] = x <= 0.04045f ? x / 12.92f : std::pow((x + 0.055f) / 1.055f, 2.4f);
        }
    }

    cv::Mat of(const cv::Mat& rgb) const {
        cv::Mat out(rgb.size(), CV_32FC3);
        for (int y = 0; y < rgb.rows; y++) {
            const auto* p = rgb.ptr<cv::Vec3b>(y);
            auto* o = out.ptr<cv::Vec3f>(y);
            for (int x = 0; x < rgb.cols; x++) {
                float c[3] = {linear[p[x][0]], linear[p[x][1]], linear[p[x][2]]};
                float lms[3];
                for (int i = 0; i < 3; i++) lms[i] = std::cbrt(m1[i][0] * c[0] + m1[i][1] * c[1] + m1[i][2] * c[2]);
                for (int i = 0; i < 3; i++) o[x][i] = m2[i][0] * lms[0] + m2[i][1] * lms[1] + m2[i][2] * lms[2];
            }
        }
        return out;
    }

    cv::Mat back(const cv::Mat& lab) const {
        cv::Mat out(lab.size(), CV_8UC3);
        const float power = static_cast<float>(1 / 2.4);
        for (int y = 0; y < lab.rows; y++) {
            const auto* p = lab.ptr<cv::Vec3f>(y);
            auto* o = out.ptr<cv::Vec3b>(y);
            for (int x = 0; x < lab.cols; x++) {
                float lms[3];
                for (int i = 0; i < 3; i++) {
                    float v = m2_inv[i][0] * p[x][0] + m2_inv[i][1] * p[x][1] + m2_inv[i][2] * p[x][2];
                    lms[i] = v * v * v;
                }
                for (int i = 0; i < 3; i++) {
                    float l = m1_inv[i][0] * lms[0] + m1_inv[i][1] * lms[1] + m1_inv[i][2] * lms[2];
                    l = std::clamp(l, 0.0f, 1.0f);
                    float s = l <= 0.0031308f ? l * 12.92f : 1.055f * std::pow(l, power) - 0.055f;
                    o[x][i] = static_cast<unsigned char>(std::nearbyint(s * 255.0f));
                }
            }
        }
        return out;
    }
};

const Lab& lab() {
    static const Lab made;
    return made;
}

/// `_laid`: where the museum's picture lies on the drawing (an affine map from the drawing's pixels to
/// its), or false when the two do not match.
bool laid(const cv::Mat& museum, const cv::Mat& drawn, cv::Mat& full) {
    int h = drawn.rows, w = drawn.cols;
    double k = std::min(1.0, LAID_SIDE / static_cast<double>(std::max(h, w)));
    cv::Size small(std::max(8, pyround(w * k)), std::max(8, pyround(h * k)));
    auto prepared = [&](const cv::Mat& m) {
        cv::Mat b;
        cv::resize(m, b, small, 0, 0, cv::INTER_AREA);
        cv::GaussianBlur(b, b, cv::Size(0, 0), 1.0);
        return b;
    };
    cv::Mat a = prepared(drawn), b = prepared(museum);
    cv::Mat warp = cv::Mat::eye(2, 3, CV_32F);
    try {
        cv::findTransformECC(a, b, warp, cv::MOTION_AFFINE,
                             cv::TermCriteria(cv::TermCriteria::EPS | cv::TermCriteria::COUNT, 100, 1e-5),
                             cv::noArray(), 5);
    } catch (const cv::Exception&) {
        return false;
    }
    cv::Mat moved;
    cv::warpAffine(b, moved, warp, small, cv::INTER_LINEAR | cv::WARP_INVERSE_MAP, cv::BORDER_REFLECT);
    float am = static_cast<float>(cv::mean(a)[0]), mm = static_cast<float>(cv::mean(moved)[0]);
    double ab = 0, aa = 0, bb = 0;
    for (int y = 0; y < small.height; y++) {
        const auto* pa = a.ptr<float>(y);
        const auto* pm = moved.ptr<float>(y);
        for (int x = 0; x < small.width; x++) {
            float da = pa[x] - am, dm = pm[x] - mm;
            ab += da * dm;
            aa += da * da;
            bb += dm * dm;
        }
    }
    double match = ab / (std::sqrt(aa * bb) + 1e-9);
    double shift = std::max(std::abs(warp.at<float>(0, 2)), std::abs(warp.at<float>(1, 2))) /
                   static_cast<double>(std::max(small.width, small.height));
    if (match < LAID_MATCH || shift > LAID_SHIFT || std::abs(warp.at<float>(0, 0) - 1) > LAID_SHIFT) return false;
    full = warp.clone();
    full.at<float>(0, 2) = static_cast<float>(full.at<float>(0, 2) / k);
    full.at<float>(1, 2) = static_cast<float>(full.at<float>(1, 2) / k);
    return true;
}

}  // namespace

/// `descreen.descreened`: the picture (RGB bytes) with a printed screen taken out, and a small one's finest
/// grain let go of; `found` the screen's points (0: none).
cv::Mat descreened(const cv::Mat& picture, int& found) {
    std::vector<Point> points = screen(picture, STANDS, FEWEST);
    found = static_cast<int>(points.size());
    bool small = std::max(picture.rows, picture.cols) <= SMALL;
    if (points.empty() && !small) return picture.clone();
    cv::Mat rgb;
    picture.convertTo(rgb, CV_32FC3);
    if (!points.empty()) {
        double notch = NOTCH * nearest(points);
        rgb = filtered(rgb, notches(lattice(points), notch));
        std::vector<Point> left = screen(image(rgb), LEFT_STANDS, LEFT_FEWEST);
        if (!left.empty()) rgb = filtered(rgb, notches(left, notch));
    }
    if (small) rgb = filtered(rgb, finest_off);
    return image(rgb);
}

/// `restorer.recoloured`: `drawn` in the colours of the picture it was drawn from; `laid_on` false when it
/// does not lie on it (kept as drawn).
cv::Mat recoloured(const cv::Mat& picture, const cv::Mat& drawn, double share, bool& laid_on) {
    cv::Size size = drawn.size();
    double sigma = COLOUR_SIGMA * std::max(size.width, size.height) / std::max(picture.cols, picture.rows);
    cv::Mat plain, own;
    cv::GaussianBlur(picture, plain, cv::Size(0, 0), GRAIN_SIGMA);
    cv::resize(plain, own, size, 0, 0, cv::INTER_LANCZOS4);
    cv::Mat museum = lab().of(own), mine = lab().of(drawn);
    cv::Mat museum_l, mine_l;
    cv::extractChannel(museum, museum_l, 0);
    cv::extractChannel(mine, mine_l, 0);
    cv::Mat warp;
    laid_on = laid(museum_l, mine_l, warp);
    if (!laid_on) return drawn.clone();
    cv::Mat moved;
    cv::warpAffine(museum, moved, warp, size, cv::INTER_LINEAR | cv::WARP_INVERSE_MAP, cv::BORDER_REFLECT);
    cv::Mat mb, lb;
    cv::GaussianBlur(moved, mb, cv::Size(0, 0), sigma);
    cv::GaussianBlur(mine, lb, cv::Size(0, 0), sigma);
    mine += mb - lb;
    auto s = static_cast<float>(share);
    cv::Mat out = moved + (mine - moved) * s;
    return lab().back(out);
}

/// `restorer.draw` and `fit`: the model's drawing brought to `LONGEST` and to the picture's proportions.
cv::Mat fitted(const cv::Mat& drawn, cv::Size picture) {
    double k = LONGEST / static_cast<double>(std::max(drawn.cols, drawn.rows));
    cv::Size size(pyround(drawn.cols * k), pyround(drawn.rows * k));
    cv::Mat out;
    cv::resize(drawn, out, size, 0, 0, cv::INTER_AREA);
    int w = picture.width, h = picture.height, dw = size.width, dh = size.height;
    if (std::max(dw, dh) <= std::max(w, h)) throw std::runtime_error("drawn no larger than its picture");
    double skew = std::abs((dw / static_cast<double>(dh)) / (w / static_cast<double>(h)) - 1);
    if (skew > SKEW_MAX) throw std::runtime_error("drawn in other proportions than its picture");
    if (skew <= SKEW_FIXED) return out;
    if (dw / static_cast<double>(w) >= dh / static_cast<double>(h))
        dh = pyround(dw * static_cast<double>(h) / w);
    else
        dw = pyround(dh * static_cast<double>(w) / h);
    cv::resize(out, out, cv::Size(dw, dh), 0, 0, cv::INTER_LANCZOS4);
    return out;
}

}  // namespace frame::restore

namespace {

int failed(const char* why, char* error, int error_size) {
    if (error && error_size > 0) std::snprintf(error, static_cast<size_t>(error_size), "%s", why);
    return -1;
}

}  // namespace

extern "C" {

int frame_restore_descreen(unsigned char* pixels, int rows, int columns, int* found, char* error, int error_size) {
    try {
        if (!pixels || rows <= 0 || columns <= 0) return failed("no picture", error, error_size);
        cv::Mat rgb(rows, columns, CV_8UC3, pixels);
        int points = 0;
        cv::Mat out = frame::restore::descreened(rgb, points);
        out.copyTo(rgb);
        if (found) *found = points;
        return 0;
    } catch (const std::exception& err) {
        return failed(err.what(), error, error_size);
    } catch (...) {
        return failed("the printed screen could not be taken out", error, error_size);
    }
}

int frame_restore_colours(const unsigned char* picture, int rows, int columns, const unsigned char* drawn,
                          int drawn_rows, int drawn_columns, double share, unsigned char* into, int* into_rows,
                          int* into_columns, int* laid, char* error, int error_size) {
    try {
        if (!picture || !drawn || !into || !into_rows || !into_columns || rows <= 0 || columns <= 0 ||
            drawn_rows <= 0 || drawn_columns <= 0)
            return failed("no picture", error, error_size);
        cv::Mat own(rows, columns, CV_8UC3, const_cast<unsigned char*>(picture));
        cv::Mat big(drawn_rows, drawn_columns, CV_8UC3, const_cast<unsigned char*>(drawn));
        cv::Mat fit = frame::restore::fitted(big, own.size());
        if (fit.cols > frame::restore::LONGEST || fit.rows > frame::restore::LONGEST)
            return failed("drawn larger than 2K", error, error_size);
        bool on = false;
        cv::Mat out = frame::restore::recoloured(own, fit, share, on);
        cv::Mat(out.rows, out.cols, CV_8UC3, into).setTo(0);
        out.copyTo(cv::Mat(out.rows, out.cols, CV_8UC3, into));
        *into_rows = out.rows;
        *into_columns = out.cols;
        if (laid) *laid = on ? 1 : 0;
        return 0;
    } catch (const std::exception& err) {
        return failed(err.what(), error, error_size);
    } catch (...) {
        return failed("the drawing could not be put in its picture's colours", error, error_size);
    }
}

}  // extern "C"
