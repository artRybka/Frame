// lens straight <photo.npy> <k1> [<centre x> <centre y> <table values…>]: the photograph (8 bits, RGB) as a lens
// without that bend would have drawn it, in place, by the C++ core; seconds it took, as a line.
// lens moved|bent <columns> <rows> <k1|-> <centre x> <centre y> <table file|-> <x> <y>…: the points moved, a line each.
#include "../include/frame_scan.h"

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

namespace {

std::vector<double> table_of(const char* path) {
    std::vector<double> table;
    if (std::strcmp(path, "-") == 0) return table;
    std::ifstream in(path);
    double value;
    while (in >> value) table.push_back(value);
    return table;
}

}  // namespace

int main(int argc, char** argv) {
    char error[512] = "";
    if (argc >= 7 && std::strcmp(argv[1], "straight") == 0) {
        std::vector<double> table = table_of(argv[6]);
        auto began = std::chrono::steady_clock::now();
        if (frame_scan_straight_file(argv[2], std::atof(argv[3]), table.empty() ? nullptr : table.data(),
                                     static_cast<int>(table.size()), std::atof(argv[4]), std::atof(argv[5]), error,
                                     sizeof(error)) != 0) {
            std::fprintf(stderr, "%s\n", error);
            return 1;
        }
        std::printf("%.3f\n", std::chrono::duration<double>(std::chrono::steady_clock::now() - began).count());
        return 0;
    }
    if (argc >= 8 && (std::strcmp(argv[1], "moved") == 0 || std::strcmp(argv[1], "bent") == 0)) {
        std::vector<double> table = table_of(argv[7]);
        std::vector<double> points;
        for (int n = 8; n < argc; n++) points.push_back(std::strtod(argv[n], nullptr));
        if (frame_scan_lens_points(points.data(), static_cast<int>(points.size() / 2), std::atoi(argv[2]),
                                   std::atoi(argv[3]), std::strtod(argv[4], nullptr),
                                   table.empty() ? nullptr : table.data(), static_cast<int>(table.size()),
                                   std::strtod(argv[5], nullptr), std::strtod(argv[6], nullptr),
                                   std::strcmp(argv[1], "bent") == 0, error, sizeof(error)) != 0) {
            std::fprintf(stderr, "%s\n", error);
            return 1;
        }
        for (size_t n = 0; n + 1 < points.size(); n += 2) std::printf("%.17g %.17g\n", points[n], points[n + 1]);
        return 0;
    }
    std::fprintf(stderr, "lens straight photo.npy k1 centre_x centre_y table|-\n"
                         "lens moved|bent columns rows k1 centre_x centre_y table|- x y…\n");
    return 2;
}
