// What the first view alone shows, and the work under a lamp: `_alone`,
// `_told`, `_own`, `_one`, `_tellings`, `_from_sides`, `_toned`, `_level`,
// `_rim`, `_outward` of `imaging/reflections.py`.
#include "scan_detail.hpp"

#include <opencv2/geometry.hpp>

namespace frame::scan {

using namespace np;

/// `_beside`: each step with those beside it, half as much for each step
/// away.
static std::vector<Mat> beside_(const std::vector<Mat>& steps) {
    size_t n = steps.size();
    std::vector<Mat> up = steps, down = steps, out;
    for (size_t k = 1; k < n; k++) up[k] = ew([](float s, float u) { return s + u / 2; }, steps[k], up[k - 1]);
    for (size_t k = n - 1; k-- > 0;)
        down[k] = ew([](float s, float d) { return s + d / 2; }, steps[k], down[k + 1]);
    for (size_t k = 0; k < n; k++)
        out.push_back(ew([](float a, float b, float c) { return a + b - c; }, up[k], down[k], steps[k]));
    return out;
}

Mat told(const Mat& side, const Mat& apart_, const Mat& counts_, const Mat& first) {
    int size = pyround(side.cols * ALONE_ABOUT) | 1;
    auto about_ = [size](const Mat& a) {
        Mat out;
        cv::boxFilter(a, out, -1, cv::Size(size, size), cv::Point(-1, -1), true, cv::BORDER_REFLECT);
        return out;
    };
    // How light, colour by colour: in steps of a factor, each place
    // between two of them.
    const float low = static_cast<float>(std::log(0.01));
    const float span = static_cast<float>(std::log(1.01) - std::log(0.01));
    const float last = static_cast<float>(ALONE_STEPS - 1);
    Mat step = ew([=](float s) { return (std::log(s + 0.01f) - low) / span * last; }, side);
    std::vector<Mat> part;
    for (int k = 0; k < ALONE_STEPS; k++)
        part.push_back(ew([k](float s) { return clipf(1 - std::abs(s - static_cast<float>(k)), 0.f, 1.f); }, step));
    // A pixel burnt out in either (in any colour) says nothing of what
    // they differ by.
    const float blown = static_cast<float>(BLOWN);
    Mat seen = ew([blown](float c, float f, float s) { return c * ((f < blown && s < blown) ? 1.f : 0.f); }, counts_,
                  max3(first), max3(side));
    Mat weigh = seen;
    Mat tells = zeros(apart_);
    const float few = static_cast<float>(ALONE_FEW);
    const float off0 = static_cast<float>(ALONE_OFF), off_of = static_cast<float>(ALONE_OFF_OF);
    for (int round = 0; round < ALONE_ROUNDS; round++) {
        // Strict by degrees: the first telling is pulled by all there is.
        float wide = static_cast<float>(std::pow(2.0, ALONE_ROUNDS - 1 - round));
        std::vector<Mat> totals(part.size()), somes(part.size());
        for (size_t k = 0; k < part.size(); k++) {
            totals[k] = about_(ew([](float o, float w, float a) { return o * w * a; }, part[k], weigh, apart_));
            somes[k] = about_(ew([](float o, float w) { return o * w; }, part[k], weigh));
        }
        std::vector<Mat> near = beside_(totals), near_some = beside_(somes);
        tells = zeros(apart_);
        for (size_t k = 0; k < part.size(); k++)
            tells = ew(
                [few](float t, float o, float total, float n, float some, float ns) {
                    return t + o * (total + few * n) / std::max(some + few * ns, 1e-6f);
                },
                tells, part[k], totals[k], near[k], somes[k], near_some[k]);
        // A place is off by its colour that is off the most.
        Mat off_ = max3(ew(
            [=](float a, float t, float f) { return std::abs(a - t) / ((off0 + off_of * f) * wide); }, apart_, tells,
            first));
        weigh = ew(
            [](float s, float o) {
                float v = 1 + o * o;
                return s / (v * v);
            },
            seen, off_);
    }
    return tells;
}

Mat own(const Mat& first, const Mat& side, const Mat& tells, const Mat& counts_) {
    Mat apart_ = median5(ew([](float f, float s, float t) { return f - s - t; }, first, side, tells));
    Mat grey = blur(mean3(side), 1.0);
    Mat five = square(5);
    const float plain = static_cast<float>(ALONE_PLAIN), plain_of = static_cast<float>(ALONE_PLAIN_OF);
    Mat weigh = ew(
        [=](float c, float d, float e, float g) {
            float rough = (d - e) / (plain + plain_of * g);
            float v = 1 + rough * rough;
            return c / (v * v);
        },
        counts_, dilate(grey, five), erode(grey, five), grey);
    Mat out = zeros(apart_);
    Mat left = ones(weigh.rows, weigh.cols);
    Mat weighed = ew([](float a, float w) { return a * w; }, apart_, weigh);
    const float sure_of = static_cast<float>(ALONE_SURE);
    for (size_t last = 0; last < ALONE_REACH.size(); last++) {
        double sigma = ALONE_REACH[last] * first.cols;
        Mat some = blur(weigh, sigma);
        Mat said = ew([](float t, float s) { return t / std::max(s, 1e-6f); }, blur(weighed, sigma), some);
        Mat sure = last == ALONE_REACH.size() - 1
                       ? left
                       : ew([sure_of](float l, float s) { return l * clipf(s / sure_of, 0.f, 1.f); }, left, some);
        out = ew([](float o, float t, float s) { return o + t * s; }, out, said, sure);
        left = ew([](float l, float s) { return l - s; }, left, sure);
    }
    return ew([](float o, float c) { return o * c; }, out, counts_);
}

std::pair<Mat, Mat> one(const std::vector<Mat>& says, const std::vector<Mat>& plains, const Mat& counts_) {
    double near = std::max(1.0, says[0].cols * GLARE_NEAR / 2);
    Mat l0 = blur(sum3(says[0]), near), l1 = blur(sum3(says[1]), near);
    Mat gap = ew([](float a, float b) { return std::abs(a - b); }, l0, l1);
    const float dark = static_cast<float>(GLARE_DARK);
    Mat only = ew([dark](float g, float a, float b) { return ramp(g / (std::min(a, b) + dark), ALONE_ONE[0], ALONE_ONE[1]); },
                  gap, l0, l1);
    Mat second = ew([](float a, float b) { return b < a ? 1.f : 0.f; }, l0, l1);
    Mat lighter = ew([](float p0, float p1, float s) { return p0 + (p1 - p0) * (1 - s); }, plains[0], plains[1], second);
    Mat off_ = sum3(ew([](float v) { return std::abs(v); }, blur(lighter, near)));
    Mat three = ew([](float o, float g) { return ramp(o / (g + 1e-3f), ALONE_THREE[0], ALONE_THREE[1]); },
                   blur(off_, near), gap);
    return {ew([](float o, float t, float c) { return o * t * c; }, only, three, counts_), second};
}

std::vector<std::pair<Mat, Mat>> tellings(const std::vector<View>& views, const std::vector<Mat>& told_,
                                          double black) {
    int ht = views[0].light.rows, wd = views[0].light.cols;
    int near = odd(3, wd * GLARE_NEAR);
    std::vector<Mat> hidden = counts(views, ht, wd);
    std::vector<std::pair<Mat, Mat>> out;
    const float least = static_cast<float>(black);
    for (size_t n = 1; n < views.size(); n++) {
        Mat tells = ew([least](float l, float d) { return std::max(l + d, l * least); }, views[n].light,
                       resize(told_[n - 1], wd, ht, cv::INTER_LINEAR));
        Mat light = ew([](float l, float h) { return h > 0 ? l : INF; }, blur(sum3(tells), near / 2.0), hidden[n]);
        out.emplace_back(tells, light);
    }
    return out;
}

/// As much of a side view as it tells of the work there: mostly the one
/// that is the darker about a place.
Mat counts_for(const Mat& light, const Mat& least) {
    return ew(
        [](float l, float m) {
            if (!std::isfinite(l)) return 0.f;
            return std::exp(-(l - m) / (0.1f * (std::abs(m) + 0.05f)));
        },
        light, least);
}

Mat least_of(const std::vector<std::pair<Mat, Mat>>& tellings_) {
    Mat least = tellings_[0].second.clone();
    for (size_t n = 1; n < tellings_.size(); n++) cv::min(least, tellings_[n].second, least);
    return least;
}

std::pair<Mat, Mat> from_sides(const std::vector<View>& views, const std::vector<Mat>& told_, double black) {
    auto tellings_ = tellings(views, told_, black);
    Mat least = least_of(tellings_);
    Mat work = zeros(views[0].light);
    Mat share = zeros(work.rows, work.cols);
    for (const auto& [tells, light] : tellings_) {
        Mat by = counts_for(light, least);
        work = ew([](float w, float t, float c) { return w + t * c; }, work, tells, by);
        share = ew([](float s, float c) { return s + c; }, share, by);
    }
    work = ew([](float w, float s) { return w / std::max(s, 1e-6f); }, work, share);
    return {work, ew([](float s) { return s > 0 ? 1.f : 0.f; }, share)};
}

Alone alone(const std::vector<View>& views) {
    int ht = views[0].light.rows, wd = views[0].light.cols;
    int w = std::min(ALONE_WIDTH, wd);
    int h = std::max(16, pyround(static_cast<double>(ht) * w / wd));
    Mat first = coarse(views[0].light, h, w);
    std::vector<Mat> counts_ = counts(views, h, w);
    std::vector<Mat> told_, says, lights, owns, plains;
    // What is the first view's own is drawn finer than it is told.
    int wf = std::min(ALONE_FINE, wd);
    int hf = std::max(16, pyround(static_cast<double>(ht) * wf / wd));
    Mat fine_ = coarse(views[0].light, hf, wf);
    std::vector<Mat> counts_fine = counts(views, hf, wf);
    std::vector<Mat> counts_full = counts(views, ht, wd);
    Mat most;
    for (size_t n = 1; n < views.size(); n++) {
        const View& view = views[n];
        // The middle of five each way: the shine of a gold letter and what
        // the laying over missed are narrower than any reflection.
        Mat side = median5(coarse(view.light, h, w));
        Mat apart_ = median5(ew([](float f, float s) { return f - s; }, first, side));
        Mat tells = told(side, apart_, counts_[n], first);
        plains.push_back(ew([](float a, float t, float c) { return (a - t) * c; }, apart_, tells, counts_[n]));
        Mat seen = ew([](float f, float l, float t, float c) { return c > 0 ? f - (l + t) : -INF; }, views[0].light,
                      view.light, resize(tells, wd, ht, cv::INTER_LINEAR), counts_full[n]);
        if (most.empty())
            most = seen;
        else
            cv::max(most, seen, most);
        owns.push_back(
            own(fine_, coarse(view.light, hf, wf), resize(tells, wf, hf, cv::INTER_LINEAR), counts_fine[n]));
        told_.push_back(tells);
        says.push_back(ew([](float s, float t, float c) { return std::max(s + t, 0.f) * c; }, side, tells, counts_[n]));
        lights.push_back(side);
    }
    const float blown_at = static_cast<float>(BLOWN);
    auto burnt_out = [blown_at](const Mat& light) {
        return ew([blown_at](float v) { return v >= blown_at ? 1.f : 0.f; }, max3(light));
    };

    // Only what every side view says; but about where the first view (its
    // `light`) is burnt out those that do show the place say it.
    auto said = [&](const std::vector<Mat>& parts, const std::vector<Mat>& count, const Mat& light) {
        int near = odd(3, light.cols * GLARE_NEAR);
        int wide = odd(3, light.cols * ALONE_SHADE);
        Mat blown = opened(burnt_out(light), square(near));
        blown = blur(dilate(blown, ellipse(wide)), wide / 4.0);
        Mat most_ = parts[0].clone();
        for (size_t n = 1; n < parts.size(); n++) cv::max(most_, parts[n], most_);
        Mat least;
        for (size_t n = 0; n < parts.size(); n++) {
            Mat part = ew([](float p, float m, float c, float b) { return p + (m - p) * ((1 - c) * b); }, parts[n],
                          most_, count[n + 1], blown);
            if (least.empty())
                least = part;
            else
                cv::min(least, part, least);
        }
        return least;
    };

    Mat alone_ = said(owns, counts_fine, fine_);
    Mat glare = said(plains, counts_, first);
    if (says.size() == 2) {
        // Unless one of the two has a reflection of its own there.
        auto [only, second] = one(says, plains, ew([](float a, float b) { return std::min(a, b); }, counts_[1], counts_[2]));

        // What the darker one says over what both say, less what is narrow
        // where the first view (its `light`) shows anything.
        auto more = [&](const std::vector<Mat>& of, const Mat& least, const Mat& only_, const Mat& second_,
                        const Mat& light) {
            Mat over = ew([](float a, float b, float s, float l) { return std::max(a + (b - a) * s - l, 0.f); }, of[0],
                          of[1], second_, least);
            int wide = odd(3, least.cols * ALONE_SHADE);
            Mat about_ = ellipse(wide);
            int near = odd(3, least.cols * GLARE_NEAR);
            Mat blown = opened(burnt_out(light), about_);
            Mat burnt = blur(dilate(blown, square(near)), near / 2.0);
            Mat broad = opened(over, about_);
            return ew([](float br, float o, float bu, float on) { return (br + (o - br) * bu) * on; }, broad, over,
                      burnt, only_);
        };

        glare = ew([](float g, float m) { return g + m; }, glare, more(plains, glare, only, second, first));
        Mat only_fine = resize(only, wf, hf, cv::INTER_LINEAR);
        Mat second_fine = resize(second, wf, hf, cv::INTER_LINEAR);
        alone_ = ew([](float a, float m) { return a + m; }, alone_, more(owns, alone_, only_fine, second_fine, fine_));
    }
    if (views.size() < 3) {
        // One side view has reflections of its own, and nothing to say
        // which of the two a difference is.
        alone_ = zeros(alone_);
        glare = zeros(glare);
    }
    // How far the side views are from telling one work (of what they tell).
    Mat differ = zeros(h, w);
    double whole = 0.0;
    const float dark = static_cast<float>(GLARE_DARK);
    if (says.size() > 1) {
        differ = ew([dark](float d, float s) { return d / (s / 2 + dark); },
                    sum3(ew([](float a, float b) { return std::abs(a - b); }, says[0], says[1])),
                    sum3(ew([](float a, float b) { return a + b; }, says[0], says[1])));
        Mat by = ew([dark](float d, float s) { return d / (s / 2 + dark); },
                    sum3(ew([](float a, float b) { return b - a; }, lights[0], lights[1])),
                    sum3(ew([](float a, float b) { return a + b; }, lights[0], lights[1])));
        std::vector<float> where, more_, less_;
        for (int y = 0; y < h; y++) {
            const float* c1 = counts_[1].ptr<float>(y);
            const float* c2 = counts_[2].ptr<float>(y);
            const float* d = differ.ptr<float>(y);
            const float* b = by.ptr<float>(y);
            for (int x = 0; x < w; x++)
                if (c1[x] == 1 && c2[x] == 1) {
                    where.push_back(d[x]);
                    more_.push_back(std::max(b[x], 0.f));
                    less_.push_back(std::max(-b[x], 0.f));
                }
        }
        if (!where.empty()) {
            whole = static_cast<double>(median(where));
            // A reflection only adds light: with the room in the glass all
            // over one side view, that one is the lighter of the two
            // everywhere and the work is what the other shows.
            double each = std::min(mean_of(more_), mean_of(less_));
            if (each <= NOT_ONE_EACH) whole = 0.0;
        }
    }
    const float from = static_cast<float>(ALONE_FROM), from_of = static_cast<float>(ALONE_FROM_OF);
    const float most_of = static_cast<float>(ALONE_MOST);
    alone_ = ew([=](float a, float f) { return std::min(std::max(a - (from + from_of * f), 0.f), f * most_of); },
                alone_, fine_);
    // A pixel or two by itself is grain.
    int few = odd(3, wf * ALONE_GRAIN);
    alone_ = blur(opened(alone_, square(few)), 0.7);
    Mat out = ew([](float v) { return std::max(v, 0.f); }, resize(alone_, wd, ht, cv::INTER_CUBIC));
    // Drawn from the plain places about, it is no more on a place than the
    // place itself has over what some side view tells there.
    most = blur(ew([](float v) { return std::isfinite(v) ? v : 0.f; }, most), 1.0);
    out = ew([](float o, float m, float l) { return std::min(std::max(std::min(o, m), 0.f), l); }, out, most,
             views[0].light);

    // A lamp is light of every colour, and no narrow thing.
    const float glare_at = static_cast<float>(GLARE), colour_at = static_cast<float>(GLARE * GLARE_COLOUR);
    Mat lamp = ew([=](float most_, float least_) { return (most_ >= glare_at && least_ >= colour_at) ? 1.f : 0.f; },
                  max3(glare), min3(glare));
    int near = odd(3, w * GLARE_NEAR);
    Mat burnt = opened(lamp, square(near));
    // And only where the side views tell one work under it.
    Mat is = burnt > 0, which;
    int some = cv::connectedComponents(is, which);
    for (int each = 1; each < some; each++) {
        std::vector<float> there;
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++)
                if (which.at<int>(y, x) == each) there.push_back(differ.at<float>(y, x));
        if (static_cast<double>(median(there)) > GLARE_DIFFER) burnt.setTo(0, which == each);
    }
    Alone result;
    result.alone = out;
    result.differ = whole;
    result.told = told_;
    if (!any(burnt)) return result;
    Mat patch = blur(dilate(burnt, square(near)), near / 3.0);
    patch = ew([](float v) { return clipf(v, 0.f, 1.f); }, resize(patch, wd, ht, cv::INTER_LINEAR));
    // The work as the side views tell it there. Where no side view shows
    // the place (the frame's side) nothing is put in.
    auto [work, shown_] = from_sides(views, told_, GLARE_BLACK);
    result.swap = std::make_pair(work, ew([](float p, float s) { return p * s; }, patch, shown_));
    return result;
}

Mat toned(const Mat& work, const Mat& to, const Mat& patch) {
    int ht = work.rows, wd = work.cols;
    double fine_ = std::max(1.0, GLARE_LINES * wd);
    // Not the patch, nor right beside it.
    int by = odd(3, wd * GLARE_NEAR);
    Mat free = ew(
        [](float v) {
            float f = 1 - v;
            return f * f;
        },
        dilate(patch, square(by)));

    // Less the grain, which the first view has more of.
    auto lines = [fine_](const Mat& of) {
        Mat grey = dot3(of, LUMA);
        return ew([](float a, float b) { return a - b; }, blur(grey, 1.0), blur(grey, fine_));
    };
    int w = std::max(64, wd / 4);
    int h = std::max(64, pyround(static_cast<double>(ht) * w / wd));
    auto small = [w, h](const Mat& of) { return resize(of, w, h, cv::INTER_AREA); };
    Mat counts_ = small(free);
    Mat apart_ = small(ew([](float t, float wk, float f) { return (t - wk) * f; }, to, work, free));
    Mat theirs = small(ew([](float l, float f) { return l * l * f; }, lines(work), free));
    Mat mine = small(ew([](float l, float f) { return l * l * f; }, lines(to), free));
    Mat light = zeros(apart_), strong = zeros(counts_), left = ones(h, w);
    const float sure_of = static_cast<float>(MEND_SURE);
    for (size_t last = 0; last < GLARE_ABOUT.size(); last++) {
        double sigma = GLARE_ABOUT[last] * w;
        Mat some = blur(counts_, sigma);
        Mat sure = last == GLARE_ABOUT.size() - 1
                       ? left
                       : ew([sure_of](float l, float s) { return l * clipf(s / sure_of, 0.f, 1.f); }, left, some);
        light = ew([](float l, float a, float s, float su) { return l + a / std::max(s, 1e-6f) * su; }, light,
                   blur(apart_, sigma), some, sure);
        strong = ew([](float st, float m, float t, float su) { return st + std::sqrt(m / std::max(t, 1e-12f)) * su; },
                    strong, blur(mine, sigma), blur(theirs, sigma), sure);
        left = ew([](float l, float s) { return l - s; }, left, sure);
    }
    light = resize(light, wd, ht, cv::INTER_LINEAR);
    const float weak = static_cast<float>(GLARE_STRENGTH[0]), most = static_cast<float>(GLARE_STRENGTH[1]);
    strong = resize(ew([=](float v) { return clipf(v, weak, most); }, strong), wd, ht, cv::INTER_LINEAR);
    Mat plain = blur(work, fine_);
    return ew([](float p, float l, float wk, float s) { return p + l + (wk - p) * s; }, plain, light, work, strong);
}

Mat level(const Mat& now, const Mat& work, const Mat& patch, const Mat& beside) {
    int ht = now.rows, wd = now.cols;
    double reach_ = std::max(2.0, wd * GLARE_FEATHER);
    const float reach_f = static_cast<float>(reach_);
    Mat over = ew(
        [reach_f](float p, float b) {
            float o = clipf(1 - b / reach_f, 0.f, 1.f);
            return std::max(p, o * o * (3 - 2 * o));
        },
        patch, beside);
    Mat outside = patch <= 0.5;
    outside /= 255;
    Mat away;
    cv::distanceTransform(outside, away, cv::DIST_L2, 5);
    Mat free = ew([reach_f](float a, float p) { return (a > reach_f ? 1.f : 0.f) * (1 - p); }, away, patch);
    int w = std::max(64, wd / 4);
    int h = std::max(64, pyround(static_cast<double>(ht) * w / wd));
    auto small = [w, h](const Mat& of) { return resize(of, w, h, cv::INTER_AREA); };
    Mat apart_ = ew([](float n, float wk) { return n - wk; }, now, work);
    Mat counts_ = small(free);
    Mat beside_small = small(ew([](float a, float f) { return a * f; }, apart_, free));
    Mat about_ = zeros(beside_small), left = ones(h, w);
    const float sure_of = static_cast<float>(MEND_SURE);
    for (size_t last = 0; last < GLARE_ABOUT.size(); last++) {
        double sigma = GLARE_ABOUT[last] * w;
        Mat some = blur(counts_, sigma);
        Mat sure = last == GLARE_ABOUT.size() - 1
                       ? left
                       : ew([sure_of](float l, float s) { return l * clipf(s / sure_of, 0.f, 1.f); }, left, some);
        about_ = ew([](float a, float b, float s, float su) { return a + b / std::max(s, 1e-6f) * su; }, about_,
                    blur(beside_small, sigma), some, sure);
        left = ew([](float l, float s) { return l - s; }, left, sure);
    }
    about_ = resize(about_, wd, ht, cv::INTER_LINEAR);
    // Told of the patch and of what is beside it alone: beyond an edge of
    // the work the two are another thing apart.
    double fine_ = std::max(1.0, GLARE_LINES * wd);
    Mat of = ew([](float o) { return o > 0 ? 1.f : 0.f; }, over);
    Mat here = ew([](float h_, float o) { return h_ / std::max(o, 1e-3f); },
                  blur(ew([](float a, float o) { return a * o; }, apart_, of), fine_), blur(of, fine_));
    return ew([](float h_, float a, float o) { return (h_ - a) * o; }, here, about_, over);
}

Mat rim(const std::vector<View>& views, const std::vector<Mat>& told_, const Mat& less, const Mat& patch,
        const Mat& beside) {
    int wd = less.cols;
    int by = std::max(1, pyround(wd * GLARE_RIM));
    Mat zone = dilate(ew([](float p) { return p > 0.5f ? 1.f : 0.f; }, patch), ellipse(2 * by + 1));
    double over = std::max(1.0, wd * GLARE_RIM_OVER);
    Mat more;
    auto tellings_ = tellings(views, told_, GLARE_BLACK);
    const float dark = static_cast<float>(GLARE_DARK);
    for (const auto& [tells, light] : tellings_) {
        Mat lit = blur(mean3(tells), over);
        Mat gap = blur(mean3(ew([](float l, float t) { return l - t; }, less, tells)), over);
        Mat has = ew([dark](float g, float l, float li) { return std::isfinite(li) ? g / (l + dark) : 0.f; }, gap, lit,
                     light);
        if (more.empty())
            more = has;
        else
            cv::min(more, has, more);
    }
    Mat rim_ = blur(ew([](float m, float z) { return ramp(m, GLARE_RIM_MORE[0], GLARE_RIM_MORE[1]) * z; }, more, zone),
                    over / 2);
    // Outward by degrees.
    const float out = static_cast<float>(std::max(1.0, wd * GLARE_OUT));
    Mat least = least_of(tellings_);
    Mat wider = ew(
        [out](float r, float b, float l) {
            float o = clipf(2 - b / out, 0.f, 1.f);
            o = o * o * (3 - 2 * o);
            return std::max(r, o * (std::isfinite(l) ? 1.f : 0.f));
        },
        rim_, beside, least);
    return ew([](float p, float w_) { return std::max(p, w_); }, patch, wider);
}

Mat outward(const Mat& work, const Mat& patch, double far) {
    int ht = patch.rows, wd = patch.cols;
    double by = std::max(1.0, wd * GLARE_OUT / 2);
    Mat soft = blur(work, by);
    const float by_f = static_cast<float>(by);
    const double root = std::sqrt(2 * 3.141592653589793);

    // A step so high, blurred so far, is as steep as this at its middle.
    auto step = [=](const Mat& of) {
        Mat sx, sy;
        cv::Sobel(of, sx, CV_32F, 1, 0);
        cv::Sobel(of, sy, CV_32F, 0, 1);
        return ew([=](float a, float b) { return static_cast<float>(static_cast<double>(std::hypot(a, b) / 8 * by_f) * root); },
                  sx, sy);
    };
    Mat light = mean3(soft);
    const float dark = static_cast<float>(GLARE_DARK), dark3 = static_cast<float>(3 * GLARE_DARK);
    Mat total = sum3(soft);
    Mat edge = ew([dark](float s, float l) { return s > static_cast<float>(GLARE_STEP[0]) * (l + dark) ? 1.f : 0.f; },
                  step(light), light);
    for (int colour = 0; colour < 3; colour++) {
        Mat share = ew([dark3](float s, float t) { return s / (t + dark3); }, channel(soft, colour), total);
        edge = ew([](float e, float s) { return (e > 0 || s > static_cast<float>(GLARE_STEP[1])) ? 1.f : 0.f; }, edge,
                  step(share));
    }
    int near = 2 * std::max(1, pyround(wd * GLARE_OUT)) + 1;
    Mat edge8;
    edge.convertTo(edge8, CV_8U);
    Mat way = 1 - dilate(edge8, ellipse(near));
    // Nor from what of the patch lies at an edge: that stays as it is.
    Mat reached = patch > 0.5;
    reached /= 255;
    cv::min(reached, way, reached);
    Mat away(ht, wd, CV_32F);
    for (int y = 0; y < ht; y++)
        for (int x = 0; x < wd; x++) away.at<float>(y, x) = reached.at<uint8_t>(y, x) > 0 ? 0.f : INF;
    if (cv::countNonZero(reached) == 0) return away;
    // Only about the patch: nothing further is reached.
    std::vector<cv::Point> at;
    cv::findNonZero(reached, at);
    cv::Rect bounds = cv::boundingRect(at);
    int span = static_cast<int>(std::ceil(far)) + 1;
    int top = std::max(0, bounds.y - span), left = std::max(0, bounds.x - span);
    int bottom = std::min(ht, bounds.y + bounds.height - 1 + span + 1);
    int right = std::min(wd, bounds.x + bounds.width - 1 + span + 1);
    cv::Rect box(left, top, right - left, bottom - top);
    reached = reached(box).clone();
    way = way(box).clone();
    Mat within = away(box);
    Mat steps[2] = {cross3(), square(3)};
    for (int n = 1; n < span; n++) {
        Mat grown_;
        cv::min(dilate(reached, steps[n % 2]), way, grown_);
        cv::max(reached, grown_, grown_);
        within.setTo(static_cast<float>(n), grown_ > reached);
        reached = grown_;
    }
    return away;
}

}  // namespace frame::scan
