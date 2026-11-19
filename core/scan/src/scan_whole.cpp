// The whole of it: `merge` and `_subtract` of `imaging/reflections.py`.
#include "scan_detail.hpp"

#include <opencv2/geometry.hpp>

#include <chrono>
#include <cstdlib>

namespace frame::scan {

using namespace np;

Mat around(const Mat& part) {
    int ht = part.rows, wd = part.cols;
    double by = AROUND / (1 + 2 * AROUND);
    int mx = pyround(wd * by), my = pyround(ht * by);
    if (mx < 1 || my < 1 || wd <= 4 * mx || ht <= 4 * my) return part;
    cv::Rect within(mx, my, wd - 2 * mx, ht - 2 * my);
    // "At them" is as far within the corners again.
    cv::Rect well(2 * mx, 2 * my, wd - 4 * mx, ht - 4 * my);
    Mat at;
    // (Isolated: a part of a picture would be given what the picture has around it.)
    cv::copyMakeBorder(part(well), at, 2 * my, 2 * my, 2 * mx, 2 * mx, cv::BORDER_REPLICATE | cv::BORDER_ISOLATED);
    // Evened along the edge: a place's own row or column is not drawn out.
    at = blur(at, std::max(mx, my) / 4.0);
    Mat out = ew([](float p, float a) { return clipf(p, std::min(a, 0.f), std::max(a, 0.f)); }, part, at);
    part(within).copyTo(out(within));
    return out;
}

Mat subtract(const Mat& first, const Grain& layer, const Mat& mend_, const std::optional<std::pair<Mat, Mat>>& swap,
             const M33& to_photo, const std::array<cv::Point2d, 4>& quad, const Finer& finer_, const Mat* theirs) {
    int h = first.rows, w = first.cols;
    double left = quad[0].x, right = quad[0].x, up = quad[0].y, below = quad[0].y;
    for (const auto& q : quad) {
        left = std::min(left, q.x), right = std::max(right, q.x);
        up = std::min(up, q.y), below = std::max(below, q.y);
    }
    int x0 = std::max(0, static_cast<int>(std::floor(left)) - 8);
    int x1 = std::min(w, static_cast<int>(std::ceil(right)) + 8);
    int y0 = std::max(0, static_cast<int>(std::floor(up)) - 8);
    int y1 = std::min(h, static_cast<int>(std::ceil(below)) + 8);
    Mat out = first.clone();
    if (x1 <= x0 || y1 <= y0) return out;
    bool mended = any(mend_);
    double feather = std::max(1.5, 0.002 * std::max(x1 - x0, y1 - y0));
    int wide = x1 - x0;
    int bands = (y1 - y0 + ROWS - 1) / ROWS;

    // Each band is worked out by itself: several at a time make the same
    // picture.
    cv::parallel_for_(cv::Range(0, bands), [&](const cv::Range& range) {
        for (int band = range.start; band < range.end; band++) {
            int top = y0 + band * ROWS;
            int count = std::min(ROWS, y1 - top);
            M33 to_band = M33(1, 0, -x0, 0, 1, -top, 0, 0, 1) * to_photo;
            auto laid = [&](const Mat& what, int how) {
                Mat o;
                cv::warpPerspective(what, o, Mat(to_band), cv::Size(wide, count), how, cv::BORDER_REPLICATE);
                return o;
            };
            Mat inside = Mat::zeros(count, wide, CV_8U);
            std::vector<cv::Point> corners;
            for (const auto& q : quad) corners.emplace_back(pyround(q.x - x0), pyround(q.y - top));
            cv::fillConvexPoly(inside, corners, 255);
            Mat within(count, wide, CV_32F);
            for (int y = 0; y < count; y++) {
                const uint8_t* in = inside.ptr<uint8_t>(y);
                float* o = within.ptr<float>(y);
                for (int x = 0; x < wide; x++) o[x] = static_cast<float>(in[x]) / 255.f;
            }
            Mat soft = blur(within, feather);
            Mat light = linear(first(cv::Rect(x0, top, wide, count)));
            Mat put_in;
            if (swap) {
                Mat glare = laid(swap->second, cv::INTER_LINEAR);
                if (any(glare)) {
                    Mat put = laid(swap->first, cv::INTER_CUBIC);
                    if (finer_) put = ew([](float a, float b) { return a + b; }, put, finer_(to_band, glare));
                    light = ew([](float l, float p, float g, float s) { return l + (p - l) * g * s; }, light, put,
                               glare, soft);
                    put_in = glare;
                }
            }
            light = ew(
                [](float l, float lo, float sh, float v, float s) {
                    float sheen = std::max(l - lo, 0.f) * clipf(sh, 0.f, 1.f);
                    return l - (std::max(v, 0.f) + sheen) * s;
                },
                light, laid(layer.low, cv::INTER_LINEAR), laid(layer.share, cv::INTER_LINEAR),
                laid(layer.veil, cv::INTER_CUBIC), soft);
            if (mended)
                light = ew([](float l, float m, float s) { return l - m * s; }, light, laid(mend_, cv::INTER_CUBIC),
                           soft);
            if (finer_ && theirs) {
                Mat also = laid(*theirs, cv::INTER_LINEAR);
                if (!put_in.empty()) also = ew([](float a, float p) { return a * (1 - p); }, also, put_in);
                if (any(also))
                    light = ew([](float l, float f, float a, float s) { return l + f * a * s; }, light,
                               finer_(to_band, also), also, soft);
            }
            srgb(light).copyTo(out(cv::Rect(x0, top, wide, count)));
        }
    });
    return out;
}

Merged merge(const Mat& first, const std::vector<Mat>& sides, const std::array<cv::Point2d, 4>& corners,
             bool anyway) {
    using clock = std::chrono::steady_clock;
    Merged out;
    out.image = first;
    auto last = clock::now();
    auto mark = [&](const char* part) {
        auto now = clock::now();
        out.took[part] += std::chrono::duration<double>(now - last).count();
        last = now;
    };

    int h = first.rows, w = first.cols;
    std::array<cv::Point2d, 4> quad = grown(corners);
    for (auto& q : quad) q = cv::Point2d(q.x * w, q.y * h);
    double scale = std::min(1.0, static_cast<double>(MATCH_SIDE) / std::max(h, w));
    Mat small = resized(first, scale);
    auto far = [](const cv::Point2d& a, const cv::Point2d& b) { return std::sqrt((a - b).ddot(a - b)); };
    double across = (far(quad[1], quad[0]) + far(quad[2], quad[3])) / 2 * scale;
    double down = (far(quad[3], quad[0]) + far(quad[2], quad[1])) / 2 * scale;
    if (across < 200 || down < 200) return out;
    int wd = pyround(across), ht = pyround(down);
    cv::Point2f from[4], rect[4] = {{0.f, 0.f}, {float(wd), 0.f}, {float(wd), float(ht)}, {0.f, float(ht)}};
    for (int i = 0; i < 4; i++)
        from[i] = cv::Point2f(static_cast<float>((quad[i].x + 0.5) * scale - 0.5),
                              static_cast<float>((quad[i].y + 0.5) * scale - 0.5));
    Mat found = cv::getPerspectiveTransform(from, rect);
    M33 to_work(found.ptr<double>());
    Mat front8;
    cv::warpPerspective(small, front8, found, cv::Size(wd, ht), cv::INTER_LINEAR);

    std::vector<View> views(1);
    views[0].light = linear(front8);
    Marks known = marks(front8);
    std::vector<std::optional<View>> laid(sides.size());
    // One after another: what each is made of (the points found, matched)
    // is worked out on all the cores as it is.
    for (size_t n = 0; n < sides.size(); n++) laid[n] = lay(front8, known, sides[n]);
    for (auto& view : laid)
        if (view) views.push_back(*view);
    mark("laid");
    if (views.size() < 2) return out;

    even(views);
    hide(views);
    double whole = mean_all(views[0].light);
    Mat front = views[0].light;
    Alone first_own = alone(views);
    Mat alone_ = first_own.alone;
    auto swap = first_own.swap;
    const std::vector<Mat>& told_ = first_own.told;
    bool doubt = first_own.differ > NOT_ONE;
    out.used = static_cast<int>(views.size()) - 1;
    if (doubt && !anyway) {
        mark("own");
        out.doubt = true;
        return out;
    }
    auto minus = [](float a, float b) { return a - b; };
    auto plus = [](float a, float b) { return a + b; };
    auto towards = [](float a, float b, float by) { return a + (b - a) * by; };
    Mat less = ew(minus, front, alone_);
    double own_ = mean_all(alone_);
    Finer finer_;
    Mat beside;
    if (swap) {
        Mat work = toned(swap->first, less, swap->second);
        beside = outward(work, swap->second, wd * GLARE_FEATHER);
        Mat patch = rim(views, told_, less, swap->second, beside);
        swap = std::make_pair(work, patch);
        finer_ = finer(views, told_, work);
        less = ew(towards, less, work, patch);
        alone_ = ew([](float a, float p) { return a * (1 - p); }, alone_, patch);
        front = ew(towards, front, work, patch);
    }
    mark("own");
    views[0] = View();
    views[0].light = less;
    auto [layer, held] = reflection(views);
    layer = ew(minus, layer, kept(layer, held));
    Mat soft = ew([](float v) { return std::max(v, 0.f); }, resize(layer, wd, ht, cv::INTER_CUBIC));
    double removed = (own_ + mean_all(soft)) / std::max(whole, 1e-6);
    doubt = doubt || removed > MOST;
    out.doubt = doubt;
    mark("layer");
    if (removed < LEAST || (removed > MOST && !anyway)) return out;
    M33 to_photo = larger(1 / scale, 1 / scale) * inv(to_work) *
                   larger(static_cast<double>(wd) / soft.cols, static_cast<double>(ht) / soft.rows);
    std::vector<View> others(views.begin() + 1, views.end());
    Grain on = grain(less, alone_, soft, others, swap ? &swap->second : nullptr);
    Mat now = ew([](float f, float v, float lo, float sh) { return f - v - std::max(f - lo, 0.f) * sh; }, front,
                 on.veil, on.low, on.share);
    auto [mend_, theirs] = mend(now, front, alone_, soft, views, told_);
    auto [veiled_, pressed] = veiled(ew(minus, now, mend_), soft, views, on.share);
    mend_ = ew(plus, mend_, veiled_);
    theirs = ew([](float a, float b) { return std::max(a, b); }, theirs, pressed);
    if (!finer_ && any(theirs)) finer_ = finer(views, told_, from_sides(views, told_, 0.0).first);
    if (swap) mend_ = ew(plus, mend_, level(ew(minus, now, mend_), swap->first, swap->second, beside));
    // Around the corners no more goes than at them.
    on.veil = around(on.veil), on.share = around(on.share);
    mend_ = around(mend_), theirs = around(theirs);
    if (swap) swap->second = around(swap->second);
    mark("mended");
    out.image = subtract(first, on, mend_, swap, to_photo, quad, finer_, &theirs);
    out.removed = round4(removed);
    mark("whole");
    return out;
}

}  // namespace frame::scan
