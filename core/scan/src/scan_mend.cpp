// What is mended once the reflections are off, and the layer as it lies on
// the work's grain: `_finer`, `_mend`, `_reach`, `_line`, `_carried`,
// `_shown`, `_veiled`, `_grain` of `imaging/reflections.py`.
#include "scan_detail.hpp"

#include <memory>

namespace frame::scan {

using namespace np;

namespace {

float mul(float a, float b) { return a * b; }
float add(float a, float b) { return a + b; }
float sub(float a, float b) { return a - b; }
float larger_of(float a, float b) { return std::max(a, b); }
float none_under(float a) { return std::max(a, 0.f); }

/// A side photograph and what of it goes in where the first has nothing.
struct Part {
    Mat photo, across, down, light, share;
    std::array<float, 3> gains;
};

}  // namespace

Finer finer(const std::vector<View>& views, const std::vector<Mat>& told_, const Mat& work) {
    int ht = work.rows, wd = work.cols;
    auto tellings_ = tellings(views, told_, GLARE_BLACK);
    Mat least = least_of(tellings_);
    double wide = std::max(2.0, GLARE_ABOUT[0] * wd);
    int near = odd(3, wd * GLARE_NEAR);

    auto lines = [wide](const Mat& of) {
        Mat grey = dot3(of, LUMA);
        Mat fine_ = ew(
            [](float g, float b) {
                float d = g - b;
                return d * d;
            },
            grey, blur(grey, 2.0));
        return blur(fine_, wide);
    };

    Mat mine = lines(work);
    auto parts = std::make_shared<std::vector<Part>>();
    Mat whole = zeros(ht, wd);
    const float most = static_cast<float>(GLARE_STRENGTH[1]);
    for (size_t n = 1; n < views.size(); n++) {
        const View& view = views[n];
        const Mat& light = tellings_[n - 1].second;
        // As much of each as it tells of the work there (`_from_sides`).
        Mat share = counts_for(light, least);
        whole = ew(add, whole, share);
        if (view.photo.empty() || view.seen.empty()) continue;
        // With the room in the glass over it a view's finest is mostly its
        // grain: the less of it, the less of its light there is the work's.
        Mat own_ = blur(sum3(view.light), near / 2.0);
        share = ew(
            [most](float s, float m, float theirs, float l, float o) {
                float strong = std::sqrt(m / std::max(theirs, 1e-12f));
                s = s * clipf(strong, 0.f, most);
                float clear = clipf(l / std::max(o, 1e-6f), 0.f, 1.f);
                return s * (std::isfinite(l) ? clear * clear : 0.f);
            },
            share, mine, lines(view.light), light, own_);
        Part part;
        part.photo = view.photo;
        part.across = channel(view.seen, 0);
        part.down = channel(view.seen, 1);
        part.light = view.light;
        part.share = share;
        for (int k = 0; k < 3; k++) part.gains[k] = static_cast<float>(view.gains[k]);
        parts->push_back(part);
    }
    for (Part& part : *parts) part.share = ew([](float s, float w) { return s / std::max(w, 1e-6f); }, part.share, whole);

    return [parts](const M33& to_part, const Mat& glare) -> Mat {
        Mat out = zeros(glare.rows, glare.cols, 3);
        int r0 = glare.rows, r1 = 0, c0 = glare.cols, c1 = 0;
        for (int y = 0; y < glare.rows; y++) {
            const float* g = glare.ptr<float>(y);
            for (int x = 0; x < glare.cols; x++)
                if (g[x] > 0) {
                    r0 = std::min(r0, y), r1 = std::max(r1, y + 1);
                    c0 = std::min(c0, x), c1 = std::max(c1, x + 1);
                }
        }
        if (r1 <= r0 || parts->empty()) return out;
        Mat at(r1 - r0, c1 - c0, CV_64FC2);
        for (int y = r0; y < r1; y++) {
            auto* p = at.ptr<cv::Vec2d>(y - r0);
            for (int x = c0; x < c1; x++) p[x - c0] = cv::Vec2d(x, y);
        }
        Mat there;
        cv::perspectiveTransform(at, there, Mat(inv(to_part)));
        Mat u(at.rows, at.cols, CV_32F), v(at.rows, at.cols, CV_32F);
        for (int y = 0; y < at.rows; y++) {
            const auto* p = there.ptr<cv::Vec2d>(y);
            float* pu = u.ptr<float>(y);
            float* pv = v.ptr<float>(y);
            for (int x = 0; x < at.cols; x++) {
                pu[x] = static_cast<float>(p[x][0]);
                pv[x] = static_cast<float>(p[x][1]);
            }
        }
        auto here = [&](const Mat& of, int how) {
            Mat o;
            cv::remap(of, o, u, v, how, cv::BORDER_REPLICATE);
            return o;
        };
        Mat into = out(cv::Rect(c0, r0, c1 - c0, r1 - r0));
        for (const Part& part : *parts) {
            Mat sharp;
            cv::remap(part.photo, sharp, here(part.across, cv::INTER_LINEAR), here(part.down, cv::INTER_LINEAR),
                      cv::INTER_CUBIC, cv::BORDER_REPLICATE);
            Mat more = linear(sharp);
            Mat soft = here(part.light, cv::INTER_CUBIC);
            Mat by = here(part.share, cv::INTER_LINEAR);
            const auto gains = part.gains;
            rows(more.rows, [&](int y) {
                const float* m = more.ptr<float>(y);
                const float* s = soft.ptr<float>(y);
                const float* b = by.ptr<float>(y);
                float* o = into.ptr<float>(y);
                for (int x = 0; x < more.cols; x++)
                    for (int k = 0; k < 3; k++) o[x * 3 + k] += (m[x * 3 + k] / gains[k] - s[x * 3 + k]) * b[x];
            });
        }
        return out;
    };
}

Mat reach(const Mat& of, double grow, double soft) {
    int ht = of.rows, wd = of.cols;
    int less = std::max(1, pyround(grow * wd) / 8);
    Mat tiny = dilate(of, square(less));
    tiny = resize(tiny, wd / less, ht / less, cv::INTER_AREA);
    int by = std::max(1, pyround(grow * wd / less));
    Mat over = blur(dilate(tiny, ellipse(2 * by + 1)), soft * wd / less);
    over = resize(over, wd, ht, cv::INTER_LINEAR);
    return ew([](float o) { return o * o * (3 - 2 * o); }, over);
}

Mat line(const Mat& theirs, const Mat& mine, const Mat& free) {
    int ht = mine.rows, wd = mine.cols;
    int w = std::max(64, wd / 4);
    int h = std::max(64, pyround(static_cast<double>(ht) * w / wd));
    auto small = [w, h](const Mat& of) { return resize(of, w, h, cv::INTER_AREA); };
    Mat counts_ = small(free);
    Mat side = small(theirs), first = small(mine);
    Mat squares = small(ew(mul, theirs, theirs)), both = small(ew(mul, theirs, mine));
    Mat slope = zeros(side), rest = zeros(side), left = ones(h, w);
    const float noise = static_cast<float>(MEND_NOISE * MEND_NOISE);
    const float sure_of = static_cast<float>(MEND_SURE);
    auto over = [](float a, float some) { return a / std::max(some, 1e-6f); };
    for (size_t last = 0; last < MEND_REACH.size(); last++) {
        double sigma = MEND_REACH[last] * w;
        auto about_of = [sigma](const Mat& of) { return blur(of, sigma); };
        Mat some = about_of(counts_);
        Mat middle = ew(over, about_of(ew(mul, side, counts_)), some);
        Mat to = ew(over, about_of(ew(mul, first, counts_)), some);
        Mat spread = ew([](float a, float s, float m) { return a / std::max(s, 1e-6f) - m * m; },
                        about_of(ew(mul, squares, counts_)), some, middle);
        Mat along = ew([](float a, float s, float m, float t) { return a / std::max(s, 1e-6f) - m * t; },
                       about_of(ew(mul, both, counts_)), some, middle, to);
        Mat steep = ew([noise](float al, float sp) { return clipf(al / (sp + noise), 0.3f, 2.0f); }, along, spread);
        Mat sure = last == MEND_REACH.size() - 1
                       ? left
                       : ew([sure_of](float l, float s) { return l * clipf(s / sure_of, 0.f, 1.f); }, left, some);
        slope = ew([](float sl, float st, float su) { return sl + st * su; }, slope, steep, sure);
        rest = ew([](float r, float t, float st, float m, float su) { return r + (t - st * m) * su; }, rest, to, steep,
                  middle, sure);
        left = ew(sub, left, sure);
    }
    double even_ = MEND_REACH[0] * w / 2;
    slope = resize(blur(slope, even_), wd, ht, cv::INTER_LINEAR);
    rest = resize(blur(rest, even_), wd, ht, cv::INTER_LINEAR);
    return ew([](float s, float t, float r) { return s * t + r; }, slope, theirs, rest);
}

Mat carried(const Mat& of, const Mat& sure) {
    int ht = of.rows, wd = of.cols;
    int w = std::max(64, wd / 4);
    int h = std::max(64, pyround(static_cast<double>(ht) * w / wd));
    Mat counts_ = resize(sure, w, h, cv::INTER_AREA);
    Mat have = resize(ew(mul, of, sure), w, h, cv::INTER_AREA);
    Mat far = zeros(have), left = ones(h, w);
    const float sure_of = static_cast<float>(MEND_SURE);
    for (size_t last = 0; last < MEND_REACH.size(); last++) {
        double sigma = MEND_REACH[last] * w;
        Mat some = blur(counts_, sigma);
        Mat about_ = blur(have, sigma);
        Mat by = last == MEND_REACH.size() - 1
                     ? left
                     : ew([sure_of](float l, float s) { return l * clipf(s / sure_of, 0.f, 1.f); }, left, some);
        far = ew([](float f, float a, float s, float b) { return f + a / std::max(s, 1e-6f) * b; }, far, about_, some,
                 by);
        left = ew(sub, left, by);
    }
    far = resize(far, wd, ht, cv::INTER_LINEAR);
    return ew([](float o, float s, float f) { return o * s + f * (1 - s); }, of, sure, far);
}

std::pair<Mat, Mat> shown(const std::vector<View>& views) {
    int ht = views[0].light.rows, wd = views[0].light.cols;
    std::vector<Mat> counts_ = counts(views, ht, wd, true);
    int near = odd(3, wd * GLARE_NEAR);
    std::vector<Mat> lights;
    for (size_t n = 1; n < views.size(); n++) lights.push_back(blur(sum3(views[n].light), near / 2.0));
    Mat least(ht, wd, CV_32F, cv::Scalar(INF));
    for (size_t n = 1; n < views.size(); n++)
        least = ew([](float m, float l, float c) { return c > 0 ? std::min(m, l) : m; }, least, lights[n - 1],
                   counts_[n]);
    least = ew([](float l) { return std::isfinite(l) ? l : 0.f; }, least);
    Mat darker = zeros(views[0].light), total = zeros(ht, wd);
    Mat sure;
    for (size_t n = 1; n < views.size(); n++) {
        Mat weigh = ew([](float l, float m, float c) { return std::exp(-(l - m) / (0.1f * (std::abs(m) + 0.05f))) * c; },
                       lights[n - 1], least, counts_[n]);
        darker = ew([](float d, float l, float w) { return d + l * w; }, darker, views[n].light, weigh);
        total = ew(add, total, weigh);
        if (sure.empty())
            sure = counts_[n].clone();
        else
            cv::min(sure, counts_[n], sure);
    }
    darker = ew([](float d, float t) { return d / std::max(t, 1e-6f); }, darker, total);
    return {darker, sure};
}

std::pair<Mat, Mat> veiled(const Mat& now, const Mat& soft, const std::vector<View>& views, const Mat& sheen) {
    int ht = now.rows, wd = now.cols;
    std::pair<Mat, Mat> none{zeros(now), zeros(ht, wd)};
    if (views.size() < 3) return none;
    auto [sides, sure] = shown(views);
    const float dark = static_cast<float>(MEND_DARK);
    Mat left = blur(mean3(ew(none_under, now)), 2.0);
    Mat strong = blur(max3(soft), 2.0);
    Mat share = ew([dark](float s, float l) { return s / (l + dark); }, strong, left);
    Mat veiled_ = ew([](float s) { return ramp(s, VEILED[0], VEILED[1]); }, share);
    if (!any(veiled_)) return none;
    Mat most_sheen = max3(sheen);
    std::vector<float> under;
    for (int y = 0; y < ht; y++) {
        const float* v = veiled_.ptr<float>(y);
        const float* s = most_sheen.ptr<float>(y);
        for (int x = 0; x < wd; x++)
            if (v[x] > 0) under.push_back(s[x]);
    }
    double paint = mean_of(under);
    if (paint >= VEILED_PAINT[1]) return none;
    const float keep =
        static_cast<float>(1 - std::max(0.0, (paint - VEILED_PAINT[0]) / (VEILED_PAINT[1] - VEILED_PAINT[0])));
    Mat grain_ = blur(most_sheen, VEILED_SHEEN_ABOUT * wd);
    veiled_ = ew(
        [keep](float v, float g, float s) {
            float glass = 1 - ramp(g, VEILED_SHEEN[0], VEILED_SHEEN[1]);
            return (v * keep) * std::max(glass, ramp(s, VEILED_STRONG[0], VEILED_STRONG[1]));
        },
        veiled_, grain_, strong);
    if (!any(veiled_)) return none;
    Mat over = reach(veiled_, VEILED_GROW, VEILED_SOFT);
    Mat free = ew(
        [](float o, float s) {
            float f = 1 - o;
            return f * f * s;
        },
        over, sure);
    // A veil over all of it: nothing says how the two pictures go together.
    if (mean_all(free) < VEILED_FREE) return none;
    Mat theirs = line(sides, now, free);
    double tint = std::max(1.0, MEND_TINT * wd);
    Mat have = blur(sure, tint);
    Mat gap = ew(sub, now, theirs);
    Mat apart_ = blur(ew(mul, gap, sure), tint);
    // The darker side view is the picture as soon as it counts at all.
    Mat known = ew([](float h) { return clipf(h * 4, 0.f, 1.f); }, have);
    apart_ = carried(ew([](float a, float h) { return a / std::max(h, 1e-3f); }, apart_, have), known);
    Mat heavy = ew([](float s, float v) { return std::min(ramp(s, VEILED_HEAVY[0], VEILED_HEAVY[1]), v); }, share,
                   veiled_);
    if (any(heavy)) {
        heavy = ew(mul, reach(heavy, VEILED_HEAVY_GROW, VEILED_HEAVY_GROW), known);
        Mat closer = blur(gap, std::max(1.0, MEND_FINE * wd));
        apart_ = ew([](float a, float c, float h) { return a + (c - a) * h; }, apart_, closer, heavy);
    }
    Mat off_ = ew(mul, apart_, over);
    // No more than most of what a place has, and of its three colours
    // alike: the frame's dark beside the work has no veil on it.
    const float most_of = static_cast<float>(VEILED_MOST);
    Mat by(ht, wd, CV_32F);
    rows(ht, [&](int y) {
        const float* o = off_.ptr<float>(y);
        const float* n = now.ptr<float>(y);
        float* b = by.ptr<float>(y);
        for (int x = 0; x < wd; x++) {
            float least = INF;
            for (int k = 0; k < 3; k++) {
                float off_k = o[x * 3 + k];
                float most = std::max(n[x * 3 + k], 0.f) * most_of;
                least = std::min(least, off_k > most ? most / std::max(off_k, 1e-6f) : 1.f);
            }
            b[x] = least;
        }
    });
    return {ew(mul, off_, by), ew(mul, heavy, over)};
}

std::pair<Mat, Mat> mend(const Mat& now, const Mat& front, const Mat& alone, const Mat& soft,
                         const std::vector<View>& views, const std::vector<Mat>& told_) {
    int ht = now.rows, wd = now.cols;
    std::pair<Mat, Mat> none{zeros(now), zeros(ht, wd)};
    if (views.size() < 3) return none;
    auto [work, shown_] = from_sides(views, told_, 0.0);
    const float dark = static_cast<float>(MEND_DARK);
    Mat base = blur(mean3(ew(none_under, work)), 2.0);
    Mat much = ew([dark](float a, float b) { return a / (b + dark); }, blur(max3(alone), 2.0), base);
    Mat hard = ew([](float m, float s) { return ramp(m, MEND_FROM, MEND_TO) * s; }, much, shown_);
    // The soft layer's edges (his own figure, dark in the glass, with the
    // room's veil about it).
    int by = std::max(1, pyround(MEND_EDGE_ABOUT * wd));
    Mat about_ = ellipse(2 * by + 1);
    Mat most = blur(max3(soft), 1.0);
    Mat edge = ew(
        [dark](float d, float e, float b, float s) {
            return ramp((d - e) / (b + dark), MEND_EDGE[0], MEND_EDGE[1]) * s;
        },
        dilate(most, about_), erode(most, about_), base, shown_);
    if (!any(hard) && !any(edge)) return none;
    double fine_ = std::max(1.0, MEND_FINE * wd);

    // Far about only where the work is plain.
    Mat rough = max3(ew([](float w, float b) { return std::abs(w - b); }, work, blur(work, 2 * fine_)));
    int off_ = std::max(1, pyround(MEND_OFF * wd));
    rough = ew([dark](float r, float b) { return 1 - ramp(r / (b + dark), MEND_PLAIN[0], MEND_PLAIN[1]); },
               dilate(rough, square(2 * off_ + 1)), base);
    Mat plain = blur(rough, off_);
    Mat far = ew(larger_of, reach(hard, MEND_FAR, MEND_FAR_SOFT), reach(edge, MEND_GROW, MEND_SOFT));
    Mat mask = ew([](float r, float f, float p, float s) { return std::max(r, f * p) * s; },
                  reach(hard, MEND_GROW, MEND_SOFT), far, plain, shown_);

    // The line the two pictures keep to, where nothing is mended.
    Mat free = ew(
        [](float m, float s) {
            float f = 1 - m;
            return f * f * s;
        },
        mask, shown_);
    int w = std::max(64, wd / 4);
    int h = std::max(64, pyround(static_cast<double>(ht) * w / wd));
    work = line(work, now, free);

    // Nor is what is wider than they can tell it theirs.
    Mat apart_ = blur(ew(sub, now, work), fine_);
    Mat coarse_ = blur(resize(apart_, w, h, cv::INTER_AREA), MEND_COARSE * w);
    apart_ = ew(sub, apart_, resize(coarse_, wd, ht, cv::INTER_LINEAR));
    // About letters and lines the colour of a place is theirs only as it
    // is over the letters and the dark between them together.
    Mat tint = ew(sub, apart_, dot3(apart_, LUMA));
    Mat wider = blur(tint, MEND_TINT * wd);
    apart_ = ew([](float a, float t, float wide, float p) { return a - (t - wide) * (1 - p); }, apart_, tint, wider,
                plain);
    Mat detail = ew(sub, now, blur(now, fine_));
    // Under a bright reflection the first view's lines are pale: the side
    // views'.
    Mat light = blur(max3(front), 2.0);
    Mat pressed = ew(
        [](float m, float l, float s) {
            return ramp(m, MEND_ALL[0], MEND_ALL[1]) * ramp(l, MEND_ALL_LIGHT[0], MEND_ALL_LIGHT[1]) * s;
        },
        much, light, shown_);
    pressed = reach(pressed, MEND_GROW, MEND_SOFT);
    // And along a sharp edge of what is taken off.
    Mat taken = blur(max3(ew(add, alone, soft)), 1.0);
    by = std::max(2, pyround(MEND_SHARP_ABOUT * wd));
    about_ = ellipse(2 * by + 1);
    Mat sharp = ew(
        [dark](float d, float e, float b, float s) {
            return ramp((d - e) / (b + dark), MEND_SHARP[0], MEND_SHARP[1]) * s;
        },
        dilate(taken, about_), erode(taken, about_), base, shown_);
    sharp = blur(dilate(sharp, about_), by / 2.0);
    pressed = ew(larger_of, pressed, sharp);
    Mat stays = ew([](float d, float p) { return d * (1 - p); }, dot3(detail, LUMA), pressed);
    stays = ew([](float s, float wk, float b, float p) { return s + (wk - b) * p; }, stays, work, blur(work, fine_),
               pressed);
    Mat mend_ = ew([](float a, float d, float s, float m) { return (a + d - s) * m; }, apart_, detail, stays, mask);
    return {mend_, ew(mul, pressed, mask)};
}

Grain grain(const Mat& less_, const Mat& alone_, const Mat& soft_, const std::vector<View>& sides,
            const Mat* lamp) {
    int ht = less_.rows, wd = less_.cols;
    int near = odd(3, wd * GRAIN_ABOUT);
    Mat about_ = ellipse(2 * near + 1);

    // Not a pixel of grain: of what is a pixel and a half wide.
    auto darkest = [&](const Mat& calm) { return erode(calm, about_); };
    auto rough = [&](const Mat& of) {
        Mat calm = blur(of, 1.0);
        return blur(ew(sub, dilate(calm, about_), darkest(calm)), near);
    };

    Mat mine = rough(ew(add, less_, alone_));
    std::vector<View> all(1);
    all[0].light = less_;
    all.insert(all.end(), sides.begin(), sides.end());
    std::vector<Mat> counts_ = counts(all, ht, wd);
    Mat theirs(ht, wd, CV_32FC3, cv::Scalar::all(INF));
    for (size_t n = 1; n < all.size(); n++)
        theirs = ew([](float t, float r, float c) { return c > 0 ? std::min(t, r) : t; }, theirs, rough(all[n].light),
                    counts_[n]);
    Mat rougher = ew(
        [](float t, float m) {
            float r = clipf(1 - t / std::max(m, 1e-4f), 0.f, 1.f);
            float sure = ramp(r, GRAIN_FROM, GRAIN_SURE);
            return r * sure * sure * (3 - 2 * sure);
        },
        theirs, mine);
    if (lamp) {
        // A lamp is one piece and wider than the grain; the glints on the
        // ridges of paint are taken out the same way and are the grain.
        Mat by = opened(ew([](float l) { return l > 0.5f ? 1.f : 0.f; }, *lamp), about_);
        by = dilate(by, about_, 3);
        rougher = ew([](float r, float b) { return r * (1 - clipf(b, 0.f, 1.f)); }, rougher, blur(by, near));
    }

    // Where the first view is the rougher one, what is its own is a sheen
    // on the grain as well and goes as the layer does.
    Mat grain_ = max3(rougher);
    auto with = [](float a, float b, float g) { return a + b * g; };
    Mat soft = ew(with, soft_, alone_, grain_);
    Mat less = ew(with, less_, alone_, grain_);
    Mat alone = ew([](float a, float g) { return a * (1 - g); }, alone_, grain_);
    Mat low = darkest(blur(less, 1.0));
    low = ew([](float a, float b) { return std::min(a, b); }, low, blur(low, near / 2.0));
    Mat over = blur(ew([](float l, float lo) { return std::max(l - lo, 0.f); }, less, low), near);
    Mat sheen = ew([](float s, float r, float o) { return std::min(s, r * o); }, soft, rougher, over);
    // The rest is a veil, and no more of one than the darkest about has.
    Grain out;
    out.veil = ew([](float a, float s, float sh, float lo) { return a + std::min(s - sh, std::max(lo, 0.f)); }, alone,
                  soft, sheen, low);
    out.share = ew([](float sh, float o) { return clipf(sh / std::max(o, 1e-4f), 0.f, 1.f); }, sheen, over);
    out.low = ew(add, low, alone);
    return out;
}

}  // namespace frame::scan
