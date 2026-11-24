// crop <photo.npy> <logits.npy> <sure>: what the C++ core makes of the crop model's answer about a museum
// photograph (`frame_crop_find`): the verdict, then the work's corners and the surround's, a line each ("-"
// where there is none). crop box <photo.npy> <into.npy>: the photograph as the model takes it (`frame_crop_letterbox`),
// written as (3 × 384) × 384 floats; the box as a line. crop plate <photo.npy> <over> <x0> <y0> … <y3>: a print's
// sheet cut down round its impression (`frame_crop_plate`): 1 or 0, then the cut's corners and the impression's.
#include "../include/frame_scan.h"
#include "../src/npy.hpp"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

int main(int argc, char** argv) {
    char error[512] = "";
    if (argc == 4 && std::strcmp(argv[1], "box") == 0) {
        npy::Array photo = npy::load(argv[2]);
        std::vector<float> into(3 * 384 * 384);
        int box[4];
        if (frame_crop_letterbox(photo.data.data(), photo.shape[0], photo.shape[1], 384, into.data(), box, error,
                                 sizeof(error)) != 0) {
            std::fprintf(stderr, "%s\n", error);
            return 1;
        }
        npy::save(argv[3], cv::Mat(3 * 384, 384, CV_32F, into.data()));
        std::printf("%d %d %d %d\n", box[0], box[1], box[2], box[3]);
        return 0;
    }
    if (argc == 12 && std::strcmp(argv[1], "plate") == 0) {
        npy::Array photo = npy::load(argv[2]);
        double sheet[8], cut[8], plate[8];
        for (int i = 0; i < 8; i++) sheet[i] = std::strtod(argv[4 + i], nullptr);
        int found = 0;
        int made = frame_crop_plate(photo.data.data(), photo.shape[0], photo.shape[1], sheet,
                                    std::strtod(argv[3], nullptr), cut, plate, &found, error, sizeof(error));
        if (made < 0) {
            std::fprintf(stderr, "%s\n", error);
            return 1;
        }
        std::printf("%d\n", made);
        for (int layer = 0; layer < 2; layer++) {
            const double* q = layer == 0 ? cut : plate;
            if (!(found & (1 << layer))) {
                std::printf("-\n");
                continue;
            }
            for (int i = 0; i < 8; i++) std::printf(i ? " %.17g" : "%.17g", q[i]);
            std::printf("\n");
        }
        return 0;
    }
    if (argc == 4) {
        npy::Array photo = npy::load(argv[1]);
        npy::Array logits = npy::load(argv[2]);
        double work[8], surround[8];
        int found = 0;
        int verdict = frame_crop_find(photo.data.data(), photo.shape[0], photo.shape[1],
                                      reinterpret_cast<const float*>(logits.data.data()), logits.shape[1],
                                      std::strtod(argv[3], nullptr), 0.9 /* crop_model.SURE */, work, surround, &found, error, sizeof(error));
        if (verdict < 0) {
            std::fprintf(stderr, "%s\n", error);
            return 1;
        }
        std::printf("%d\n", verdict);
        for (int layer = 0; layer < 2; layer++) {
            const double* q = layer == 0 ? work : surround;
            if (!(found & (1 << layer))) {
                std::printf("-\n");
                continue;
            }
            for (int i = 0; i < 8; i++) std::printf(i ? " %.17g" : "%.17g", q[i]);
            std::printf("\n");
        }
        return 0;
    }
    std::fprintf(stderr, "crop photo.npy logits.npy sure\ncrop box photo.npy into.npy\ncrop plate photo.npy over x0 y0 … y3\n");
    return 2;
}
