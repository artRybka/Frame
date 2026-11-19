// A lens's own bend taken out of a photograph: the server's
// `imaging/lens.py` (`straight`, `moved`, `bent`). The phone does this to
// the scan it made before it sends it, and to what it shows him of the
// photographs, so that the server need not when the work is added
// (Mateusz 2026-11-19 09:52 UTC: "Czy tego także nie lepiej robić na
// iPhone? … telefon i tak pewnie zrobi to szybciej").
#include "scan.hpp"

#include <opencv2/core/utility.hpp>
#include <opencv2/imgproc.hpp>

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace frame::scan {

namespace {

// `lens.STRIP`: rows straightened at a time (the map of 48 MP whole is
// 400 MB).
const int STRIP = 512;
// `lens.moved` goes round so many times.
const int ROUNDS = 12;

// `Bend._middle`: the lens's middle in the photograph's pixels, and the
// radius there at which its distances are 1.
struct Middle {
    double cx, cy, reach;
};

Middle middle(const Bend& bend, int width, int height) {
    if (bend.table.empty()) return {(width - 1) / 2.0, (height - 1) / 2.0, std::hypot(double(width), double(height)) / 2};
    double cx = bend.centre[0] * width, cy = bend.centre[1] * height;
    double reach = std::hypot(std::max(cx, width - cx), std::max(cy, height - cy));
    return {cx - 0.5, cy - 0.5, reach};
}

// `Bend.by` of a table: `np.interp` at `at` (the radius times the table's
// last place) over the places 0, 1, 2…
double shared(const std::vector<double>& table, double at) {
    const int last = static_cast<int>(table.size()) - 1;
    if (!(at < last)) return table[last];
    if (at <= 0) return table[0];
    const int j = static_cast<int>(at);
    const double slope = (table[j + 1] - table[j]) / 1.0;
    return slope * (at - j) + table[j];
}

double rounded5(double v) { return std::round(std::min(std::max(v, 0.0), 1.0) * 1e5) / 1e5; }

}  // namespace

void straight(cv::Mat& photo, const Bend& bend) {
    if (photo.depth() != CV_8U) throw std::runtime_error("lens: the photograph is not of 8 bits");
    if (!bend.table.empty() && bend.table.size() < 2) throw std::runtime_error("lens: no table");
    const int width = photo.cols, height = photo.rows;
    const Middle at = middle(bend, width, height);
    // As NumPy has them beside float32, and every sum of 32 bits rounded
    // on its own (-ffp-contract=off): the map is the server's to the bit.
    const float cx = static_cast<float>(at.cx), cy = static_cast<float>(at.cy);
    const float half = static_cast<float>(at.reach), k1 = static_cast<float>(bend.k1);
    const float last = static_cast<float>(bend.table.empty() ? 0 : bend.table.size() - 1);
    std::vector<float> xs(width);
    for (int x = 0; x < width; x++) xs[x] = (static_cast<float>(x) - cx) / half;
    cv::Mat out(photo.size(), photo.type());
    for (int top = 0; top < height; top += STRIP) {
        const int rows = std::min(STRIP, height - top);
        cv::Mat mx(rows, width, CV_32FC1), my(rows, width, CV_32FC1);
        cv::parallel_for_(cv::Range(0, rows), [&](const cv::Range& range) {
            for (int r = range.start; r < range.end; r++) {
                const float y = (static_cast<float>(top + r) - cy) / half;
                const float yy = y * y;
                float* px = mx.ptr<float>(r);
                float* py = my.ptr<float>(r);
                for (int x = 0; x < width; x++) {
                    const float sum = xs[x] * xs[x] + yy;
                    float bent;
                    if (bend.table.empty()) {
                        bent = 1.f + k1 * sum;
                    } else {
                        const float radius = std::sqrt(sum);
                        bent = 1.f + static_cast<float>(shared(bend.table, static_cast<double>(radius * last)));
                    }
                    px[x] = xs[x] * bent * half + cx;
                    py[x] = y * bent * half + cy;
                }
            }
        });
        cv::remap(photo, out.rowRange(top, top + rows), mx, my, cv::INTER_LANCZOS4, cv::BORDER_REPLICATE);
    }
    photo = out;
}

std::vector<cv::Point2d> moved(const std::vector<cv::Point2d>& points, int width, int height, const Bend& bend, bool back) {
    std::vector<cv::Point2d> out;
    const Middle at = middle(bend, width, height);
    const bool table = !bend.table.empty();
    const double last = table ? static_cast<double>(bend.table.size() - 1) : 0;
    // A corner is said from the photograph's edges, a pixel's middle half
    // a pixel in: the one term is about the photograph's very middle.
    const double ox = table ? at.cx + 0.5 : width / 2.0, oy = table ? at.cy + 0.5 : height / 2.0;
    auto by = [&](double ux, double uy) {
        return table ? 1 + shared(bend.table, std::hypot(ux, uy) * last) : 1 + bend.k1 * (ux * ux + uy * uy);
    };
    for (const cv::Point2d& p : points) {
        const double px = (p.x * width - ox) / at.reach, py = (p.y * height - oy) / at.reach;
        double ux = px, uy = py;
        if (back) {
            const double bent = by(px, py);
            ux = px * bent;
            uy = py * bent;
        } else {
            for (int n = 0; n < ROUNDS; n++) {
                const double bent = by(ux, uy);
                ux = px / bent;
                uy = py / bent;
            }
        }
        out.emplace_back(rounded5((ux * at.reach + ox) / width), rounded5((uy * at.reach + oy) / height));
    }
    return out;
}

}  // namespace frame::scan
