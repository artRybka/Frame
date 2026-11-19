// What the Python merge does with NumPy, said the same way over cv::Mat:
// the C++ core is `imaging/reflections.py` line by line, and comes to the
// same numbers (float32 pictures, Python's own numbers as doubles first).
#pragma once

#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <stdexcept>
#include <utility>
#include <vector>

namespace frame::scan::np {

using cv::Mat;

constexpr float INF = std::numeric_limits<float>::infinity();
constexpr float NaN = std::numeric_limits<float>::quiet_NaN();

/// Python's round(): halves to the even one.
inline int pyround(double v) { return static_cast<int>(std::nearbyint(v)); }

inline float clipf(float v, float low, float high) { return v < low ? low : v > high ? high : v; }

/// (v - from) / (to - from) held to 0–1: "from, and wholly at".
inline float ramp(float v, double from, double to) {
    return clipf((v - static_cast<float>(from)) / static_cast<float>(to - from), 0.f, 1.f);
}

inline void same_size(const Mat& a, const Mat& b) {
    if (a.rows != b.rows || a.cols != b.cols) throw std::logic_error("pictures of two sizes");
}

/// Rows of a picture worked on side by side.
template <class F>
void rows(int count, F&& each) {
    cv::parallel_for_(cv::Range(0, count), [&](const cv::Range& r) {
        for (int y = r.start; y < r.end; y++) each(y);
    });
}

namespace detail {
template <class F, size_t... I>
inline float call(F& f, const float* const* p, const int* ch, int x, int c, std::index_sequence<I...>) {
    return f(p[I][x * ch[I] + (ch[I] == 1 ? 0 : c)]...);
}
}  // namespace detail

/// f over every value of the pictures given (float32, one size; one with
/// a single channel counts for each channel of the others).
template <class F, class... M>
Mat ew(F f, const M&... m) {
    const Mat* mats[] = {&m...};
    constexpr size_t n = sizeof...(M);
    int channels = 1;
    for (const Mat* each : mats) {
        if (each->depth() != CV_32F) throw std::logic_error("ew: float32 only");
        same_size(*mats[0], *each);
        channels = std::max(channels, each->channels());
    }
    int ch[n];
    for (size_t i = 0; i < n; i++) {
        ch[i] = mats[i]->channels();
        if (ch[i] != 1 && ch[i] != channels) throw std::logic_error("ew: channels");
    }
    Mat out(mats[0]->rows, mats[0]->cols, CV_32FC(channels));
    rows(out.rows, [&](int y) {
        const float* p[n];
        for (size_t i = 0; i < n; i++) p[i] = mats[i]->template ptr<float>(y);
        float* o = out.ptr<float>(y);
        for (int x = 0; x < out.cols; x++)
            for (int c = 0; c < channels; c++)
                o[x * channels + c] = detail::call(f, p, ch, x, c, std::index_sequence_for<M...>{});
    });
    return out;
}

/// f(the pixel's channels) → one value: `.mean(-1)`, `.max(-1)`…
template <class F>
Mat per_pixel(const Mat& a, F f) {
    Mat out(a.rows, a.cols, CV_32F);
    int ch = a.channels();
    rows(a.rows, [&](int y) {
        const float* p = a.ptr<float>(y);
        float* o = out.ptr<float>(y);
        for (int x = 0; x < a.cols; x++) o[x] = f(p + x * ch);
    });
    return out;
}

inline Mat mean3(const Mat& a) {
    return per_pixel(a, [](const float* p) { return (p[0] + p[1] + p[2]) / 3.0f; });
}
inline Mat sum3(const Mat& a) {
    return per_pixel(a, [](const float* p) { return p[0] + p[1] + p[2]; });
}
inline Mat max3(const Mat& a) {
    return per_pixel(a, [](const float* p) { return std::max(p[0], std::max(p[1], p[2])); });
}
inline Mat min3(const Mat& a) {
    return per_pixel(a, [](const float* p) { return std::min(p[0], std::min(p[1], p[2])); });
}
/// `a @ weights`.
inline Mat dot3(const Mat& a, const std::array<float, 3>& w) {
    return per_pixel(a, [w](const float* p) { return p[0] * w[0] + p[1] * w[1] + p[2] * w[2]; });
}
inline constexpr std::array<float, 3> LUMA{0.2126f, 0.7152f, 0.0722f};

inline Mat channel(const Mat& a, int c) {
    Mat out;
    cv::extractChannel(a, out, c);
    return out;
}

inline Mat zeros(const Mat& like) { return Mat::zeros(like.rows, like.cols, like.type()); }
inline Mat zeros(int rows, int cols, int channels = 1) { return Mat::zeros(rows, cols, CV_32FC(channels)); }
inline Mat ones(int rows, int cols) { return Mat(rows, cols, CV_32F, cv::Scalar(1)); }

/// `a.any()`.
inline bool any(const Mat& a) {
    Mat flat = a.reshape(1);
    return cv::countNonZero(flat) > 0;
}

/// NumPy's pairwise sum of float32 (what `.sum()` and `.mean()` of a whole
/// picture come to).
inline float pairwise(const float* a, size_t n) {
    if (n < 8) {
        float res = 0.f;
        for (size_t i = 0; i < n; i++) res += a[i];
        return res;
    }
    if (n <= 128) {
        float r[8];
        for (int i = 0; i < 8; i++) r[i] = a[i];
        size_t i;
        for (i = 8; i < n - (n % 8); i += 8)
            for (int k = 0; k < 8; k++) r[k] += a[i + k];
        float res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        for (; i < n; i++) res += a[i];
        return res;
    }
    size_t half = n / 2;
    half -= half % 8;
    return pairwise(a, half) + pairwise(a + half, n - half);
}

/// `float(a.mean())` of float32 values: NumPy's sum by pairs, over their
/// count as doubles, and a float32 again.
inline double mean_of(const float* a, size_t n) {
    return static_cast<double>(static_cast<float>(static_cast<double>(pairwise(a, n)) / static_cast<double>(n)));
}
inline double mean_of(const std::vector<float>& v) { return v.empty() ? NaN : mean_of(v.data(), v.size()); }

/// `float(a.mean())` of a whole float32 picture.
inline double mean_all(const Mat& a) {
    Mat flat = a.isContinuous() ? a : a.clone();
    return mean_of(flat.ptr<float>(), flat.total() * flat.channels());
}

/// Python's round(v, 4).
inline double round4(double v) {
    char text[64];
    std::snprintf(text, sizeof text, "%.4f", v);
    return std::strtod(text, nullptr);
}

/// NumPy's linear quantile of float32 values (which it puts in order), q
/// in 0–1: between the two about it, in float32 as NumPy does it for a q
/// that is Python's own number.
inline float quantile(std::vector<float>& v, double q) {
    if (v.empty()) return NaN;
    double at = static_cast<double>(v.size() - 1) * q;
    size_t below = static_cast<size_t>(std::floor(at));
    size_t above = std::min(below + 1, v.size() - 1);
    double t = at - static_cast<double>(below);
    std::nth_element(v.begin(), v.begin() + below, v.end());
    float a = v[below];
    float b = above == below ? a : *std::min_element(v.begin() + below + 1, v.end());
    // NumPy's _lerp.
    float d = b - a;
    return t >= 0.5 ? b - d * static_cast<float>(1 - t) : a + d * static_cast<float>(t);
}

/// `np.median` of float32 values: the middle one, or the mean of the two
/// (in float32).
inline float median(std::vector<float>& v) {
    if (v.empty()) return NaN;
    size_t mid = v.size() / 2;
    std::nth_element(v.begin(), v.begin() + mid, v.end());
    float high = v[mid];
    if (v.size() % 2) return high;
    float low = *std::max_element(v.begin(), v.begin() + mid);
    return (low + high) / 2.0f;
}

inline std::vector<float> flat(const Mat& a) {
    Mat c = a.isContinuous() ? a : a.clone();
    const float* p = c.ptr<float>();
    return std::vector<float>(p, p + c.total() * c.channels());
}

/// OpenCV's blur with sigma alone, as `cv2.GaussianBlur(a, (0, 0), sigma)`.
inline Mat blur(const Mat& a, double sigma, int border = cv::BORDER_DEFAULT) {
    Mat out;
    cv::GaussianBlur(a, out, cv::Size(0, 0), sigma, 0, border);
    return out;
}

inline Mat resize(const Mat& a, int w, int h, int how) {
    Mat out;
    cv::resize(a, out, cv::Size(w, h), 0, 0, how);
    return out;
}

inline Mat dilate(const Mat& a, const Mat& with, int times = 1) {
    Mat out;
    cv::dilate(a, out, with, cv::Point(-1, -1), times);
    return out;
}
inline Mat erode(const Mat& a, const Mat& with) {
    Mat out;
    cv::erode(a, out, with);
    return out;
}
inline Mat opened(const Mat& a, const Mat& with) {
    Mat out;
    cv::morphologyEx(a, out, cv::MORPH_OPEN, with);
    return out;
}
inline Mat square(int size) { return Mat::ones(size, size, CV_8U); }
inline Mat ellipse(int size) { return cv::getStructuringElement(cv::MORPH_ELLIPSE, cv::Size(size, size)); }
inline Mat cross3() { return cv::getStructuringElement(cv::MORPH_CROSS, cv::Size(3, 3)); }

inline Mat median5(const Mat& a) {
    Mat out;
    cv::medianBlur(a, out, 5);
    return out;
}

/// `max(3, round(v)) | 1` and the like.
inline int odd(int least, double v) { return std::max(least, pyround(v)) | 1; }

/// 3 × 3 of doubles.
using M33 = cv::Matx33d;

/// `np.linalg.inv` of a 3 × 3: LAPACK's way, rows swapped for the largest
/// pivot.
inline M33 inv(const M33& m) {
    double a[3][6];
    for (int i = 0; i < 3; i++)
        for (int j = 0; j < 3; j++) {
            a[i][j] = m(i, j);
            a[i][j + 3] = i == j ? 1.0 : 0.0;
        }
    for (int col = 0; col < 3; col++) {
        int pivot = col;
        for (int r = col + 1; r < 3; r++)
            if (std::abs(a[r][col]) > std::abs(a[pivot][col])) pivot = r;
        if (pivot != col)
            for (int j = 0; j < 6; j++) std::swap(a[col][j], a[pivot][j]);
        for (int r = col + 1; r < 3; r++) {
            double f = a[r][col] / a[col][col];
            for (int j = col; j < 6; j++) a[r][j] -= f * a[col][j];
        }
    }
    for (int col = 2; col >= 0; col--) {
        for (int j = 3; j < 6; j++) {
            double v = a[col][j];
            for (int k = col + 1; k < 3; k++) v -= a[col][k] * a[k][j];
            a[col][j] = v / a[col][col];
        }
    }
    M33 out;
    for (int i = 0; i < 3; i++)
        for (int j = 0; j < 3; j++) out(i, j) = a[i][j + 3];
    return out;
}

}  // namespace frame::scan::np
