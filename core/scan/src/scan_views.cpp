// The views made even and the layer they share: `_even`, `_hide`,
// `_counts`, `_reflection`, `_shared`, `_kept` of `imaging/reflections.py`.
#include "scan_detail.hpp"

namespace frame::scan {

using namespace np;

Mat coarse(const Mat& light, int h, int w) { return resize(light, w, h, cv::INTER_AREA); }

Mat apart(const Mat& apart_, int h, int w) {
    Mat fine_ = resize(apart_, w * CELL, h * CELL, cv::INTER_AREA);
    Mat middle(h, w, CV_32FC3);
    rows(h, [&](int y) {
        std::vector<float> cell(CELL * CELL);
        float* o = middle.ptr<float>(y);
        for (int x = 0; x < w; x++)
            for (int c = 0; c < 3; c++) {
                for (int i = 0; i < CELL; i++) {
                    const float* p = fine_.ptr<float>(y * CELL + i);
                    for (int j = 0; j < CELL; j++) cell[i * CELL + j] = p[(x * CELL + j) * 3 + c];
                }
                o[x * 3 + c] = median(cell);
            }
    });
    return median5(middle);
}

std::vector<Mat> counts(const std::vector<View>& views, int h, int w, bool tone) {
    std::vector<Mat> out;
    for (const View& view : views) {
        Mat each = ones(h, w);
        if (view.side != 0) {
            int band = std::max(1, pyround(w * (tone ? view.shows : view.hidden)));
            int ease = std::max(1, pyround(w * (tone ? HIDDEN_SHOWN : HIDDEN_EASE)));
            std::vector<float> along(w);
            for (int x = 0; x < w; x++)
                along[x] = clipf((static_cast<float>(x) - static_cast<float>(band - 1)) / static_cast<float>(ease),
                                 0.f, 1.f);
            for (int y = 0; y < h; y++) {
                float* o = each.ptr<float>(y);
                for (int x = 0; x < w; x++) o[x] = view.side < 0 ? along[x] : along[w - 1 - x];
            }
        }
        out.push_back(each);
    }
    return out;
}

void hide(std::vector<View>& views) {
    Mat first = mean3(views[0].light);
    int ht = first.rows, wd = first.cols;
    int reach_ = pyround(wd * HIDDEN_MOST);

    std::vector<Mat> drawn;
    for (const View& view : views) {
        Mat grey = blur(per_pixel(view.light,
                                  [](const float* p) { return std::sqrt(std::max((p[0] + p[1] + p[2]) / 3.0f, 0.f)); }),
                        1.5);
        drawn.push_back(grey - blur(grey, 0.006 * wd));
    }
    int strip = std::max(4, pyround(wd * 0.01));
    // A column counted from the edge the view was taken from.
    auto col = [wd](int side, int x) { return side > 0 ? wd - 1 - x : x; };
    for (size_t n = 1; n < views.size(); n++) {
        View& view = views[n];
        if (view.side == 0) continue;
        // Its lines along its edge beside the other views' there.
        int unlike = 0;
        for (int k = 1; k < std::max(2, pyround(HIDDEN / 0.01)); k++) {
            float like = -INF;
            for (size_t m = 0; m < views.size(); m++) {
                if (m == n) continue;
                float ab = 0, aa = 0, bb = 0;
                for (int y = 0; y < ht; y++) {
                    const float* a = drawn[n].ptr<float>(y);
                    const float* b = drawn[m].ptr<float>(y);
                    for (int x = k * strip; x < std::min((k + 1) * strip, wd); x++) {
                        float av = a[col(view.side, x)], bv = b[col(view.side, x)];
                        ab += av * bv;
                        aa += av * av;
                        bb += bv * bv;
                    }
                }
                float as = ab / static_cast<float>(std::sqrt(static_cast<double>(aa * bb)) + 1e-9);
                like = std::max(like, as);
            }
            if (like < static_cast<float>(HIDDEN_LIKE)) unlike = k;
        }
        bool shown_ = unlike == 0;
        double least = shown_ ? HIDDEN_SHOWN : HIDDEN;
        Mat mine = mean3(view.light);
        // Column by column from the edge: the side view's middle light
        // beside the first's.
        int cols = std::min(reach_, wd);
        std::vector<char> dark(cols);
        std::vector<float> a(ht), b(ht);
        for (int x = 0; x < cols; x++) {
            int at = col(view.side, x);
            for (int y = 0; y < ht; y++) {
                a[y] = mine.ptr<float>(y)[at];
                b[y] = first.ptr<float>(y)[at];
            }
            dark[x] = median(a) < static_cast<float>(HIDDEN_DARK) * median(b);
        }
        // Only the dark that begins in the band there always is: further
        // in it is the work's own (an oil's sheen in the first view).
        int last = pyround(wd * HIDDEN);
        bool any_ = false;
        for (int x = 0; x <= last && x < cols; x++) any_ = any_ || dark[x];
        if (!any_) last = 0;
        while (0 < last && last < reach_ && last < cols && dark[last]) last++;
        view.hidden = std::max(least, std::min(HIDDEN_MOST, static_cast<double>(last) / wd + HIDDEN_BESIDE));
        view.shows = std::min(
            view.hidden, std::max({HIDDEN_SHOWN, (unlike + 1.5) * 0.01, static_cast<double>(last) / wd}));
    }
}

void even(std::vector<View>& views) {
    int h = std::max(8, pyround(static_cast<double>(views[0].light.rows) * EVEN_WIDTH / views[0].light.cols));
    int w = EVEN_WIDTH;

    // The steps across and down, each colour's by itself: across first.
    auto steps = [&](const Mat& light) {
        Mat soft = blur(coarse(light, h, w), 1.5);
        std::array<std::vector<float>, 3> out;
        for (int c = 0; c < 3; c++) {
            out[c].reserve(static_cast<size_t>(h) * (w - 1) + static_cast<size_t>(h - 1) * w);
            for (int y = 0; y < h; y++) {
                const float* p = soft.ptr<float>(y);
                for (int x = 0; x + 1 < w; x++) out[c].push_back(p[(x + 1) * 3 + c] - p[x * 3 + c]);
            }
            for (int y = 0; y + 1 < h; y++) {
                const float* p = soft.ptr<float>(y);
                const float* q = soft.ptr<float>(y + 1);
                for (int x = 0; x < w; x++) out[c].push_back(q[x * 3 + c] - p[x * 3 + c]);
            }
        }
        return out;
    };

    auto first = steps(views[0].light);
    for (size_t n = 1; n < views.size(); n++) {
        View& view = views[n];
        auto side = steps(view.light);
        std::array<double, 3> gains{};
        for (int c = 0; c < 3; c++) {
            const std::vector<float>& a = first[c];
            const std::vector<float>& b = side[c];
            std::vector<float> abs_a(a.size()), abs_b(b.size());
            for (size_t i = 0; i < a.size(); i++) {
                abs_a[i] = std::abs(a[i]);
                abs_b[i] = std::abs(b[i]);
            }
            std::vector<float> order = abs_a;
            float strong_a = quantile(order, 1 - EVEN_STRONG);
            order = abs_b;
            float strong_b = quantile(order, 1 - EVEN_STRONG);
            std::vector<float> ratios;
            for (size_t i = 0; i < a.size(); i++)
                if (abs_a[i] >= strong_a && abs_b[i] >= strong_b && a[i] * b[i] > 0) ratios.push_back(b[i] / a[i]);
            if (static_cast<int>(ratios.size()) < EVEN_FEW) {
                order = abs_a;
                float strongest = quantile(order, 0.9);
                ratios.clear();
                for (size_t i = 0; i < a.size(); i++)
                    if (abs_a[i] >= strongest) ratios.push_back(b[i] / a[i]);
            }
            gains[c] = static_cast<double>(clipf(median(ratios), 0.5f, 2.0f));
        }
        // The exposure is one for the three channels; the white balance
        // moves between two photographs of one wall only so far.
        std::array<double, 3> sorted = gains;
        std::sort(sorted.begin(), sorted.end());
        double middle = sorted[1];
        for (double& g : gains) g = std::min(std::max(g, middle * (1 - BALANCE)), middle * (1 + BALANCE));
        float by[3] = {static_cast<float>(gains[0]), static_cast<float>(gains[1]), static_cast<float>(gains[2])};
        rows(view.light.rows, [&](int y) {
            float* p = view.light.ptr<float>(y);
            for (int x = 0; x < view.light.cols; x++)
                for (int c = 0; c < 3; c++) p[x * 3 + c] /= by[c];
        });
        view.gains = gains;
    }
}

std::pair<Mat, Mat> reflection(const std::vector<View>& views) {
    int ht = views[0].light.rows, wd = views[0].light.cols;
    size_t n = views.size();
    Mat common, low;
    std::vector<Mat> lights;
    // What each side view differs from the first by, once.
    std::vector<Mat> differs;
    for (size_t i = 1; i < n; i++)
        differs.push_back(ew([](float v, float f) { return v - f; }, views[i].light, views[0].light));
    for (const auto& level : LEVELS) {
        int shrink = level[0], steps = level[1];
        int w = std::max(16, LAYER_WIDTH / shrink);
        int h = std::max(16, pyround(static_cast<double>(ht) * w / wd));
        Mat first = blur(coarse(views[0].light, h, w), 1.0);
        std::vector<Mat> some = counts(views, h, w);
        // A view that counts for less differs from the first by less.
        lights.assign(1, first);
        for (size_t i = 1; i < n; i++)
            lights.push_back(ew([](float f, float a, float s) { return f + a * s; }, first,
                                apart(differs[i - 1], h, w), some[i]));
        std::vector<Mat> counted;
        for (const Mat& s : some) counted.push_back(ew([](float v) { return v > 0 ? 1.f : 0.f; }, s));
        low = Mat(h, w, CV_32FC3, cv::Scalar::all(INF));
        for (size_t i = 0; i < n; i++)
            low = ew([](float l, float v, float c) { return c > 0 ? std::min(l, v) : l; }, low, lights[i], counted[i]);
        std::vector<Mat> over, across, down;
        for (size_t i = 0; i < n; i++) {
            over.push_back(
                ew([](float v, float l, float c) { return c > 0 ? v - l : 0.f; }, lights[i], low, counted[i]));
            // A difference counts only where both its pixels do.
            Mat ac = counted[i].clone(), dn = counted[i].clone();
            for (int y = 0; y < h; y++) {
                float* a = ac.ptr<float>(y);
                const float* c = counted[i].ptr<float>(y);
                for (int x = 0; x + 1 < w; x++) a[x] *= c[x + 1];
                if (y + 1 < h) {
                    float* d = dn.ptr<float>(y);
                    const float* below = counted[i].ptr<float>(y + 1);
                    for (int x = 0; x < w; x++) d[x] *= below[x];
                }
            }
            across.push_back(ac);
            down.push_back(dn);
        }
        Mat start = common.empty() ? zeros(low) : resize(common, w, h, cv::INTER_LINEAR);
        Mat most = ew([](float l) { return l * static_cast<float>(VEIL_MOST); }, low);
        common = shared(over, across, down, most, ew([](float s, float m) { return std::min(s, m); }, start, most),
                        steps);
    }
    Mat held = ew(
        [](float c, float l) {
            float near = c / std::max(l * static_cast<float>(VEIL_MOST), 1e-6f);
            return ramp(near, KEPT_HELD[0], KEPT_HELD[1]);
        },
        common, low);
    Mat layer = ew([](float f, float l, float c) { return std::max(f - (l - c), 0.f); }, lights[0], low, common);
    return {layer, held};
}

Mat shared(const std::vector<Mat>& over, const std::vector<Mat>& across, const std::vector<Mat>& down,
           const Mat& most, const Mat& start, int steps) {
    // Chambolle and Pock's primal-dual steps, a pixel at a time, as
    // `_steps` has them.
    const int n = static_cast<int>(over.size());
    const int h = most.rows, w = most.cols, channels = most.channels();
    const float step = static_cast<float>(0.99 / std::sqrt(8.0 * n));
    const float cost = static_cast<float>(VEIL_COST * static_cast<double>(step));
    std::vector<Mat> px, py;
    for (int i = 0; i < n; i++) {
        px.push_back(zeros(most));
        py.push_back(zeros(most));
    }
    Mat m = start.clone(), ahead = m.clone();
    Mat sx = zeros(most), sy = zeros(most);
    // Small ones are quicker on one thread than handed out.
    const bool spread = h * w >= 64 * 64;
    auto each_row = [&](const std::function<void(int)>& row) {
        if (spread)
            rows(h, row);
        else
            for (int y = 0; y < h; y++) row(y);
    };
    for (int round = 0; round < steps; round++) {
        each_row([&](int y) {
            float* sxr = sx.ptr<float>(y);
            float* syr = sy.ptr<float>(y);
            std::fill(sxr, sxr + w * channels, 0.f);
            std::fill(syr, syr + w * channels, 0.f);
            const float* a0 = ahead.ptr<float>(y);
            const float* a1 = y < h - 1 ? ahead.ptr<float>(y + 1) : nullptr;
            for (int i = 0; i < n; i++) {
                const float* o0 = over[i].ptr<float>(y);
                const float* o1 = y < h - 1 ? over[i].ptr<float>(y + 1) : nullptr;
                const float* wxr = across[i].ptr<float>(y);
                const float* wyr = down[i].ptr<float>(y);
                float* pxr = px[i].ptr<float>(y);
                float* pyr = py[i].ptr<float>(y);
                for (int x = 0; x < w; x++) {
                    float wx = wxr[x], wy = wyr[x];
                    float size = 0.f;
                    for (int c = 0; c < channels; c++) {
                        int at = x * channels + c;
                        float gx = 0.f, gy = 0.f;
                        if (x < w - 1) gx = (a0[at + channels] - a0[at]) + (o0[at + channels] - o0[at]);
                        if (a1) gy = (a1[at] - a0[at]) + (o1[at] - o0[at]);
                        float a = (pxr[at] + step * gx) * wx;
                        float b = (pyr[at] + step * gy) * wy;
                        pxr[at] = a;
                        pyr[at] = b;
                        size += a * a + b * b;
                    }
                    // Onto the unit ball over both directions and the
                    // three channels at once.
                    size = std::sqrt(size);
                    for (int c = 0; c < channels; c++) {
                        int at = x * channels + c;
                        if (size > 1.f) {
                            pxr[at] /= size;
                            pyr[at] /= size;
                        }
                        sxr[at] += pxr[at];
                        syr[at] += pyr[at];
                    }
                }
            }
        });
        each_row([&](int y) {
            const float* sxr = sx.ptr<float>(y);
            const float* syr = sy.ptr<float>(y);
            const float* above = y > 0 ? sy.ptr<float>(y - 1) : nullptr;
            const float* mostr = most.ptr<float>(y);
            float* mr = m.ptr<float>(y);
            float* ar = ahead.ptr<float>(y);
            for (int x = 0; x < w; x++)
                for (int c = 0; c < channels; c++) {
                    int at = x * channels + c;
                    // The divergence of (sx, sy).
                    float div = 0.f;
                    if (x < w - 1) div += sxr[at];
                    if (x > 0) div -= sxr[at - channels];
                    if (y < h - 1) div += syr[at];
                    if (above) div -= above[at];
                    float next = mr[at] + step * div - cost;
                    if (next > mostr[at]) next = mostr[at];
                    if (next < 0) next = 0.f;
                    ar[at] = 2 * next - mr[at];
                    mr[at] = next;
                }
        });
    }
    return m;
}

Mat kept(const Mat& layer, const Mat& held) {
    int ht = layer.rows, wd = layer.cols;
    std::array<float, 3> even_{};
    for (int c = 0; c < 3; c++) {
        std::vector<float> values = flat(channel(layer, c));
        even_[c] = quantile(values, KEPT / 100.0);
    }
    Mat least(ht, wd, CV_32FC3), level_(ht, wd, CV_32F);
    rows(ht, [&](int y) {
        const float* p = layer.ptr<float>(y);
        float* l = least.ptr<float>(y);
        float* o = level_.ptr<float>(y);
        for (int x = 0; x < wd; x++) {
            // How much of the even light a place has: of the colour it
            // has the most of.
            float most = -INF;
            for (int c = 0; c < 3; c++) {
                float v = std::min(p[x * 3 + c], even_[c]);
                l[x * 3 + c] = v;
                most = std::max(most, v / std::max(even_[c], 1e-6f));
            }
            o[x] = most;
        }
    });
    int rim_ = std::max(1, pyround(wd * KEPT_RIM));
    Mat inner;
    cv::copyMakeBorder(level_(cv::Rect(rim_, rim_, wd - 2 * rim_, ht - 2 * rim_)).clone(), inner, rim_, rim_, rim_,
                       rim_, cv::BORDER_REPLICATE);
    int wide = std::max(3, pyround(wd * KEPT_FIGURE)) | 1;
    Mat less = ew([](float i, float h) { return (1 - i) * (1 - h); }, inner, max3(held));
    Mat full = ew([](float v) { return 1 - v; }, opened(less, ellipse(wide)));
    int reach_ = std::max(1, pyround(wd * KEPT_EASE));
    Mat sq = square(3), cr = cross3();
    Mat eased = full;
    float rise = static_cast<float>(1.0 / reach_);
    for (int step = 0; step < reach_; step++)
        // Square and cross by turns: about as far each way.
        eased = ew([rise](float e, float n) { return std::min(e, n + rise); }, eased,
                   erode(eased, step % 2 ? cr : sq));
    eased = ew([](float e, float l) { return std::min(e, l); }, eased, level_);
    Mat five = square(5);
    Mat edge = ew([](float d, float e) { return ramp(d - e, KEPT_EDGE[0], KEPT_EDGE[1]); }, dilate(full, five),
                  erode(full, five));
    Mat near = blur(dilate(edge, ellipse(2 * reach_ + 1)), reach_ / 2.0);
    level_ = ew([](float l, float e, float n) { return l - (l - e) * clipf(n, 0.f, 1.f); }, level_, eased, near);
    Mat out(ht, wd, CV_32FC3);
    rows(ht, [&](int y) {
        const float* l = least.ptr<float>(y);
        const float* v = level_.ptr<float>(y);
        float* o = out.ptr<float>(y);
        for (int x = 0; x < wd; x++)
            for (int c = 0; c < 3; c++) o[x * 3 + c] = std::min(l[x * 3 + c], even_[c] * v[x]);
    });
    return out;
}

}  // namespace frame::scan
