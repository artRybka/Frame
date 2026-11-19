// check <golden> [step…]: each step of the C++ core given what the Python
// merge gave its own (tools/golden.py), and held against what that made.
#include "../src/npy.hpp"
#include "../src/scan_detail.hpp"

#include <chrono>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <map>
#include <sstream>

using namespace frame::scan;
namespace fs = std::filesystem;

static std::string golden;
static int failed = 0;

struct Call {
    std::map<std::string, std::string> said;

    explicit Call(const std::string& name) {
        std::ifstream in(golden + "/" + name + "/call.txt");
        if (!in) throw std::runtime_error("no call " + name);
        std::string line;
        while (std::getline(in, line)) {
            auto space = line.find(' ');
            said[line.substr(0, space)] = line.substr(space + 1);
        }
    }
    bool has(const std::string& key) const { return said.count(key) > 0; }
    bool none(const std::string& key) const { return said.count(key) && said.at(key) == "none"; }
    double num(const std::string& key) const { return std::stod(said.at(key)); }
    int len(const std::string& key) const { return std::stoi(said.at(key + ".len")); }
    npy::Array array(const std::string& key) const {
        const std::string& v = said.at(key);
        return npy::load(golden + "/arrays/" + v.substr(0, v.find(' ')));
    }
    Mat mat(const std::string& key) const { return array(key).mat(); }
    std::vector<Mat> mats(const std::string& key) const {
        std::vector<Mat> out;
        for (int i = 0; i < len(key); i++) out.push_back(mat(key + "." + std::to_string(i)));
        return out;
    }
    /// A stack of pictures in one array (N × H × W × C).
    std::vector<Mat> stack(const std::string& key) const { return array(key).mats(); }
    View view(const std::string& key) const {
        View v;
        v.light = mat(key + ".light");
        v.side = static_cast<int>(num(key + ".side"));
        v.hidden = num(key + ".hidden");
        v.shows = num(key + ".shows");
        if (!none(key + ".photo")) v.photo = mat(key + ".photo");
        if (!none(key + ".seen")) v.seen = mat(key + ".seen");
        Mat g = mat(key + ".gains");
        for (int i = 0; i < 3; i++) v.gains[i] = g.at<double>(i);
        return v;
    }
    std::vector<View> views(const std::string& key) const {
        std::vector<View> out;
        for (int i = 0; i < len(key); i++) out.push_back(view(key + "." + std::to_string(i)));
        return out;
    }
    M33 m33(const std::string& key) const { return M33(mat(key).ptr<double>()); }
};

/// How far `got` is from what Python made: fine within `allowed` (of the
/// largest value there, or of 1 where all is small).
static void held(const std::string& what, const Mat& got, const Mat& ref, double allowed = 2e-5,
                 bool levels = false) {
    if (got.rows != ref.rows || got.cols != ref.cols || got.channels() != ref.channels()) {
        std::printf("    %-28s SIZES %dx%dx%d against %dx%dx%d\n", what.c_str(), got.rows, got.cols, got.channels(),
                    ref.rows, ref.cols, ref.channels());
        failed++;
        return;
    }
    Mat a, b;
    got.reshape(1).convertTo(a, CV_64F);
    ref.reshape(1).convertTo(b, CV_64F);
    // Infinite or NaN in both is the same.
    double most = 0, sum = 0, scale = 0;
    size_t wrong = 0, n = a.total();
    const double* pa = a.ptr<double>();
    const double* pb = b.ptr<double>();
    Mat ac = a.isContinuous() ? a : a.clone(), bc = b.isContinuous() ? b : b.clone();
    pa = ac.ptr<double>();
    pb = bc.ptr<double>();
    for (size_t i = 0; i < n; i++) {
        bool fa = std::isfinite(pa[i]), fb = std::isfinite(pb[i]);
        if (!fa || !fb) {
            bool same = (std::isnan(pa[i]) && std::isnan(pb[i])) || pa[i] == pb[i];
            wrong += !same;
            continue;
        }
        double d = std::abs(pa[i] - pb[i]);
        most = std::max(most, d);
        sum += d;
        scale = std::max(scale, std::abs(pb[i]));
    }
    double of = levels ? 1.0 : std::max(scale, 1.0);
    bool ok = wrong == 0 && most <= allowed * of;
    std::printf("    %-28s %s max %.3g mean %.3g (values to %.3g)%s\n", what.c_str(), ok ? "ok  " : "OFF ", most,
                sum / std::max<size_t>(n, 1), scale, wrong ? "  and not finite alike" : "");
    failed += !ok;
}

static void held(const std::string& what, double got, double ref, double allowed = 1e-5) {
    bool ok = std::abs(got - ref) <= allowed * std::max(1.0, std::abs(ref));
    std::printf("    %-28s %s %.8g against %.8g\n", what.c_str(), ok ? "ok  " : "OFF ", got, ref);
    failed += !ok;
}

static Marks marks_of(const Call& c, const std::string& key) {
    Marks m;
    Mat table = c.mat(key + ".0");
    for (int i = 0; i < table.rows; i++) {
        const double* r = table.ptr<double>(i);
        m.points.emplace_back(cv::Point2f(static_cast<float>(r[0]), static_cast<float>(r[1])),
                              static_cast<float>(r[2]), static_cast<float>(r[3]), static_cast<float>(r[4]),
                              static_cast<int>(r[5]));
    }
    m.about = c.mat(key + ".1");
    return m;
}

static Mat stacked(const std::vector<Mat>& each) {
    Mat out;
    cv::merge(each, out);
    return out;
}

static std::array<cv::Point2d, 4> quad_of(const Mat& table) {
    std::array<cv::Point2d, 4> quad;
    for (int i = 0; i < 4; i++) quad[i] = cv::Point2d(table.at<double>(i, 0), table.at<double>(i, 1));
    return quad;
}

/// Two photographs, level by level: how many of their values differ, and
/// by how much.
static void levels(const std::string& what, const Mat& got, const Mat& ref) {
    if (got.size() != ref.size() || got.type() != ref.type()) {
        std::printf("    %-28s SIZES\n", what.c_str());
        failed++;
        return;
    }
    Mat apart;
    cv::absdiff(got, ref, apart);
    apart = apart.reshape(1);
    size_t n = apart.total();
    int by1 = cv::countNonZero(apart), by2 = cv::countNonZero(apart > 1), by4 = cv::countNonZero(apart > 3);
    double most;
    cv::minMaxLoc(apart, nullptr, &most);
    bool ok = most <= 2 && static_cast<size_t>(by2) <= n / 100000;
    std::printf("    %-28s %s of %zu values %d differ (%.4f%%), %d by 2 or more, %d by 4 or more, the most %g\n",
                what.c_str(), ok ? "ok  " : "OFF ", n, by1, 100.0 * by1 / n, by2, by4, most);
    failed += !ok;
}

static Finer the_finer();

using Step = std::function<void(const Call&)>;

static std::map<std::string, Step> steps() {
    std::map<std::string, Step> s;
    s["_marks"] = [](const Call& c) {
        Marks m = marks(c.mat("in.0"));
        Mat table = c.mat("out.0");
        std::printf("    points %zu against %d\n", m.points.size(), table.rows);
        held("what is about each", m.about, c.mat("out.1"), 1.0, true);
    };
    s["_fine"] = [](const Call& c) { held("fine", fine(c.mat("in.0")), c.mat("out")); };
    s["_off"] = [](const Call& c) {
        held("off", off(c.mat("in.0"), c.mat("in.1"), static_cast<int>(c.num("in.2"))), c.mat("out"), 1e-3);
    };
    s["_about"] = [](const Call& c) { held("about", about(c.mat("in.0")), c.mat("out")); };
    s["_field"] = [](const Call& c) {
        int ht = static_cast<int>(c.num("in.2.0")), wd = static_cast<int>(c.num("in.2.1"));
        auto f = field(c.mat("in.0"), static_cast<int>(c.num("in.1")), cv::Size(wd, ht));
        if (c.none("out")) {
            std::printf("    %-28s %s\n", "no field", f ? "OFF" : "ok");
            failed += bool(f);
            return;
        }
        // Python's is 2 × H × W.
        held("field", *f, stacked(c.stack("out")));
    };
    s["_settled"] = [](const Call& c) {
        auto [over, seen] = settled(c.mat("in.0"), c.mat("in.1"), c.m33("in.2"));
        held("laid over", over, c.mat("out.0"), 1.0, true);
        held("where it lies", seen, c.mat("out.1"), 0.01, true);
    };
    s["_rival"] = [](const Call& c) {
        auto points = [&](const std::string& key) {
            Mat table = c.mat(key);
            std::vector<cv::Point2f> out;
            for (int i = 0; i < table.rows; i++) out.emplace_back(table.at<float>(i, 0), table.at<float>(i, 1));
            return out;
        };
        held("held by another laying", rival(points("in.0"), points("in.1"), c.m33("in.2"),
                                             static_cast<int>(c.num("in.3"))),
             c.num("out"));
    };
    s["_lay"] = [](const Call& c) {
        auto v = lay(c.mat("in.0"), marks_of(c, "in.1"), c.mat("in.2"));
        if (c.none("out")) {
            failed += bool(v);
            return;
        }
        held("light", v->light, c.mat("out.light"), 0.01, true);
        held("side", v->side, c.num("out.side"));
        held("seen", v->seen, c.mat("out.seen"), 0.01, true);
    };
    s["_apart"] = [](const Call& c) {
        held("apart", apart(c.mat("in.0"), static_cast<int>(c.num("in.1.0")), static_cast<int>(c.num("in.1.1"))),
             c.mat("out"));
    };
    s["_counts"] = [](const Call& c) {
        bool tone = c.has("in.3") && c.num("in.3") != 0;
        auto got = counts(c.views("in.0"), static_cast<int>(c.num("in.1")), static_cast<int>(c.num("in.2")), tone);
        held("counts", stacked(got), stacked(c.stack("out")));
    };
    s["_hide"] = [](const Call& c) {
        auto views = c.views("in.0");
        hide(views);
        for (size_t n = 1; n < views.size(); n++) {
            std::string key = "out.1." + std::to_string(n);
            held("hidden " + std::to_string(n), views[n].hidden, c.num(key + ".hidden"));
            held("shows " + std::to_string(n), views[n].shows, c.num(key + ".shows"));
        }
    };
    s["_even"] = [](const Call& c) {
        auto views = c.views("in.0");
        even(views);
        for (size_t n = 1; n < views.size(); n++) {
            std::string key = "out.1." + std::to_string(n);
            held("light " + std::to_string(n), views[n].light, c.mat(key + ".light"));
            Mat g = c.mat(key + ".gains");
            for (int k = 0; k < 3; k++) held("gain", views[n].gains[k], g.at<double>(k));
        }
    };
    s["_reflection"] = [](const Call& c) {
        auto [layer, held_] = reflection(c.views("in.0"));
        held("layer", layer, c.mat("out.0"), 1e-4);
        held("held", held_, c.mat("out.1"), 1e-3);
    };
    s["_shared"] = [](const Call& c) {
        Mat got = shared(c.stack("in.0"), c.stack("in.1"), c.stack("in.2"), c.mat("in.3"), c.mat("in.4"),
                         static_cast<int>(c.num("in.5")));
        held("shared", got, c.mat("out"));
    };
    s["_kept"] = [](const Call& c) { held("kept", kept(c.mat("in.0"), c.mat("in.1")), c.mat("out")); };
    s["_told"] = [](const Call& c) {
        Mat reach;
        if (c.has("in.4") && !c.none("in.4")) reach = c.mat("in.4");
        held("told", told(c.mat("in.0"), c.mat("in.1"), c.mat("in.2"), c.mat("in.3"), reach.empty() ? nullptr : &reach),
             c.mat("out"), 1e-4);
    };
    s["_own"] = [](const Call& c) {
        held("own", own(c.mat("in.0"), c.mat("in.1"), c.mat("in.2"), c.mat("in.3")), c.mat("out"), 1e-4);
    };
    s["_one"] = [](const Call& c) {
        auto [only, second] = one(c.mats("in.0"), c.mats("in.1"), c.mat("in.2"));
        held("only", only, c.mat("out.0"), 1e-3);
        held("second", second, c.mat("out.1"));
    };
    s["_tellings"] = [](const Call& c) {
        auto got = tellings(c.views("in.0"), c.mats("in.1"), c.num("in.2"));
        for (size_t n = 0; n < got.size(); n++) {
            std::string key = "out." + std::to_string(n);
            held("tells " + std::to_string(n), got[n].first, c.mat(key + ".0"), 1e-4);
            held("light " + std::to_string(n), got[n].second, c.mat(key + ".1"), 1e-4);
        }
    };
    s["_from_sides"] = [](const Call& c) {
        auto [work, shown_] = from_sides(c.views("in.0"), c.mats("in.1"), c.num("in.2"));
        held("work", work, c.mat("out.0"), 1e-4);
        held("shown", shown_, c.mat("out.1"));
    };
    s["_alone"] = [](const Call& c) {
        Alone a = alone(c.views("in.0"));
        held("alone", a.alone, c.mat("out.0"), 1e-3);
        if (c.none("out.1")) {
            std::printf("    %-28s %s\n", "no glare", a.swap ? "OFF" : "ok");
            failed += bool(a.swap);
        } else {
            held("work under the glare", a.swap->first, c.mat("out.1.0"), 1e-3);
            held("patch", a.swap->second, c.mat("out.1.1"), 1e-3);
        }
        held("differ", a.differ, c.num("out.2"));
        auto told_ = c.mats("out.3");
        for (size_t n = 0; n < told_.size(); n++) held("told " + std::to_string(n), a.told[n], told_[n], 1e-4);
    };
    s["_reach"] = [](const Call& c) {
        held("reach", reach(c.mat("in.0"), c.num("in.1"), c.num("in.2")), c.mat("out"), 1e-4);
    };
    s["_line"] = [](const Call& c) {
        held("line", line(c.mat("in.0"), c.mat("in.1"), c.mat("in.2")), c.mat("out"), 1e-4);
    };
    s["_carried"] = [](const Call& c) {
        held("carried", carried(c.mat("in.0"), c.mat("in.1")), c.mat("out"), 1e-4);
    };
    s["_shown"] = [](const Call& c) {
        auto [darker, sure] = shown(c.views("in.0"));
        held("darker", darker, c.mat("out.0"), 1e-4);
        held("sure", sure, c.mat("out.1"));
    };
    s["_veiled"] = [](const Call& c) {
        auto [off_, heavy] = veiled(c.mat("in.0"), c.mat("in.1"), c.views("in.2"), c.mat("in.3"));
        held("to come off", off_, c.mat("out.0"), 1e-3);
        held("theirs", heavy, c.mat("out.1"), 1e-3);
    };
    s["_grain"] = [](const Call& c) {
        Mat lamp;
        if (!c.none("in.4")) lamp = c.mat("in.4");
        Grain g = grain(c.mat("in.0"), c.mat("in.1"), c.mat("in.2"), c.views("in.3"), lamp.empty() ? nullptr : &lamp);
        held("veil", g.veil, c.mat("out.0"), 1e-4);
        held("low", g.low, c.mat("out.1"), 1e-4);
        held("share", g.share, c.mat("out.2"), 1e-3);
    };
    s["_mend"] = [](const Call& c) {
        auto [mend_, theirs] =
            mend(c.mat("in.0"), c.mat("in.1"), c.mat("in.2"), c.mat("in.3"), c.views("in.4"), c.mats("in.5"));
        held("mend", mend_, c.mat("out.0"), 1e-3);
        held("theirs", theirs, c.mat("out.1"), 1e-3);
    };
    s["fine"] = [](const Call& c) {
        static const Finer made = the_finer();
        held("finer", made(c.m33("in.0"), c.mat("in.1")), c.mat("out"), 1e-3);
    };
    s["_subtract"] = [](const Call& c) {
        Grain layer{c.mat("in.1.0"), c.mat("in.1.1"), c.mat("in.1.2")};
        std::optional<std::pair<Mat, Mat>> swap;
        if (!c.none("in.3")) swap = std::make_pair(c.mat("in.3.0"), c.mat("in.3.1"));
        Mat theirs;
        if (!c.none("in.7")) theirs = c.mat("in.7");
        Finer finer_;
        if (!c.none("in.6")) finer_ = the_finer();
        Mat got = subtract(c.mat("in.0"), layer, c.mat("in.2"), swap, c.m33("in.4"), quad_of(c.mat("in.5")), finer_,
                           theirs.empty() ? nullptr : &theirs);
        levels("the photograph", got, c.mat("out"));
    };
    s["merge"] = [](const Call& c) {
        Mat corners = c.mat("in.2");
        Merged m = merge(c.mat("in.0"), c.mats("in.1"), quad_of(corners), c.num("in.3") != 0);
        levels("the photograph", m.image, c.mat("out.0"));
        held("used", m.used, c.num("out.1"));
        held("removed", m.removed, c.num("out.2"));
        held("doubt", m.doubt, c.num("out.3"));
        for (const auto& [part, seconds] : m.took) std::printf("    %-8s %.2f s\n", part.c_str(), seconds);
    };
    s["_toned"] = [](const Call& c) {
        held("toned", toned(c.mat("in.0"), c.mat("in.1"), c.mat("in.2")), c.mat("out"), 1e-4);
    };
    s["_outward"] = [](const Call& c) {
        held("outward", outward(c.mat("in.0"), c.mat("in.1"), c.num("in.2")), c.mat("out"));
    };
    s["_rim"] = [](const Call& c) {
        held("rim", rim(c.views("in.0"), c.mats("in.1"), c.mat("in.2"), c.mat("in.3"), c.mat("in.4")), c.mat("out"),
             1e-4);
    };
    s["_around"] = [](const Call& c) { held("around", around(c.mat("in.0")), c.mat("out")); };
    s["_level"] = [](const Call& c) {
        held("level", level(c.mat("in.0"), c.mat("in.1"), c.mat("in.2"), c.mat("in.3")), c.mat("out"), 1e-4);
    };
    return s;
}

static Finer the_finer() {
    Call c("_finer.0");
    return finer(c.views("in.0"), c.mats("in.1"), c.mat("in.2"));
}

int main(int argc, char** argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    golden = argv[1];
    std::vector<std::string> only(argv + 2, argv + argc);
    auto all = steps();
    std::vector<std::string> names;
    for (const auto& entry : fs::directory_iterator(golden))
        if (entry.is_directory() && entry.path().filename() != "arrays") names.push_back(entry.path().filename());
    std::sort(names.begin(), names.end());
    for (const auto& name : names) {
        std::string step = name.substr(0, name.rfind('.'));
        if (!all.count(step)) continue;
        if (!only.empty() && std::find(only.begin(), only.end(), step) == only.end()) continue;
        auto began = std::chrono::steady_clock::now();
        std::printf("%s\n", name.c_str());
        try {
            Call call(name);
            began = std::chrono::steady_clock::now();
            all[step](call);
        } catch (const std::exception& e) {
            std::printf("    FAILED: %s\n", e.what());
            failed++;
        }
        std::printf("    %.2f s\n", std::chrono::duration<double>(std::chrono::steady_clock::now() - began).count());
    }
    std::printf(failed ? "%d OFF\n" : "all as Python has it\n", failed);
    return failed ? 1 : 0;
}
