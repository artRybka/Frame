// made_up [side] [threads]: the made-up scene merged, and what came of it.
#include "../include/frame_scan.h"

#include <cstdio>
#include <cstdlib>

int main(int argc, char** argv) {
    int side = argc > 1 ? std::atoi(argv[1]) : 1400;
    if (argc > 2) frame_scan_threads(std::atoi(argv[2]));
    frame_scan_note note;
    char error[256] = "";
    if (frame_scan_made_up(side, &note, error, sizeof error) != 0) {
        std::fprintf(stderr, "%s\n", error);
        return 1;
    }
    std::printf("%s: used %d removed %.4f doubt %d | laid %.2f own %.2f layer %.2f mended %.2f whole %.2f\n",
                frame_scan_built(), note.used, note.removed, note.doubt, note.laid, note.own, note.layer,
                note.mended, note.whole);
    return 0;
}
