// A museum photograph cut down to the work by the phone's model, with no
// Claude (Mateusz 2026-11-20): what `imaging/crop_model.py` makes of the
// model's masks and how sure it is, and `imaging/cut.py`'s `snap` and
// `valid`, written a second time; and a print's sheet cut down round its
// impression (`crop_model.plate`, Mateusz 2026-11-24). The Python is the truth: a change there
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
#include <tuple>
#include <utility>
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

// `crop_model._inside`: the pixels whose middles are inside the quad, 255.
cv::Mat inside(const Quad& quad, int columns, int rows) {
    std::array<cv::Point2d, 4> q;
    for (int i = 0; i < 4; i++) q[i] = {quad[i].x * columns, quad[i].y * rows};
    double turn = 0;
    for (int i = 0; i < 4; i++) turn += q[i].x * q[(i + 1) % 4].y - q[(i + 1) % 4].x * q[i].y;
    double sign = turn > 0 ? 1.0 : -1.0;
    cv::Mat mask = cv::Mat::zeros(rows, columns, CV_8U);
    for (int r = 0; r < rows; r++) {
        unsigned char* row = mask.ptr<unsigned char>(r);
        double y = r + 0.5;
        for (int c = 0; c < columns; c++) {
            double x = c + 0.5;
            bool in = true;
            for (int i = 0; i < 4 && in; i++) {
                const cv::Point2d &a = q[i], &b = q[(i + 1) % 4];
                in = sign * ((b.x - a.x) * (y - a.y) - (b.y - a.y) * (x - a.x)) >= 0;
            }
            row[c] = in ? 255 : 0;
        }
    }
    return mask;
}

// `crop_model.framed`: whether the band between the work and what is round
// it looks like a frame (FRAME_CHROMA, FRAME_APART).
bool framed(const cv::Mat& rgb, const Quad& work, const Quad& around) {
    cv::Mat as_float, lab;
    rgb.convertTo(as_float, CV_32FC3, 1.0 / 255.0);
    cv::cvtColor(as_float, lab, cv::COLOR_RGB2Lab);
    cv::Mat outer = inside(around, rgb.cols, rgb.rows), band, grown, strip;
    cv::subtract(outer, inside(work, rgb.cols, rgb.rows), band);
    if (cv::countNonZero(band) == 0) return false;
    cv::Mat kernel = cv::getStructuringElement(cv::MORPH_RECT, cv::Size(2 * FRAME_EDGE + 1, 2 * FRAME_EDGE + 1));
    cv::dilate(outer, grown, kernel);
    cv::subtract(grown, outer, strip);
    cv::Scalar mean = cv::mean(lab, band);
    if (std::hypot(mean[1], mean[2]) >= FRAME_CHROMA) return true;
    if (cv::countNonZero(strip) == 0) return false;
    cv::Scalar out = cv::mean(lab, strip);
    double d = std::sqrt((mean[0] - out[0]) * (mean[0] - out[0]) + (mean[1] - out[1]) * (mean[1] - out[1]) +
                         (mean[2] - out[2]) * (mean[2] - out[2]));
    return d >= FRAME_APART;
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
int decide(double sure, const std::optional<Quad>& quad, int w, int h, double cut_at) {
    if (sure <= WHOLE) return 0;
    if (sure < cut_at || !quad) return 2;
    return upright_off(*quad, w, h) <= UPRIGHT ? 1 : 2;
}

// A print's impression on its sheet set upright (`crop_model.Impression`):
// its box turned by `turn` degrees about `middle`.
struct Impression {
    std::array<double, 4> box;  // left, top, right, bottom
    std::array<double, 4> inked;  // the same with its lettering (`cut_caption` leaves it out)
    std::vector<std::array<double, 4>> others;  // the sheet's other inked parts, as `box`
    double edged = 1.0;  // how much of its box's edges it lies along (`crop_model._edged`)
    std::vector<cv::Point2d> lines;  // the squares the drawing's fine lines are in (`crop_model._lines`), as `box`: u, v
    double turn = 0;
    cv::Point2d middle;
    int cols = 0, rows = 0;
    cv::Mat to_sheet;

    std::array<cv::Point2d, 4> corners(double grow = 0) const { return corners_of(box, grow); }

    std::array<cv::Point2d, 4> corners_of(const std::array<double, 4>& of, double grow = 0) const {
        double u0 = of[0] - grow, v0 = of[1] - grow, u1 = of[2] + grow, v1 = of[3] + grow;
        double a = turn * M_PI / 180.0, ca = std::cos(a), sa = std::sin(a);
        std::array<std::array<double, 2>, 4> uv{{{u0, v0}, {u1, v0}, {u1, v1}, {u0, v1}}};
        std::array<cv::Point2d, 4> out;
        for (int i = 0; i < 4; i++)
            out[i] = {middle.x + uv[i][0] * ca - uv[i][1] * sa, middle.y + uv[i][0] * sa + uv[i][1] * ca};
        return out;
    }

    std::array<double, 4> margins() const { return margins_of(box); }

    std::array<double, 4> margins_of(const std::array<double, 4>& of) const {
        auto q = corners_of(of);
        return {(q[0].x + q[3].x) / 2, (q[0].y + q[1].y) / 2, cols - (q[1].x + q[2].x) / 2,
                rows - (q[2].y + q[3].y) / 2};
    }

    Quad on_photo(const std::array<cv::Point2d, 4>& q, int w, int h) const {
        std::vector<cv::Point2f> from, back;
        for (const auto& p : q) from.emplace_back(static_cast<float>(p.x), static_cast<float>(p.y));
        cv::Mat inverse;
        cv::invert(to_sheet, inverse);
        cv::perspectiveTransform(from, back, inverse);
        Quad out;
        for (int i = 0; i < 4; i++)
            out[i] = {static_cast<double>(back[i].x) / w, static_cast<double>(back[i].y) / h};
        return out;
    }
};

// NumPy's `median` of floats (of float32: the two middle ones' mean in float).
float median_of(std::vector<float> v) {
    size_t n = v.size(), mid = n / 2;
    std::nth_element(v.begin(), v.begin() + static_cast<long>(mid), v.end());
    float hi = v[mid];
    if (n % 2) return hi;
    float lo = *std::max_element(v.begin(), v.begin() + static_cast<long>(mid));
    return (lo + hi) / 2.0f;
}

double median_of(std::vector<double> v) {
    size_t n = v.size(), mid = n / 2;
    std::nth_element(v.begin(), v.begin() + static_cast<long>(mid), v.end());
    double hi = v[mid];
    if (n % 2) return hi;
    double lo = *std::max_element(v.begin(), v.begin() + static_cast<long>(mid));
    return (lo + hi) / 2.0;
}

// `quantile` of the low and high share `q` and 1 - `q` at once, as NumPy's.
std::pair<double, double> ends_of(std::vector<double> v, double q) {
    auto at = [&](double share) {
        double where = share * static_cast<double>(v.size() - 1);
        double below = std::floor(where), gamma = where - below;
        size_t lo = static_cast<size_t>(below);
        std::nth_element(v.begin(), v.begin() + static_cast<long>(lo), v.end());
        double a = v[lo];
        double b = lo + 1 < v.size() ? *std::min_element(v.begin() + static_cast<long>(lo) + 1, v.end()) : a;
        double diff = b - a;
        return gamma >= 0.5 ? b - diff * (1 - gamma) : a + diff * gamma;
    };
    double lo = at(q);
    return {lo, at(1 - q)};
}

// `crop_model._spread_above`: the median and PLATE_SPREAD median deviations.
float spread_above(const std::vector<float>& values) {
    float mid = median_of(values);
    std::vector<float> off(values.size());
    for (size_t i = 0; i < values.size(); i++) off[i] = std::abs(values[i] - mid);
    return mid + static_cast<float>(PLATE_SPREAD) * median_of(off);
}

// `crop_model.upright`: the sheet set upright, its long side PLATE_SIDE.
cv::Mat upright(const cv::Mat& rgb, const Quad& sheet, cv::Mat& to_sheet) {
    std::array<cv::Point2f, 4> q;
    for (int i = 0; i < 4; i++)
        q[i] = {static_cast<float>(sheet[i].x * rgb.cols), static_cast<float>(sheet[i].y * rgb.rows)};
    auto length = [](cv::Point2f a, cv::Point2f b) { return std::sqrt((b.x - a.x) * (b.x - a.x) + (b.y - a.y) * (b.y - a.y)); };
    float width = (length(q[0], q[1]) + length(q[3], q[2])) / 2.0f;
    float height = (length(q[0], q[3]) + length(q[1], q[2])) / 2.0f;
    float s = static_cast<float>(PLATE_SIDE) / std::max(width, height);
    int cols = std::max(8, static_cast<int>(std::nearbyint(width * s)));
    int rows = std::max(8, static_cast<int>(std::nearbyint(height * s)));
    std::array<cv::Point2f, 4> to{cv::Point2f(0, 0), cv::Point2f(cols, 0), cv::Point2f(cols, rows), cv::Point2f(0, rows)};
    to_sheet = cv::getPerspectiveTransform(q.data(), to.data());
    cv::Mat flat;
    cv::warpPerspective(rgb, flat, to_sheet, cv::Size(cols, rows), cv::INTER_AREA, cv::BORDER_REPLICATE);
    return flat;
}

// `crop_model._cut_caption`: the impression's extent along one axis without
// a caption or signature at either end.
std::pair<double, double> cut_caption(const std::vector<double>& t, double lo, double hi, double across) {
    int n = static_cast<int>(hi - lo) + 1;
    std::vector<double> prof(static_cast<size_t>(n), 0.0);
    for (double x : t) prof[static_cast<size_t>(std::clamp(static_cast<int>(x - lo), 0, n - 1))] += 1;
    for (double& p : prof) p /= std::max(1.0, across);
    double body = median_of(prof);
    int reach = static_cast<int>(PLATE_REACH * n);
    double gap = std::max(0.01, PLATE_GAP * body);
    std::array<double, 2> ends{lo, hi};
    for (int side = 0; side < 2; side++) {
        auto p = [&](int j) { return prof[static_cast<size_t>(side == 0 ? j : n - 1 - j)]; };
        int cut_at = -1;
        double sum = p(0) + p(1);
        for (int j = 2; j < static_cast<int>(PLATE_NEAR * n); j++) {
            if (p(j) <= gap && sum / j < PLATE_SPARSE * body) cut_at = j;
            sum += p(j);
        }
        if (cut_at >= 0) {
            int j = cut_at;
            while (j < n - 1 && p(j) <= gap) j++;
            cut_at = j;
        } else if (body >= PLATE_DENSE) {
            int j = 0;
            while (j < reach && p(j) < PLATE_THIN * body) j++;
            if (2 <= j && j < reach) cut_at = j;
        }
        if (cut_at > 0) ends[side] = side == 0 ? lo + cut_at : hi - cut_at;
    }
    return {ends[0], ends[1]};
}

// `crop_model.impression`: a print's impression on its sheet, where there is
// plain paper all round it.
std::optional<Impression> impression(const cv::Mat& rgb, const Quad& sheet) {
    Impression found;
    cv::Mat flat = upright(rgb, sheet, found.to_sheet);
    int rows = flat.rows, cols = flat.cols;
    cv::Mat blurred, as_float, lab;
    cv::GaussianBlur(flat, blurred, cv::Size(0, 0), 1.2);
    blurred.convertTo(as_float, CV_32FC3);
    for (int r = 0; r < rows; r++) {
        float* row = as_float.ptr<float>(r);
        for (int c = 0; c < 3 * cols; c++) row[c] = row[c] / 255.0f;
    }
    cv::cvtColor(as_float, lab, cv::COLOR_RGB2Lab);
    int least_side = std::min(cols, rows);
    int e = std::max(2, static_cast<int>(std::nearbyint(PLATE_EDGE * least_side)));
    int b = std::max(e + 3, static_cast<int>(std::nearbyint(PLATE_BAND * least_side)));
    auto in_band = [&](int r, int c) {
        bool outer = r >= e && r < rows - e && c >= e && c < cols - e;
        bool inner = r >= b && r < rows - b && c >= b && c < cols - b;
        return outer && !inner;
    };
    std::array<std::vector<float>, 3> band_colours;
    for (int r = 0; r < rows; r++)
        for (int c = 0; c < cols; c++)
            if (in_band(r, c)) {
                const cv::Vec3f& v = lab.at<cv::Vec3f>(r, c);
                for (int k = 0; k < 3; k++) band_colours[k].push_back(v[k]);
            }
    std::array<float, 3> paper;
    for (int k = 0; k < 3; k++) paper[k] = median_of(band_colours[k]);
    cv::Mat apart(rows, cols, CV_32F), light(rows, cols, CV_32F);
    for (int r = 0; r < rows; r++)
        for (int c = 0; c < cols; c++) {
            const cv::Vec3f& v = lab.at<cv::Vec3f>(r, c);
            float d0 = v[0] - paper[0], d1 = v[1] - paper[1], d2 = v[2] - paper[2];
            apart.at<float>(r, c) = std::sqrt(d0 * d0 + d1 * d1 + d2 * d2);
            light.at<float>(r, c) = v[0];
        }
    cv::Mat mean, squares, mean_squares;
    cv::blur(light, mean, cv::Size(5, 5));
    cv::multiply(light, light, squares);
    cv::blur(squares, mean_squares, cv::Size(5, 5));
    cv::Mat grain(rows, cols, CV_32F);
    for (int r = 0; r < rows; r++)
        for (int c = 0; c < cols; c++) {
            float m = mean.at<float>(r, c);
            grain.at<float>(r, c) = std::sqrt(std::max(mean_squares.at<float>(r, c) - m * m, 0.0f));
        }
    std::vector<float> band_apart, band_grain;
    for (int r = 0; r < rows; r++)
        for (int c = 0; c < cols; c++)
            if (in_band(r, c)) band_apart.push_back(apart.at<float>(r, c)), band_grain.push_back(grain.at<float>(r, c));
    float far = std::max(static_cast<float>(PLATE_APART), spread_above(band_apart));
    float rough = std::max(static_cast<float>(PLATE_GRAIN), spread_above(band_grain));
    cv::Mat work = cv::Mat::zeros(rows, cols, CV_8U);
    for (int r = e; r < rows - e; r++)
        for (int c = e; c < cols - e; c++)
            work.at<unsigned char>(r, c) = apart.at<float>(r, c) > far || grain.at<float>(r, c) > rough;
    cv::morphologyEx(work, work, cv::MORPH_OPEN, cv::Mat::ones(3, 3, CV_8U));
    int grow = std::max(2, static_cast<int>(std::nearbyint(PLATE_GROW * std::max(cols, rows))));
    cv::Mat grown, parts, stats, centres;
    cv::dilate(work, grown, cv::getStructuringElement(cv::MORPH_ELLIPSE, cv::Size(2 * grow + 1, 2 * grow + 1)));
    int n = cv::connectedComponentsWithStats(grown, parts, stats, centres, 8);
    if (n < 2) return std::nullopt;
    std::vector<long> count(static_cast<size_t>(n), 0);
    long all = 0;
    for (int r = 0; r < rows; r++)
        for (int c = 0; c < cols; c++)
            if (work.at<unsigned char>(r, c)) count[static_cast<size_t>(parts.at<int>(r, c))]++, all++;
    count[0] = 0;
    int k = static_cast<int>(std::max_element(count.begin(), count.end()) - count.begin());
    std::vector<cv::Point2f> points;
    std::vector<double> xs, ys;
    for (int r = 0; r < rows; r++)
        for (int c = 0; c < cols; c++)
            if (parts.at<int>(r, c) == k && work.at<unsigned char>(r, c)) {
                points.emplace_back(static_cast<float>(c), static_cast<float>(r));
                xs.push_back(c), ys.push_back(r);
            }
    cv::RotatedRect turned_rect = cv::minAreaRect(points);
    double cx = turned_rect.center.x, cy = turned_rect.center.y;
    double turn = std::fmod(static_cast<double>(turned_rect.angle) + 45.0, 90.0);
    if (turn < 0) turn += 90.0;
    turn -= 45.0;
    auto boxed = [&](double by, std::vector<double>& u, std::vector<double>& v) {
        double a = by * M_PI / 180.0, ca = std::cos(a), sa = std::sin(a);
        u.resize(xs.size()), v.resize(xs.size());
        for (size_t i = 0; i < xs.size(); i++) {
            u[i] = (xs[i] - cx) * ca + (ys[i] - cy) * sa;
            v[i] = -(xs[i] - cx) * sa + (ys[i] - cy) * ca;
        }
        auto [u0, u1] = ends_of(u, PLATE_STRAY);
        auto [v0, v1] = ends_of(v, PLATE_STRAY);
        return std::array<double, 4>{u0, v0, u1 + 1, v1 + 1};
    };
    auto size = [](const std::array<double, 4>& x) { return (x[2] - x[0]) * (x[3] - x[1]); };
    std::vector<double> u, v;
    std::array<double, 4> box = boxed(0.0, u, v);
    if (PLATE_TURN_LEAST < std::abs(turn) && std::abs(turn) <= PLATE_TURN) {
        std::vector<double> tu, tv;
        std::array<double, 4> tbox = boxed(turn, tu, tv);
        if (size(tbox) <= PLATE_TURN_GAIN * size(box)) {
            u.swap(tu), v.swap(tv), box = tbox;
        } else {
            turn = 0.0;
        }
    } else {
        turn = 0.0;
    }
    std::vector<double> ku, kv;
    for (size_t i = 0; i < u.size(); i++)
        if (u[i] >= box[0] && u[i] <= box[2] && v[i] >= box[1] && v[i] <= box[3]) ku.push_back(u[i]), kv.push_back(v[i]);
    found.inked = box;
    std::tie(box[0], box[2]) = cut_caption(ku, box[0], box[2], box[3] - box[1]);
    std::tie(box[1], box[3]) = cut_caption(kv, box[1], box[3], box[2] - box[0]);
    found.box = box;
    {
        // `crop_model._edged`: how much of its box's edges it lies along.
        double u0 = box[0], v0 = box[1], u1 = box[2], v1 = box[3];
        double d = std::max(3.0, PLATE_EDGE_DEPTH * std::min(u1 - u0, v1 - v0));
        int nu = std::max(1, static_cast<int>(u1 - u0)), nv = std::max(1, static_cast<int>(v1 - v0));
        std::vector<char> top(static_cast<size_t>(nu), 0), bottom(static_cast<size_t>(nu), 0);
        std::vector<char> left(static_cast<size_t>(nv), 0), right(static_cast<size_t>(nv), 0);
        for (size_t i = 0; i < ku.size(); i++) {
            double uu = ku[i], vv = kv[i];
            if (!(uu >= u0 && uu < u1 && vv >= v0 && vv < v1)) continue;
            size_t across = static_cast<size_t>(std::clamp(static_cast<int>(uu - u0), 0, nu - 1));
            size_t down = static_cast<size_t>(std::clamp(static_cast<int>(vv - v0), 0, nv - 1));
            if (vv < v0 + d) top[across] = 1;
            if (vv >= v1 - d) bottom[across] = 1;
            if (uu < u0 + d) left[down] = 1;
            if (uu >= u1 - d) right[down] = 1;
        }
        auto share = [](const std::vector<char>& x) {
            return static_cast<double>(std::count(x.begin(), x.end(), 1)) / static_cast<double>(x.size());
        };
        found.edged = (share(top) + share(bottom) + share(left) + share(right)) / 4.0;
    }
    found.turn = turn;
    found.middle = {cx, cy};
    {
        // `crop_model._others`: the other inked parts, all but specks.
        double a = turn * M_PI / 180.0, ca = std::cos(a), sa = std::sin(a);
        const double inf = std::numeric_limits<double>::infinity();
        std::vector<std::array<double, 4>> spans(static_cast<size_t>(n), {inf, inf, -inf, -inf});
        for (int r = 0; r < rows; r++)
            for (int c = 0; c < cols; c++) {
                if (!work.at<unsigned char>(r, c)) continue;
                int j = parts.at<int>(r, c);
                if (j == 0 || j == k) continue;
                double uu = (c - cx) * ca + (r - cy) * sa, vv = -(c - cx) * sa + (r - cy) * ca;
                auto& x = spans[static_cast<size_t>(j)];
                x[0] = std::min(x[0], uu), x[1] = std::min(x[1], vv);
                x[2] = std::max(x[2], uu + 1), x[3] = std::max(x[3], vv + 1);
            }
        for (int j = 1; j < n; j++)
            if (j != k && static_cast<double>(count[static_cast<size_t>(j)]) >= PLATE_PART * rows * cols)
                found.others.push_back(spans[static_cast<size_t>(j)]);
    }
    {
        // `crop_model._lines`: the drawing's fine lines, darker than what
        // lies round them.
        cv::Mat dark;
        cv::morphologyEx(light, dark, cv::MORPH_BLACKHAT,
                         cv::getStructuringElement(cv::MORPH_ELLIPSE, cv::Size(PLATE_LINE, PLATE_LINE)));
        std::vector<float> band_dark;
        for (int r = 0; r < rows; r++)
            for (int c = 0; c < cols; c++)
                if (in_band(r, c)) band_dark.push_back(dark.at<float>(r, c));
        float least_dark = std::max(static_cast<float>(PLATE_FAINT), spread_above(band_dark));
        cv::Mat line = cv::Mat::zeros(rows, cols, CV_8U);
        for (int r = e; r < rows - e; r++)
            for (int c = e; c < cols - e; c++) line.at<unsigned char>(r, c) = dark.at<float>(r, c) > least_dark;
        cv::morphologyEx(line, line, cv::MORPH_OPEN, cv::Mat::ones(2, 2, CV_8U));
        // Counted in squares, each where its middle is.
        double a = turn * M_PI / 180.0, ca = std::cos(a), sa = std::sin(a);
        int n_r = rows / PLATE_CELL, n_c = cols / PLATE_CELL;
        for (int i = 0; i < n_r; i++)
            for (int j = 0; j < n_c; j++) {
                int in = cv::countNonZero(line(cv::Rect(j * PLATE_CELL, i * PLATE_CELL, PLATE_CELL, PLATE_CELL)));
                if (in < PLATE_CELL_LEAST) continue;
                double x = (j + 0.5) * PLATE_CELL, y = (i + 0.5) * PLATE_CELL;
                found.lines.emplace_back((x - cx) * ca + (y - cy) * sa, -(x - cx) * sa + (y - cy) * ca);
            }
    }
    found.cols = cols, found.rows = rows;
    // Plain paper round it: alike on every side, light, and little on it.
    std::array<cv::Rect, 4> sides{cv::Rect(e, e, cols - 2 * e, b - e), cv::Rect(e, rows - b, cols - 2 * e, b - e),
                                  cv::Rect(e, e, b - e, rows - 2 * e), cv::Rect(cols - b, e, b - e, rows - 2 * e)};
    std::array<std::array<float, 3>, 4> med;
    for (int s = 0; s < 4; s++) {
        std::array<std::vector<float>, 3> colours;
        for (int r = sides[s].y; r < sides[s].y + sides[s].height; r++)
            for (int c = sides[s].x; c < sides[s].x + sides[s].width; c++) {
                const cv::Vec3f& x = lab.at<cv::Vec3f>(r, c);
                for (int j = 0; j < 3; j++) colours[j].push_back(x[j]);
            }
        for (int j = 0; j < 3; j++) med[s][j] = median_of(colours[j]);
    }
    float sides_apart = 0;
    for (const auto& p : med)
        for (const auto& q : med) {
            float d0 = p[0] - q[0], d1 = p[1] - q[1], d2 = p[2] - q[2];
            sides_apart = std::max(sides_apart, std::sqrt(d0 * d0 + d1 * d1 + d2 * d2));
        }
    cv::Mat filled = cv::Mat::zeros(rows, cols, CV_8U), near;
    std::vector<cv::Point> outline;
    for (const auto& p : found.corners())
        outline.emplace_back(static_cast<int>(std::nearbyint(p.x)), static_cast<int>(std::nearbyint(p.y)));
    cv::fillPoly(filled, std::vector<std::vector<cv::Point>>{outline}, cv::Scalar(1));
    cv::dilate(filled, near, cv::Mat::ones(2 * grow + 1, 2 * grow + 1, CV_8U));
    long beyond = 0, loose = 0;
    for (int r = e; r < rows - e; r++)
        for (int c = e; c < cols - e; c++)
            if (!near.at<unsigned char>(r, c)) {
                beyond++;
                loose += apart.at<float>(r, c) > static_cast<float>(PLATE_LOOSE) ||
                         grain.at<float>(r, c) > static_cast<float>(PLATE_LOOSE_GRAIN);
            }
    double busy = beyond > 50 ? static_cast<double>(loose) / static_cast<double>(beyond) : 1.0;
    bool plain = busy <= PLATE_BUSY && rough <= PLATE_GRAIN_MOST &&
                 static_cast<double>(count[static_cast<size_t>(k)]) / std::max(1L, all) >= PLATE_WHOLE &&
                 sides_apart <= PLATE_SIDES && paper[0] >= PLATE_LIGHT &&
                 size(box) >= PLATE_LEAST * cols * rows;
    if (!plain) return std::nullopt;
    return found;
}

// `crop_model.plate`: the sheet cut down round its impression when its paper
// is wide (PLATE_OVER): the impression and PLATE_MARGIN round it, the same on
// every side; and the impression alone.
// `crop_model.kept`: corners within the picture, to five places.
Quad kept(const Quad& q) {
    Quad out;
    for (int i = 0; i < 4; i++)
        out[i] = {round5(std::clamp(q[i].x, 0.0, 1.0)), round5(std::clamp(q[i].y, 0.0, 1.0))};
    return out;
}

std::optional<std::pair<Quad, Quad>> plate(const cv::Mat& rgb, const Quad& sheet, double over) {
    auto found = impression(rgb, sheet);
    if (!found) return std::nullopt;
    double least = std::min(found->box[2] - found->box[0], found->box[3] - found->box[1]);
    auto margins = found->margins();
    if (*std::max_element(margins.begin(), margins.end()) <= over * least) return std::nullopt;
    // The margin round the impression with its lettering, and round
    // whatever else it would cut through.
    auto inked = found->inked;
    double pad = 0;
    for (int round = 0; round < 3; round++) {
        least = std::min(inked[2] - inked[0], inked[3] - inked[1]);
        margins = found->margins_of(inked);
        pad = std::max(0.0, std::min(PLATE_MARGIN * least, *std::min_element(margins.begin(), margins.end())));
        std::array<double, 4> reach{inked[0] - pad, inked[1] - pad, inked[2] + pad, inked[3] + pad};
        bool touched = false;
        auto grown = inked;
        for (const auto& o : found->others) {
            bool meets = o[0] < reach[2] && o[2] > reach[0] && o[1] < reach[3] && o[3] > reach[1];
            bool inside = o[0] >= reach[0] && o[1] >= reach[1] && o[2] <= reach[2] && o[3] <= reach[3];
            if (!meets || inside) continue;
            touched = true;
            grown[0] = std::min(grown[0], o[0]), grown[1] = std::min(grown[1], o[1]);
            grown[2] = std::max(grown[2], o[2]), grown[3] = std::max(grown[3], o[3]);
        }
        if (!touched) break;
        inked = grown;
    }
    // A cut that leaves the drawing out is none.
    if (!found->lines.empty()) {
        long out = 0;
        for (const auto& p : found->lines)
            out += p.x < inked[0] - pad || p.x > inked[2] + pad || p.y < inked[1] - pad;  // not under it: lettering
        if (static_cast<double>(out) / static_cast<double>(found->lines.size()) > PLATE_DRAWN && found->edged < PLATE_EDGED)
            return std::nullopt;
    }
    auto cut = valid(found->on_photo(found->corners_of(inked, pad), rgb.cols, rgb.rows));
    if (!cut) return std::nullopt;
    return std::make_pair(*cut, kept(found->on_photo(found->corners(), rgb.cols, rgb.rows)));
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

double frame_crop_upright(const double* quad, int rows, int columns) {
    if (!quad || rows <= 0 || columns <= 0) return 90.0;
    frame::crop::Quad q;
    for (int i = 0; i < 4; i++) q[i] = {quad[2 * i], quad[2 * i + 1]};
    return frame::crop::upright_off(q, columns, rows);
}

int frame_crop_plate(const unsigned char* pixels, int rows, int columns, const double* sheet, double over,
                     double* cut, double* plate, int* found, char* error, int error_size) {
    using namespace frame::crop;
    try {
        if (!pixels || !sheet || !cut || !plate || !found || rows <= 0 || columns <= 0)
            return failed("no picture", error, error_size);
        cv::Mat rgb(rows, columns, CV_8UC3, const_cast<unsigned char*>(pixels));
        Quad given;
        for (int i = 0; i < 4; i++) given[i] = {sheet[2 * i], sheet[2 * i + 1]};
        *found = 0;
        auto made = frame::crop::plate(rgb, given, over);
        if (!made) return 0;
        put(made->first, cut);
        put(made->second, plate);
        *found = 3;
        return 1;
    } catch (const std::exception& err) {
        return failed(err.what(), error, error_size);
    } catch (...) {
        return failed("the impression could not be found", error, error_size);
    }
}

int frame_crop_find(const unsigned char* pixels, int rows, int columns, const float* logits, int side, double sure,
                    double cut_at, double* work, double* surround, int* found, char* error, int error_size) {
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
        if (around && (!shown || area_of(*around) <= area_of(*shown) || !holds(*around, *shown) ||
                       !framed(rgb, *shown, *around)))
            around.reset();
        *found = (shown ? 1 : 0) | (around ? 2 : 0);
        if (shown) put(*shown, work);
        if (around) put(*around, surround);
        return decide(sure, shown, columns, rows, cut_at);
    } catch (const std::exception& err) {
        return failed(err.what(), error, error_size);
    } catch (...) {
        return failed("the work could not be found", error, error_size);
    }
}

}  // extern "C"
