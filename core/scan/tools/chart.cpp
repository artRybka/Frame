// chart <photo.npy> <tables>: the photograph (RGB, 8 bits) put in the colours a chart gives it, in place,
// by the C++ core; `tables` as the server's `colorchecker.tables` writes them. Seconds it took, as a line.
#include "../include/frame_scan.h"

#include <chrono>
#include <cstdio>

int main(int argc, char** argv) {
    if (argc != 3) {
        std::fprintf(stderr, "chart photo.npy tables\n");
        return 2;
    }
    char error[512] = "";
    auto began = std::chrono::steady_clock::now();
    if (frame_scan_chart_file(argv[1], argv[2], error, sizeof(error)) != 0) {
        std::fprintf(stderr, "%s\n", error);
        return 1;
    }
    std::printf("%.3f\n", std::chrono::duration<double>(std::chrono::steady_clock::now() - began).count());
    return 0;
}
