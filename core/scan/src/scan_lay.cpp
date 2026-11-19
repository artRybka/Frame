// The side photographs laid over the first: `_marks`, `_lay`, `_settled`
// and what they are made of in `imaging/reflections.py`.
#include "scan_detail.hpp"

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <tuple>

#include <opencv2/geometry.hpp>

namespace frame::scan {

using namespace np;

std::array<cv::Point2d, 4> grown(const std::array<cv::Point2d, 4>& corners) {
    cv::Point2d middle(0, 0);
    for (const auto& c : corners) middle += c;
    middle.x /= 4;
    middle.y /= 4;
    std::array<cv::Point2d, 4> out;
    for (int i = 0; i < 4; i++) out[i] = middle + (corners[i] - middle) * (1 + 2 * AROUND);
    return out;
}

M33 larger(double across, double down) {
    return M33(across, 0, (across - 1) / 2, 0, down, (down - 1) / 2, 0, 0, 1);
}

Mat resized(const Mat& img, double scale) {
    if (scale >= 1) return img;
    return resize(img, pyround(img.cols * scale), pyround(img.rows * scale), cv::INTER_AREA);
}

static Mat to_linear() {
    Mat lut(1, 256, CV_32F);
    for (int i = 0; i < 256; i++) {
        double v = i / 255.0;
        lut.at<float>(i) = static_cast<float>(v <= 0.04045 ? v / 12.92 : std::pow((v + 0.055) / 1.055, 2.4));
    }
    return lut;
}

Mat linear(const Mat& img) {
    static const Mat lut = to_linear();
    Mat out;
    cv::LUT(img, lut, out);
    return out;
}

static std::vector<uint8_t> from_linear() {
    std::vector<uint8_t> lut(65536);
    for (int i = 0; i < 65536; i++) {
        double v = i / 65535.0;
        double coded = v <= 0.0031308 ? v * 12.92 : 1.055 * std::pow(v, 1 / 2.4) - 0.055;
        lut[i] = static_cast<uint8_t>(coded * 255 + 0.5);
    }
    return lut;
}

Mat srgb(const Mat& light) {
    static const std::vector<uint8_t> lut = from_linear();
    Mat out(light.rows, light.cols, CV_8UC(light.channels()));
    int n = light.cols * light.channels();
    rows(light.rows, [&](int y) {
        const float* p = light.ptr<float>(y);
        uint8_t* o = out.ptr<uint8_t>(y);
        for (int i = 0; i < n; i++) {
            float steps = clipf(p[i] * 65535.f + 0.5f, 0.f, 65535.f);
            o[i] = lut[static_cast<uint16_t>(steps)];
        }
    });
    return out;
}

// FRAME_SCAN_TRACE=1: what each step of laying took, on stderr.
struct Lap {
    std::chrono::steady_clock::time_point last = std::chrono::steady_clock::now();
    bool on = std::getenv("FRAME_SCAN_TRACE") != nullptr;
    void operator()(const char* what) {
        auto now = std::chrono::steady_clock::now();
        if (on) std::fprintf(stderr, "    %-12s %.2f s\n", what, std::chrono::duration<double>(now - last).count());
        last = now;
    }
};

Marks marks(const Mat& img) {
    auto sift = cv::SIFT::create(8000, 3, 0.02);
    Mat grey;
    cv::cvtColor(img, grey, cv::COLOR_RGB2GRAY);
    Marks out;
    sift->detectAndCompute(grey, cv::noArray(), out.points, out.about);
    return out;
}

std::optional<View> lay(const Mat& front, const Marks& first, const Mat& photo) {
    double scale = std::min(1.0, static_cast<double>(MATCH_SIDE) / std::max(photo.rows, photo.cols));
    Lap lap;
    Mat side = resized(photo, scale);
    lap("resized");
    Marks other = marks(side);
    lap("marks");
    if (first.about.empty() || other.about.empty() || static_cast<int>(first.points.size()) < MIN_MATCHES ||
        static_cast<int>(other.points.size()) < MIN_MATCHES)
        return std::nullopt;
    std::vector<std::vector<cv::DMatch>> pairs;
    cv::BFMatcher(cv::NORM_L2).knnMatch(other.about, first.about, pairs, 2);
    lap("matched");
    std::vector<cv::Point2f> src, dst;
    for (const auto& p : pairs)
        if (p.size() == 2 && p[0].distance < 0.8 * p[1].distance) {
            src.push_back(other.points[p[0].queryIdx].pt);
            dst.push_back(first.points[p[0].trainIdx].pt);
        }
    if (static_cast<int>(src.size()) < MIN_MATCHES) return std::nullopt;
    Mat inliers;
    Mat homography = cv::findHomography(src, dst, cv::USAC_MAGSAC, 2.0, inliers);
    lap("homography");
    if (homography.empty() || inliers.empty() || cv::countNonZero(inliers) < MIN_MATCHES) return std::nullopt;
    M33 found(homography.ptr<double>());
    int ht = front.rows, wd = front.cols;
    // The work's corners in the side photograph: all of it must be there,
    // and its taller side is the one the photograph was taken from.
    M33 back = inv(found);
    std::vector<cv::Point2d> rect{{0, 0}, {double(wd), 0}, {double(wd), double(ht)}, {0, double(ht)}}, ends;
    cv::perspectiveTransform(rect, ends, back);
    int sh = side.rows, sw = side.cols;
    for (const auto& e : ends)
        if (e.x < -0.02 * std::max(sh, sw) || e.y < -0.02 * std::max(sh, sw) || e.x > sw * 1.02 || e.y > sh * 1.02)
            return std::nullopt;
    double left = cv::norm(ends[3] - ends[0]);
    double right = cv::norm(ends[2] - ends[1]);
    if (std::min(left, right) <= 0) return std::nullopt;
    double lean = std::log(left / right);
    Mat over, seen;
    std::tie(over, seen) = settled(front, side, found);
    lap("settled");
    // A pixel's place is its middle, in the photograph as it was given.
    float by = static_cast<float>(scale);
    Mat there(seen.rows, seen.cols, CV_32FC2);
    rows(seen.rows, [&](int y) {
        const float* p = seen.ptr<float>(y);
        float* o = there.ptr<float>(y);
        for (int i = 0; i < seen.cols * 2; i++) o[i] = (p[i] + 0.5f) / by - 0.5f;
    });
    View view;
    view.light = linear(over);
    view.side = lean > 0.03 ? -1 : lean < -0.03 ? 1 : 0;
    view.photo = photo;
    view.seen = there;
    return view;
}

std::pair<Mat, Mat> settled(const Mat& front, const Mat& side, const M33& found) {
    int ht = front.rows, wd = front.cols;
    M33 back = inv(found);
    Mat moved = Mat::zeros(ht, wd, CV_32FC2);
    float most = static_cast<float>(wd * SETTLE_MOST);

    auto laid = [&]() -> std::pair<Mat, Mat> {
        Mat at(ht * wd, 1, CV_64FC2);
        rows(ht, [&](int y) {
            const float* m = moved.ptr<float>(y);
            cv::Vec2d* o = at.ptr<cv::Vec2d>(y * wd);
            for (int x = 0; x < wd; x++)
                o[x] = cv::Vec2d(static_cast<float>(x) + m[2 * x], static_cast<float>(y) + m[2 * x + 1]);
        });
        Mat seen64, seen;
        cv::perspectiveTransform(at, seen64, Mat(back));
        seen64.convertTo(seen, CV_32F);
        seen = seen.reshape(2, ht);
        Mat over;
        cv::remap(side, over, channel(seen, 0), channel(seen, 1), cv::INTER_LINEAR);
        return {over, seen};
    };

    auto [over, seen] = laid();
    Mat first = fine(linear(front));
    for (int size : SETTLE_TILES) {
        int tile = size;
        while (tile > 32 && tile > std::min(wd, ht) / 4) tile /= 2;
        if (tile > std::min(wd, ht) / 2) break;
        auto by = field(off(first, fine(linear(over)), tile), tile, cv::Size(wd, ht));
        if (!by) break;
        const Mat& add = *by;
        rows(ht, [&](int y) {
            float* m = moved.ptr<float>(y);
            const float* a = add.ptr<float>(y);
            for (int i = 0; i < wd * 2; i++) m[i] = clipf(m[i] + a[i], -most, most);
        });
        std::tie(over, seen) = laid();
    }
    return {over, seen};
}

Mat fine(const Mat& light) {
    Mat tone = per_pixel(light, [](const float* p) { return std::log((p[0] + p[1] + p[2]) / 3.0f + 0.02f); });
    double wide = std::max(2 * SETTLE_FINE[0], light.cols * SETTLE_FINE[1]);
    return blur(tone, SETTLE_FINE[0]) - blur(tone, wide);
}

Mat off(const Mat& first, const Mat& other, int tile) {
    int ht = first.rows, wd = first.cols;
    int step = tile / 2;
    Mat window;
    cv::createHanningWindow(window, cv::Size(tile, tile), CV_32F);
    int n_rows = ht >= tile ? (ht - tile) / step + 1 : 0;
    int n_cols = wd >= tile ? (wd - tile) / step + 1 : 0;
    Mat out = Mat::zeros(n_rows, n_cols, CV_32FC3);
    rows(n_rows, [&](int i) {
        int y = i * step;
        cv::Vec3f* o = out.ptr<cv::Vec3f>(i);
        for (int j = 0; j < n_cols; j++) {
            int x = j * step;
            // Copies: the correlation writes into what it is given.
            Mat one = first(cv::Rect(x, y, tile, tile)).clone();
            Mat two = other(cv::Rect(x, y, tile, tile)).clone();
            double sure = 0;
            cv::Point2d by = cv::phaseCorrelate(one, two, window, &sure);
            o[j] = cv::Vec3f(static_cast<float>(by.x), static_cast<float>(by.y), static_cast<float>(sure));
        }
    });
    return out;
}

Mat about(const Mat& said) {
    int n_rows = said.rows, n_cols = said.cols, ch = said.channels();
    Mat out(n_rows, n_cols, said.type());
    for (int y = 0; y < n_rows; y++)
        for (int x = 0; x < n_cols; x++)
            for (int c = 0; c < ch; c++) {
                std::vector<float> nine;
                for (int dy = -1; dy <= 1; dy++)
                    for (int dx = -1; dx <= 1; dx++) {
                        int yy = y + dy, xx = x + dx;
                        if (yy < 0 || yy >= n_rows || xx < 0 || xx >= n_cols) continue;
                        float v = said.ptr<float>(yy)[xx * ch + c];
                        if (!std::isnan(v)) nine.push_back(v);
                    }
                out.ptr<float>(y)[x * ch + c] = nine.empty() ? NaN : median(nine);
            }
    return out;
}

std::optional<Mat> field(const Mat& off, int tile, cv::Size shape) {
    if (off.rows < 2 || off.cols < 2) return std::nullopt;
    Mat across = channel(off, 0), down = channel(off, 1), said = channel(off, 2);
    float far_most = static_cast<float>(SETTLE_FAR * tile);
    Mat sure = ew(
        [far_most](float a, float d, float s) {
            float far = std::hypot(a, d);
            float v = (s >= static_cast<float>(SETTLE_SURE) && far <= far_most) ? s : 0.f;
            return clipf(v, 0.f, 1.f);
        },
        across, down, said);
    for (int round = 0; round < 2; round++) {
        Mat both(off.rows, off.cols, CV_32FC2);
        for (int y = 0; y < off.rows; y++)
            for (int x = 0; x < off.cols; x++) {
                bool is = sure.at<float>(y, x) > 0;
                both.at<cv::Vec2f>(y, x) =
                    is ? cv::Vec2f(across.at<float>(y, x), down.at<float>(y, x)) : cv::Vec2f(NaN, NaN);
            }
        Mat near = about(both);
        for (int y = 0; y < off.rows; y++)
            for (int x = 0; x < off.cols; x++) {
                cv::Vec2f n = near.at<cv::Vec2f>(y, x);
                float odd = std::hypot(across.at<float>(y, x) - n[0], down.at<float>(y, x) - n[1]);
                float allowed = std::max(static_cast<float>(SETTLE_ODD[0]),
                                         static_cast<float>(SETTLE_ODD[1]) * std::hypot(n[0], n[1]));
                // NaN: nothing about, stays.
                if (odd > allowed) sure.at<float>(y, x) = 0.f;
            }
    }
    if (!any(sure)) return std::nullopt;

    auto told = [&](double sigma) -> std::pair<Mat, Mat> {
        Mat weight = blur(sure, sigma, cv::BORDER_REPLICATE);
        Mat each[2];
        const Mat* of[2] = {&across, &down};
        for (int k = 0; k < 2; k++) {
            Mat weighed = ew([](float v, float s) { return v * s; }, *of[k], sure);
            each[k] = ew([](float v, float w) { return v / std::max(w, 1e-6f); },
                         blur(weighed, sigma, cv::BORDER_REPLICATE), weight);
        }
        Mat both;
        cv::merge(each, 2, both);
        return {both, weight};
    };

    auto [near, weight] = told(SETTLE_ABOUT[0]);
    Mat wide = told(SETTLE_ABOUT[1]).first;
    Mat mesh = ew([](float n, float w, float weight_) { return weight_ > 0.2f ? n : w; }, near, wide, weight);
    // One more square about, going on as the last two did.
    int mr = mesh.rows, mc = mesh.cols;
    Mat grown_(mr + 2, mc + 2, CV_32FC2);
    auto at = [&](int y, int x) -> cv::Vec2f& { return grown_.at<cv::Vec2f>(y, x); };
    for (int y = 0; y < mr; y++)
        for (int x = 0; x < mc; x++) at(y + 1, x + 1) = mesh.at<cv::Vec2f>(y, x);
    for (int x = 1; x <= mc; x++) {
        at(0, x) = 2 * at(1, x) - at(2, x);
        at(mr + 1, x) = 2 * at(mr, x) - at(mr - 1, x);
    }
    for (int y = 0; y < mr + 2; y++) {
        at(y, 0) = 2 * at(y, 1) - at(y, 2);
        at(y, mc + 1) = 2 * at(y, mc) - at(y, mc - 1);
    }
    // A square's middle is where it says it for; the first, one step out.
    int step = tile / 2;
    double start = (tile - 1) / 2.0 - step;
    Mat to_mesh = Mat(cv::Matx23d(1.0 / step, 0, -start / step, 0, 1.0 / step, -start / step));
    Mat out;
    cv::warpAffine(grown_, out, to_mesh, shape, cv::INTER_LINEAR | cv::WARP_INVERSE_MAP, cv::BORDER_REPLICATE);
    return out;
}

}  // namespace frame::scan
