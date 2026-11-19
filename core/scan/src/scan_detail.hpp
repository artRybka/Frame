// The steps of the merge, one for each of `imaging/reflections.py`'s and
// under its name there: what each is for, and what of Mateusz's scans it
// came from, is told there and not twice.
#pragma once

#include "constants.hpp"
#include "np.hpp"
#include "scan.hpp"

#include <opencv2/features.hpp>

#include <functional>
#include <optional>
#include <utility>
#include <vector>

namespace frame::scan {

using cv::Mat;
using np::M33;

/// `_View`: the work as one photograph shows it, laid over the first's.
struct View {
    Mat light;  // linear, H × W × 3
    int side = 0;  // -1 taken from the left, 1 from the right, 0 the first
    double hidden = HIDDEN;
    double shows = HIDDEN;
    Mat photo;  // a side view's photograph as given (empty: none)
    Mat seen;  // where each place of the view lies in it, H × W × 2 (empty: none)
    std::array<double, 3> gains{1.0, 1.0, 1.0};
};

/// What a photograph is known by in another: its points and what is about
/// each.
struct Marks {
    std::vector<cv::KeyPoint> points;
    Mat about;
};

/// `_finer`'s answer: for a part of the first photograph (where the views'
/// pixels lie in it, how much of each of its places is a glare).
using Finer = std::function<Mat(const M33&, const Mat&)>;

// scan_lay.cpp
std::array<cv::Point2d, 4> grown(const std::array<cv::Point2d, 4>& corners);
M33 larger(double across, double down);
Mat resized(const Mat& img, double scale);
Mat linear(const Mat& img);
Mat srgb(const Mat& light);
Marks marks(const Mat& img);
std::optional<View> lay(const Mat& front, const Marks& first, const Mat& photo);
std::pair<Mat, Mat> settled(const Mat& front, const Mat& side, const M33& found);
Mat fine(const Mat& light);
Mat off(const Mat& first, const Mat& other, int tile);
std::optional<Mat> field(const Mat& off, int tile, cv::Size shape);
Mat about(const Mat& said);

// scan_views.cpp
Mat coarse(const Mat& light, int h, int w);
Mat apart(const Mat& apart, int h, int w);
std::vector<Mat> counts(const std::vector<View>& views, int h, int w, bool tone = false);
void hide(std::vector<View>& views);
void even(std::vector<View>& views);
std::pair<Mat, Mat> reflection(const std::vector<View>& views);
Mat shared(const std::vector<Mat>& over, const std::vector<Mat>& across, const std::vector<Mat>& down,
           const Mat& most, const Mat& start, int steps);
Mat kept(const Mat& layer, const Mat& held);

// scan_alone.cpp
struct Alone {
    Mat alone;
    std::optional<std::pair<Mat, Mat>> swap;  // the work under a glare, and how much of a place is one
    double differ = 0;
    std::vector<Mat> told;
};
Alone alone(const std::vector<View>& views);
Mat told(const Mat& side, const Mat& apart, const Mat& counts, const Mat& first, const Mat* reach = nullptr);
Mat own(const Mat& first, const Mat& side, const Mat& tells, const Mat& counts);
std::pair<Mat, Mat> one(const std::vector<Mat>& says, const std::vector<Mat>& plains, const Mat& counts);
std::vector<std::pair<Mat, Mat>> tellings(const std::vector<View>& views, const std::vector<Mat>& told,
                                          double black);
Mat counts_for(const Mat& light, const Mat& least);
Mat least_of(const std::vector<std::pair<Mat, Mat>>& tellings);
std::pair<Mat, Mat> from_sides(const std::vector<View>& views, const std::vector<Mat>& told, double black);
Mat toned(const Mat& work, const Mat& to, const Mat& patch);
Mat level(const Mat& now, const Mat& work, const Mat& patch, const Mat& beside);
Mat rim(const std::vector<View>& views, const std::vector<Mat>& told, const Mat& less, const Mat& patch,
        const Mat& beside);
Mat outward(const Mat& work, const Mat& patch, double far);

// scan_mend.cpp
Finer finer(const std::vector<View>& views, const std::vector<Mat>& told, const Mat& work);
std::pair<Mat, Mat> mend(const Mat& now, const Mat& front, const Mat& alone, const Mat& soft,
                         const std::vector<View>& views, const std::vector<Mat>& told);
Mat reach(const Mat& of, double grow, double soft);
Mat line(const Mat& theirs, const Mat& mine, const Mat& free);
Mat carried(const Mat& of, const Mat& sure);
std::pair<Mat, Mat> shown(const std::vector<View>& views);
std::pair<Mat, Mat> veiled(const Mat& now, const Mat& soft, const std::vector<View>& views, const Mat& sheen);
struct Grain {
    Mat veil, low, share;
};
Grain grain(const Mat& less, const Mat& alone, const Mat& soft, const std::vector<View>& sides,
            const Mat* lamp);

// scan_whole.cpp
Mat around(const Mat& part);
Mat subtract(const Mat& first, const Grain& layer, const Mat& mend,
             const std::optional<std::pair<Mat, Mat>>& swap, const M33& to_photo,
             const std::array<cv::Point2d, 4>& quad, const Finer& finer, const Mat* theirs);

}  // namespace frame::scan
