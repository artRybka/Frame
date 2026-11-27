// restore descreen <picture.npy> <into.npy>: the picture without its printed screen
// (`frame_restore_descreen`); the screen's points as a line. restore colours <picture.npy> <drawn.npy>
// <share> <into.npy>: the model's drawing brought to 2K and put in the picture's colours
// (`frame_restore_colours`); 1 or 0 (laid on its picture or kept as drawn) as a line. Checked against the
// server's Python by tools/restore.py.
#include "../include/frame_scan.h"
#include "../src/npy.hpp"

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

int main(int argc, char** argv) {
    char error[512] = "";
    auto start = std::chrono::steady_clock::now();
    auto seconds = [&] {
        return std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    };
    if (argc == 4 && std::strcmp(argv[1], "descreen") == 0) {
        npy::Array picture = npy::load(argv[2]);
        int found = 0;
        if (frame_restore_descreen(picture.data.data(), picture.shape[0], picture.shape[1], &found, error,
                                   sizeof(error)) != 0) {
            std::fprintf(stderr, "%s\n", error);
            return 1;
        }
        double took = seconds();
        npy::save(argv[3], cv::Mat(picture.shape[0], picture.shape[1], CV_8UC3, picture.data.data()));
        std::printf("%d %.3f\n", found, took);
        return 0;
    }
    if (argc == 6 && std::strcmp(argv[1], "colours") == 0) {
        npy::Array picture = npy::load(argv[2]);
        npy::Array drawn = npy::load(argv[3]);
        std::vector<unsigned char> into(2048 * 2048 * 3);
        int rows = 0, columns = 0, laid = 0;
        if (frame_restore_colours(picture.data.data(), picture.shape[0], picture.shape[1], drawn.data.data(),
                                  drawn.shape[0], drawn.shape[1], std::strtod(argv[4], nullptr), into.data(), &rows,
                                  &columns, &laid, error, sizeof(error)) != 0) {
            std::fprintf(stderr, "%s\n", error);
            return 1;
        }
        double took = seconds();
        npy::save(argv[5], cv::Mat(rows, columns, CV_8UC3, into.data()));
        std::printf("%d %.3f\n", laid, took);
        return 0;
    }
    std::fprintf(stderr, "restore descreen <picture.npy> <into.npy> | restore colours <picture.npy> <drawn.npy> <share> <into.npy>\n");
    return 2;
}
