// merge <first.npy> <out.npy> <anyway 0|1> <x0 y0 x1 y1 x2 y2 x3 y3> <side.npy>…: the scan of three by
// the C++ core, photographs given and taken as .npy (RGB, 8 bits); what came of it as one line of JSON.
#include "../src/npy.hpp"
#include "../src/scan.hpp"

#include <chrono>
#include <cstdio>
#include <cstdlib>

int main(int argc, char** argv) {
    if (argc < 13) {
        std::fprintf(stderr, "merge first.npy out.npy anyway x0 y0 … x3 y3 side.npy…\n");
        return 2;
    }
    cv::Mat first = npy::load(argv[1]).mat();
    bool anyway = std::atoi(argv[3]) != 0;
    std::array<cv::Point2d, 4> corners;
    for (int i = 0; i < 4; i++) corners[i] = cv::Point2d(std::atof(argv[4 + 2 * i]), std::atof(argv[5 + 2 * i]));
    std::vector<cv::Mat> sides;
    for (int i = 12; i < argc; i++) sides.push_back(npy::load(argv[i]).mat());
    auto began = std::chrono::steady_clock::now();
    frame::scan::Merged m = frame::scan::merge(first, sides, corners, anyway);
    double took = std::chrono::duration<double>(std::chrono::steady_clock::now() - began).count();
    npy::save(argv[2], m.image);
    std::printf("{\"used\": %d, \"removed\": %.4f, \"doubt\": %s, \"seconds\": %.2f, \"took\": {", m.used, m.removed,
                m.doubt ? "true" : "false", took);
    bool more = false;
    for (const auto& [part, seconds] : m.took) {
        std::printf("%s\"%s\": %.2f", more ? ", " : "", part.c_str(), seconds);
        more = true;
    }
    std::printf("}}\n");
    return 0;
}
