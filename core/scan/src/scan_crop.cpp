// A museum photograph cut down to the work by the phone's model, with no
// Claude (Mateusz 2026-11-20): what `imaging/crop_model.py` makes of the
// model's masks and how sure it is, and `imaging/cut.py`'s `snap` and
// `valid`, written a second time. The Python is the truth: a change there
// is made here by hand, and checked with `tools/crop.py`.
#include "../include/frame_scan.h"
#include "constants.hpp"

#include <opencv2/geometry.hpp>
#include <opencv2/imgproc.hpp>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <numeric>
#include <optional>
#include <stdexcept>
#include <vector>

namespace frame::crop {

namespace {

using Quad = std::array<cv::Point2d, 4>;

struct Line {
    cv::Point2d at, along;
};

// `_order`: by the angle about their middle, from the one of least x + y.
Quad ordered(const std::vector<cv::Point2d>& q) {
    cv::Point2d c((q[0].x + q[1].x + q[2].x + q[3].x) / 4.0, (q[0].y + q[1].y + q[2].y + q[3].y) / 4.0);
    std::array<int, 4> by{0, 1, 2, 3};
    std::array<double, 4> angle;
    for (int i = 0; i < 4; i++) angle[i] = std::atan2(q[i].y - c.y, q[i].x - c.x);
    std::stable_sort(by.begin(), by.end(), [&](int a, int b) { return angle[a] < angle[b]; });
    Quad s;
    for (int i = 0; i < 4; i++) s[i] = q[by[i]];
    int k = 0;
    for (int i = 1; i < 4; i++)
        if (s[i].x + s[i].y < s[k].x + s[k].y) k = i;
    Quad out;
    for (int i = 0; i < 4; i++) out[i] = s[(i + k) % 4];
    return out;
}

double norm(const cv::Point2d& p) { return std::hypot(p.x, p.y); }

// NumPy's `quantile` (its "linear" way) of `values`, which it sorts.
double quantile(std::vector<double> values, double q) {
    std::sort(values.begin(), values.end());
    double at = q * static_cast<double>(values.size() - 1);
    double below = std::floor(at);
    double gamma = at - below;
    size_t lo = static_cast<size_t>(below);
    size_t hi = std::min(lo + 1, values.size() - 1);
    double a = values[lo], b = values[hi], diff = b - a;
    return gamma >= 0.5 ? b - diff * (1 - gamma) : a + diff * gamma;
}

cv::Vec4f fit(const std::vector<cv::Point2f>& points, int how) {
    cv::Vec4f line;
    cv::fitLine(points, line, how, 0, 0.01, 0.01);
    return line;
}

// Corner i: where side i - 1 meets side i, when they meet.
std::optional<cv::Point2d> meet(const Line& one, const Line& two) {
    const cv::Point2d &d1 = one.along, &d2 = two.along;
    double det = d1.x * -d2.y - (-d2.x) * d1.y;
    if (std::abs(det) < 1e-6) return std::nullopt;
    cv::Point2d r = two.at - one.at;
    double t = (r.x * -d2.y - (-d2.x) * r.y) / det;
    return one.at + t * d1;
}

double area_of(const Quad& q) {
    double a = 0, b = 0;
    for (int i = 0; i < 4; i++) {
        const cv::Point2d& before = q[(i + 3) % 4];
        a += q[i].x * before.y;
        b += q[i].y * before.x;
    }
    return std::abs(a - b) / 2;
}

/// `crop_model.holds`: whether `around` holds every corner of `work`, to HOLD.
bool holds(const Quad& around, const Quad& work) {
    double turn = 0.0;
    for (int i = 0; i < 4; i++) {
        const auto& a = around[i];
        const auto& b = around[(i + 1) % 4];
        turn += a.x * b.y - b.x * a.y;
    }
    double sign = turn > 0 ? 1.0 : -1.0;
    for (int i = 0; i < 4; i++) {
        const auto& a = around[i];
        const auto& b = around[(i + 1) % 4];
        double length = std::hypot(b.x - a.x, b.y - a.y);
        if (length <= 0) return false;
        for (const auto& p : work) {
            double inside = sign * ((b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x)) / length;
            if (inside < -HOLD) return false;
        }
    }
    return true;
}

double round5(double v) { return std::nearbyint(v * 1e5) / 1e5; }

}  // namespace

// `cut.valid`: four corners within the picture, convex, roughly square at
// each corner and of a sensible size.
std::optional<Quad> valid(const Quad& given) {
    Quad pts;
    for (int i = 0; i < 4; i++) {
        if (!std::isfinite(given[i].x) || !std::isfinite(given[i].y)) return std::nullopt;
        pts[i] = cv::Point2d(std::clamp(given[i].x, 0.0, 1.0), std::clamp(given[i].y, 0.0, 1.0));
    }
    double area = area_of(pts);
    if (!(LEAST_KEPT <= area && area <= 1.0)) return std::nullopt;
    for (int i = 0; i < 4; i++) {
        cv::Point2d v1 = pts[(i + 3) % 4] - pts[i], v2 = pts[(i + 1) % 4] - pts[i];
        double n = norm(v1) * norm(v2);
        if (n < 1e-9) return std::nullopt;
        double angle = std::acos(std::clamp(v1.dot(v2) / n, -1.0, 1.0)) * 180.0 / M_PI;
        if (std::abs(angle - 90.0) > SQUARE) return std::nullopt;
    }
    int plus = 0, minus = 0;
    for (int i = 0; i < 4; i++) {
        cv::Point2d t1 = pts[(i + 1) % 4] - pts[i], t2 = pts[(i + 2) % 4] - pts[(i + 1) % 4];
        double cross = t1.x * t2.y - t1.y * t2.x;
        plus += cross > 0;
        minus += cross < 0;
    }
    if (plus != 4 && minus != 4) return std::nullopt;
    for (auto& p : pts) p = cv::Point2d(round5(p.x), round5(p.y));
    return pts;
}

// `crop_model.letterbox`: the photograph shrunk into a black square, as
// floats; where it is in the square.
cv::Vec4i letterbox(const cv::Mat& rgb, int side, float* into) {
    int h = rgb.rows, w = rgb.cols;
    double s = static_cast<double>(side) / std::max(w, h);
    int nw = static_cast<int>(std::nearbyint(w * s)), nh = static_cast<int>(std::nearbyint(h * s));
    int ox = (side - nw) / 2, oy = (side - nh) / 2;
    cv::Mat small;
    cv::resize(rgb, small, cv::Size(nw, nh), 0, 0, cv::INTER_AREA);
    std::fill(into, into + static_cast<size_t>(3) * side * side, 0.0f);
    for (int y = 0; y < nh; y++) {
        const uint8_t* row = small.ptr<uint8_t>(y);
        for (int x = 0; x < nw; x++)
            for (int c = 0; c < 3; c++)
                into[(static_cast<size_t>(c) * side + (oy + y)) * side + (ox + x)] = static_cast<float>(row[3 * x + c]);
    }
    return cv::Vec4i(ox, oy, nw, nh);
}

// `crop_model.probabilities`, of one mask.
cv::Mat probabilities(const float* logits, int side, const cv::Vec4i& box, int w, int h) {
    cv::Mat p(box[3], box[2], CV_32F);
    for (int y = 0; y < box[3]; y++) {
        float* row = p.ptr<float>(y);
        const float* from = logits + static_cast<size_t>(box[1] + y) * side + box[0];
        for (int x = 0; x < box[2]; x++) row[x] = 1.0f / (1.0f + std::exp(-from[x]));
    }
    cv::Mat out;
    cv::resize(p, out, cv::Size(w, h), 0, 0, cv::INTER_LINEAR);
    return out;
}

// `crop_model.mask_quad`: the mask's largest part as four straight sides and
// the corners where they meet, as fractions of the photograph.
std::optional<Quad> mask_quad(const cv::Mat& prob, double* cover) {
    int rows = prob.rows, cols = prob.cols;
    if (cover) *cover = 0;
    cv::Mat m = prob > MASK;  // 255 where so
    m = m / 255;
    cv::Mat lab, st, centres;
    int n = cv::connectedComponentsWithStats(m, lab, st, centres, 4);
    if (n <= 1) return std::nullopt;
    int k = 1;
    for (int i = 2; i < n; i++)
        if (st.at<int>(i, cv::CC_STAT_AREA) > st.at<int>(k, cv::CC_STAT_AREA)) k = i;
    cv::Mat comp = lab == k;
    comp = comp / 255;
    std::vector<std::vector<cv::Point>> cs;
    cv::findContours(comp, cs, cv::RETR_EXTERNAL, cv::CHAIN_APPROX_NONE);
    size_t best = 0;
    double best_area = -1;
    for (size_t i = 0; i < cs.size(); i++) {
        double a = cv::contourArea(cs[i]);
        if (a > best_area) best = i, best_area = a;
    }
    const std::vector<cv::Point>& cnt = cs[best];
    if (cover) *cover = best_area / (static_cast<double>(cols) * rows);
    std::vector<cv::Point> hull;
    cv::convexHull(cnt, hull, false, true);
    double peri = cv::arcLength(hull, true);
    std::vector<cv::Point2d> q0;
    double step = (0.12 - 0.01) / 22;
    for (int i = 0; i < 23; i++) {
        double e = i == 22 ? 0.12 : i * step + 0.01;
        std::vector<cv::Point> ap;
        cv::approxPolyDP(hull, ap, e * peri, true);
        if (ap.size() == 4) {
            for (const auto& p : ap) q0.emplace_back(p.x, p.y);
            break;
        }
        if (ap.size() < 4) break;
    }
    if (q0.empty()) {
        cv::Point2f box[4];
        cv::minAreaRect(cnt).points(box);
        for (const auto& p : box) q0.emplace_back(p.x, p.y);
    }
    Quad q = ordered(q0);
    double diag = std::hypot(cols, rows);
    std::array<Line, 4> lines;
    for (int i = 0; i < 4; i++) {
        cv::Point2d a = q[i], b = q[(i + 1) % 4];
        double length = norm(b - a);
        cv::Point2d d = (b - a) / std::max(length, 1e-9), nrm(-d.y, d.x);
        std::vector<cv::Point2d> p;
        for (const auto& c : cnt) {
            cv::Point2d v(c.x - a.x, c.y - a.y);
            double t = v.x * d.x + v.y * d.y, off = v.x * nrm.x + v.y * nrm.y;
            if (t > 0.1 * length && t < 0.9 * length && std::abs(off) < 0.03 * diag) p.emplace_back(c.x, c.y);
        }
        lines[i] = Line{a, d};
        if (p.size() >= 10) {
            for (int round = 0; round < 2; round++) {
                std::vector<cv::Point2f> f(p.begin(), p.end());
                cv::Vec4f l = fit(f, cv::DIST_L2);
                std::vector<double> r(p.size());
                for (size_t j = 0; j < p.size(); j++)
                    r[j] = std::abs((p[j].x - static_cast<double>(l[2])) * static_cast<double>(l[1]) -
                                    (p[j].y - static_cast<double>(l[3])) * static_cast<double>(l[0]));
                double most = quantile(r, 0.8);
                std::vector<cv::Point2d> kept;
                for (size_t j = 0; j < p.size(); j++)
                    if (r[j] <= most) kept.push_back(p[j]);
                if (kept.size() >= 8) p = kept;
            }
            std::vector<cv::Point2f> f(p.begin(), p.end());
            cv::Vec4f l = fit(f, cv::DIST_HUBER);
            lines[i] = Line{cv::Point2d(l[2], l[3]), cv::Point2d(l[0], l[1])};
        }
    }
    Quad out = q;
    for (int i = 0; i < 4; i++) {
        auto c = meet(lines[(i + 3) % 4], lines[i]);
        if (c && norm(*c - q[i]) < 0.1 * diag) out[i] = *c;
    }
    for (auto& p : out) p = cv::Point2d(std::clamp(p.x / cols, 0.0, 1.0), std::clamp(p.y / rows, 0.0, 1.0));
    return out;
}

// `cut._gray` at the phone's size (`PHOTO_SIDE`, under `SNAP_SIDE`: the
// server's LANCZOS is never needed).
cv::Mat gray_of(const cv::Mat& rgb) {
    cv::Mat small = rgb;
    double scale = std::min(1.0, static_cast<double>(SNAP_SIDE) / std::max(rgb.cols, rgb.rows));
    if (scale < 1.0)
        cv::resize(rgb, small,
                   cv::Size(std::max(1, static_cast<int>(std::nearbyint(rgb.cols * scale))),
                            std::max(1, static_cast<int>(std::nearbyint(rgb.rows * scale)))),
                   0, 0, cv::INTER_AREA);
    cv::Mat gray, blurred, out;
    cv::cvtColor(small, gray, cv::COLOR_RGB2GRAY);
    cv::GaussianBlur(gray, blurred, cv::Size(5, 5), 0);
    blurred.convertTo(out, CV_32F);
    return out;
}

// `cut.snap` (of no layer's kind): the quad set on the picture's own edges.
Quad snap(const cv::Mat& rgb, const Quad& quad) {
    cv::Mat gray = gray_of(rgb);
    int h = gray.rows, w = gray.cols;
    cv::Mat gx, gy;
    cv::Sobel(gray, gx, CV_32F, 1, 0, 3);
    cv::Sobel(gray, gy, CV_32F, 0, 1, 3);
    Quad q;
    for (int i = 0; i < 4; i++) q[i] = cv::Point2d(quad[i].x * w, quad[i].y * h);
    cv::Point2d centre((q[0].x + q[1].x + q[2].x + q[3].x) / 4.0, (q[0].y + q[1].y + q[2].y + q[3].y) / 4.0);
    double reach = BAND * std::max(w, h);
    // np.arange(-reach, reach + 1.0)
    double start = -reach, stop = reach + 1.0;
    int many = static_cast<int>(std::ceil(stop - start));
    std::vector<double> offsets(many), weight(many);
    for (int j = 0; j < many; j++) {
        offsets[j] = start + j;
        weight[j] = 1.0 - 0.5 * std::abs(offsets[j]) / std::max(reach, 1.0);
    }
    double step = (0.92 - 0.08) / (SAMPLES - 1);
    std::array<Line, 4> lines;
    for (int i = 0; i < 4; i++) {
        cv::Point2d a = q[i], b = q[(i + 1) % 4];
        cv::Point2d along = (b - a) / std::max(norm(b - a), 1e-9);
        cv::Point2d normal(-along.y, along.x);
        if ((centre - a).dot(normal) < 0) normal = -normal;
        std::vector<cv::Point2f> found;
        for (int n = 0; n < SAMPLES; n++) {
            double s = n == SAMPLES - 1 ? 0.92 : n * step + 0.08;
            cv::Point2d p = a + s * (b - a);
            double best = -1, gk = 0;
            cv::Point2d at;
            for (int j = 0; j < many; j++) {
                cv::Point2d pt(p.x + offsets[j] * normal.x, p.y + offsets[j] * normal.y);
                int xi = std::clamp(static_cast<int>(std::nearbyint(pt.x)), 0, w - 1);
                int yi = std::clamp(static_cast<int>(std::nearbyint(pt.y)), 0, h - 1);
                double g = std::abs(static_cast<double>(gx.at<float>(yi, xi)) * normal.x +
                                    static_cast<double>(gy.at<float>(yi, xi)) * normal.y);
                double gw = g * weight[j];
                if (gw > best) best = gw, gk = g, at = pt;
            }
            if (gk > STRENGTH) found.emplace_back(static_cast<float>(at.x), static_cast<float>(at.y));
        }
        lines[i] = Line{a, along};
        if (found.size() >= SAMPLES * 0.3) {
            cv::Vec4f l = fit(found, cv::DIST_HUBER);
            int near = 0;
            for (const auto& f : found) {
                float off = std::abs((f.x - l[2]) * l[1] - (f.y - l[3]) * l[0]);
                near += off < static_cast<float>(ON_LINE);
            }
            if (static_cast<double>(near) / found.size() >= LINE_SHARE)
                lines[i] = Line{cv::Point2d(l[2], l[3]), cv::Point2d(l[0], l[1])};
        }
    }
    Quad out = q;
    for (int i = 0; i < 4; i++) {
        auto c = meet(lines[(i + 3) % 4], lines[i]);
        if (c) out[i] = *c;
    }
    for (auto& p : out) p = cv::Point2d(p.x / w, p.y / h);
    auto snapped = valid(out);
    return snapped ? *snapped : quad;
}

// `crop_model.upright_off`: how far (degrees) from an upright rectangle.
double upright_off(const Quad& quad, int w, int h) {
    std::vector<cv::Point2d> given(quad.begin(), quad.end());
    Quad p = ordered(given);
    for (auto& c : p) c = cv::Point2d(c.x * w, c.y * h);
    double worst = 0;
    for (int i = 0; i < 4; i++) {
        cv::Point2d u = p[(i + 3) % 4] - p[i], v = p[(i + 1) % 4] - p[i];
        double cos = u.dot(v) / std::max(norm(u) * norm(v), 1e-9);
        worst = std::max(worst, std::abs(90.0 - std::acos(std::clamp(cos, -1.0, 1.0)) * 180.0 / M_PI));
    }
    for (int i = 0; i < 4; i++) {
        cv::Point2d d = p[(i + 1) % 4] - p[i];
        double ang = std::atan2(std::abs(d.y), std::abs(d.x)) * 180.0 / M_PI;
        worst = std::max(worst, std::min(ang, 90.0 - ang));
    }
    return worst;
}

// `crop_model.decide`: 0 whole, 1 cut, 2 unsure.
int decide(double sure, const std::optional<Quad>& quad, int w, int h) {
    if (sure <= WHOLE) return 0;
    if (sure < SURE || !quad) return 2;
    return upright_off(*quad, w, h) <= UPRIGHT ? 1 : 2;
}

}  // namespace frame::crop

namespace {

int failed(const char* why, char* error, int error_size) {
    if (error && error_size > 0) std::snprintf(error, static_cast<size_t>(error_size), "%s", why);
    return -1;
}

void put(const frame::crop::Quad& q, double* into) {
    for (int i = 0; i < 4; i++) into[2 * i] = q[i].x, into[2 * i + 1] = q[i].y;
}

}  // namespace

extern "C" {

int frame_crop_letterbox(const unsigned char* pixels, int rows, int columns, int side, float* into, int* box,
                         char* error, int error_size) {
    try {
        if (!pixels || !into || !box || rows <= 0 || columns <= 0 || side <= 0)
            return failed("no picture", error, error_size);
        cv::Mat rgb(rows, columns, CV_8UC3, const_cast<unsigned char*>(pixels));
        cv::Vec4i b = frame::crop::letterbox(rgb, side, into);
        for (int i = 0; i < 4; i++) box[i] = b[i];
        return 0;
    } catch (const std::exception& err) {
        return failed(err.what(), error, error_size);
    } catch (...) {
        return failed("the photograph could not be made the model's", error, error_size);
    }
}

int frame_crop_find(const unsigned char* pixels, int rows, int columns, const float* logits, int side, double sure,
                    double* work, double* surround, int* found, char* error, int error_size) {
    using namespace frame::crop;
    try {
        if (!pixels || !logits || !work || !surround || !found || rows <= 0 || columns <= 0 || side <= 0)
            return failed("no picture", error, error_size);
        cv::Mat rgb(rows, columns, CV_8UC3, const_cast<unsigned char*>(pixels));
        std::vector<float> scratch(static_cast<size_t>(3) * side * side);
        cv::Vec4i box = letterbox(rgb, side, scratch.data());
        size_t plane = static_cast<size_t>(side) * side;
        std::optional<Quad> shown, around;
        if (auto q = mask_quad(probabilities(logits, side, box, columns, rows), nullptr))
            if ((shown = valid(*q))) shown = snap(rgb, *shown);
        if (auto q = mask_quad(probabilities(logits + plane, side, box, columns, rows), nullptr))
            around = valid(*q);
        if (around && (!shown || area_of(*around) <= area_of(*shown) || !holds(*around, *shown))) around.reset();
        *found = (shown ? 1 : 0) | (around ? 2 : 0);
        if (shown) put(*shown, work);
        if (around) put(*around, surround);
        return decide(sure, shown, columns, rows);
    } catch (const std::exception& err) {
        return failed(err.what(), error, error_size);
    } catch (...) {
        return failed("the work could not be found", error, error_size);
    }
}

}  // extern "C"
