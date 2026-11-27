// Made by tools/constants.py from server/src/frame_server/imaging/reflections.py
// (and cut.py, crop_model.py, descreen.py, restorer.py): the numbers are set there (and told there why),
// never here.
#pragma once

#include <array>

namespace frame::scan {

inline constexpr double ALONE_ABOUT = 0.15;
inline constexpr double ALONE_FEW = 0.03;
inline constexpr int ALONE_FINE = 1024;
inline constexpr double ALONE_FROM = 0.0015;
inline constexpr double ALONE_FROM_OF = 0.015;
inline constexpr double ALONE_GRAIN = 0.005;
inline constexpr double ALONE_MOST = 0.9;
inline constexpr double ALONE_OFF = 0.003;
inline constexpr double ALONE_OFF_OF = 0.03;
inline constexpr std::array<double, 2> ALONE_ONE{0.15, 0.4};
inline constexpr double ALONE_PLAIN = 0.02;
inline constexpr double ALONE_PLAIN_OF = 0.15;
inline constexpr std::array<double, 3> ALONE_REACH{0.0015, 0.005, 0.015};
inline constexpr int ALONE_ROUNDS = 4;
inline constexpr double ALONE_SHADE = 0.03;
inline constexpr int ALONE_STEPS = 8;
inline constexpr double ALONE_SURE = 0.3;
inline constexpr std::array<double, 2> ALONE_THREE{0.4, 0.7};
inline constexpr int ALONE_WIDTH = 512;
inline constexpr double AROUND = 0.015;
inline constexpr int AT_A_TIME = 2;
inline constexpr double BALANCE = 0.12;
inline constexpr double BLOWN = 0.85;
inline constexpr int CELL = 4;
inline constexpr int EVEN_FEW = 50;
inline constexpr double EVEN_STRONG = 0.2;
inline constexpr int EVEN_WIDTH = 192;
inline constexpr double GLARE = 0.2;
inline constexpr std::array<double, 3> GLARE_ABOUT{0.03, 0.1, 0.4};
inline constexpr double GLARE_BLACK = 0.3;
inline constexpr double GLARE_COLOUR = 0.4;
inline constexpr double GLARE_DARK = 0.1;
inline constexpr double GLARE_DIFFER = 0.25;
inline constexpr double GLARE_FEATHER = 0.03;
inline constexpr double GLARE_LINES = 0.006;
inline constexpr double GLARE_NEAR = 0.006;
inline constexpr double GLARE_OUT = 0.006;
inline constexpr double GLARE_REACH = 0.01;
inline constexpr double GLARE_REACH_FAR = 0.1;
inline constexpr double GLARE_RIM = 0.012;
inline constexpr std::array<double, 2> GLARE_RIM_MORE{0.04, 0.1};
inline constexpr double GLARE_RIM_OVER = 0.003;
inline constexpr std::array<double, 2> GLARE_STEP{0.4, 0.045};
inline constexpr std::array<double, 2> GLARE_STRENGTH{0.4, 1.5};
inline constexpr double GRAIN_ABOUT = 0.006;
inline constexpr double GRAIN_FROM = 0.15;
inline constexpr double GRAIN_SURE = 0.4;
inline constexpr double HIDDEN = 0.06;
inline constexpr double HIDDEN_BESIDE = 0.01;
inline constexpr double HIDDEN_DARK = 0.15;
inline constexpr double HIDDEN_EASE = 0.04;
inline constexpr double HIDDEN_LIKE = 0.4;
inline constexpr double HIDDEN_MOST = 0.15;
inline constexpr double HIDDEN_SHOWN = 0.02;
inline constexpr int KEPT = 30;
inline constexpr double KEPT_EASE = 0.12;
inline constexpr std::array<double, 2> KEPT_EDGE{0.4, 0.8};
inline constexpr double KEPT_FIGURE = 0.05;
inline constexpr std::array<double, 2> KEPT_HELD{0.5, 0.9};
inline constexpr double KEPT_RIM = 0.04;
inline constexpr int LAYER_WIDTH = 256;
inline constexpr double LEAST = 0.01;
inline constexpr std::array<std::array<int, 2>, 4> LEVELS{{{8, 1500}, {4, 1000}, {2, 600}, {1, 300}}};
inline constexpr int MATCH_SIDE = 2400;
inline constexpr std::array<double, 2> MEND_ALL{0.2, 0.5};
inline constexpr std::array<double, 2> MEND_ALL_LIGHT{0.55, 0.8};
inline constexpr double MEND_COARSE = 0.025;
inline constexpr double MEND_DARK = 0.03;
inline constexpr std::array<double, 2> MEND_EDGE{0.06, 0.15};
inline constexpr double MEND_EDGE_ABOUT = 0.008;
inline constexpr double MEND_FAR = 0.045;
inline constexpr double MEND_FAR_SOFT = 0.02;
inline constexpr double MEND_FINE = 0.0018;
inline constexpr double MEND_FROM = 0.08;
inline constexpr double MEND_GROW = 0.008;
inline constexpr double MEND_NOISE = 0.02;
inline constexpr double MEND_OFF = 0.004;
inline constexpr std::array<double, 2> MEND_PLAIN{0.05, 0.15};
inline constexpr std::array<double, 4> MEND_REACH{0.008, 0.025, 0.08, 0.3};
inline constexpr std::array<double, 2> MEND_SHARP{0.06, 0.15};
inline constexpr double MEND_SHARP_ABOUT = 0.004;
inline constexpr double MEND_SOFT = 0.012;
inline constexpr double MEND_SURE = 0.5;
inline constexpr double MEND_TINT = 0.006;
inline constexpr double MEND_TO = 0.25;
inline constexpr int MIN_MATCHES = 40;
inline constexpr double MOST = 0.7;
inline constexpr double NOT_ONE = 0.085;
inline constexpr double NOT_ONE_EACH = 0.045;
inline constexpr double RIVAL = 0.25;
inline constexpr double RIVAL_FAR = 0.04;
inline constexpr int ROWS = 512;
inline constexpr std::array<double, 2> SETTLE_ABOUT{0.8, 3.0};
inline constexpr double SETTLE_FAR = 0.4;
inline constexpr std::array<double, 2> SETTLE_FINE{1.0, 0.005};
inline constexpr double SETTLE_MOST = 0.04;
inline constexpr std::array<double, 2> SETTLE_ODD{1.5, 0.5};
inline constexpr double SETTLE_SURE = 0.1;
inline constexpr std::array<int, 3> SETTLE_TILES{128, 128, 64};
inline constexpr double SPARE = 3.0;
inline constexpr std::array<double, 2> VEILED{0.1, 0.3};
inline constexpr double VEILED_FREE = 0.15;
inline constexpr double VEILED_GROW = 0.01;
inline constexpr std::array<double, 2> VEILED_HEAVY{0.5, 1.0};
inline constexpr double VEILED_HEAVY_GROW = 0.004;
inline constexpr double VEILED_MOST = 0.75;
inline constexpr std::array<double, 2> VEILED_PAINT{0.22, 0.32};
inline constexpr std::array<double, 2> VEILED_SHEEN{0.25, 0.5};
inline constexpr double VEILED_SHEEN_ABOUT = 0.02;
inline constexpr double VEILED_SOFT = 0.02;
inline constexpr std::array<double, 2> VEILED_STRONG{0.07, 0.12};
inline constexpr double VEIL_COST = 0.002;
inline constexpr double VEIL_MOST = 0.3;

}  // namespace frame::scan

namespace frame::crop {

inline constexpr double BAND = 0.012;
inline constexpr double FRAME_APART = 15.7;
inline constexpr double FRAME_CHROMA = 16.0;
inline constexpr int FRAME_EDGE = 5;
inline constexpr double HOLD = 0.004;
inline constexpr double INSET = 0.004;
inline constexpr double LEAST_KEPT = 0.15;
inline constexpr double LINE_SHARE = 0.6;
inline constexpr double MASK = 0.5;
inline constexpr double MOST_KEPT = 0.985;
inline constexpr double ON_LINE = 2.5;
inline constexpr double OUTER_SHARE = 0.5;
inline constexpr double PAINTING_SURE = 0.81;
inline constexpr int PHOTO_SIDE = 1024;
inline constexpr int PLATE = 2;
inline constexpr double PLATE_APART = 7.0;
inline constexpr double PLATE_BAND = 0.05;
inline constexpr double PLATE_BUSY = 0.1;
inline constexpr double PLATE_DENSE = 0.6;
inline constexpr double PLATE_EDGE = 0.015;
inline constexpr double PLATE_GAP = 0.15;
inline constexpr double PLATE_GRAIN = 2.5;
inline constexpr double PLATE_GRAIN_MOST = 4.0;
inline constexpr double PLATE_GROW = 0.012;
inline constexpr double PLATE_LEAST = 0.04;
inline constexpr double PLATE_LIGHT = 60.0;
inline constexpr double PLATE_LOOSE = 10.0;
inline constexpr double PLATE_LOOSE_GRAIN = 3.0;
inline constexpr double PLATE_MARGIN = 0.08;
inline constexpr double PLATE_NEAR = 0.1;
inline constexpr double PLATE_OVER = 0.15;
inline constexpr double PLATE_PART = 0.0002;
inline constexpr double PLATE_REACH = 0.18;
inline constexpr double PLATE_SAME = 0.85;
inline constexpr int PLATE_SIDE = 900;
inline constexpr double PLATE_SIDES = 20.0;
inline constexpr double PLATE_SPARSE = 0.6;
inline constexpr double PLATE_SPREAD = 7.412999999999999;
inline constexpr double PLATE_STRAY = 0.001;
inline constexpr double PLATE_THIN = 0.35;
inline constexpr double PLATE_TURN = 5.0;
inline constexpr double PLATE_TURN_GAIN = 0.98;
inline constexpr double PLATE_TURN_LEAST = 0.3;
inline constexpr double PLATE_WHOLE = 0.8;
inline constexpr int SAMPLES = 160;
inline constexpr int SIDE = 384;
inline constexpr int SNAP_SIDE = 1500;
inline constexpr double SQUARE = 16.0;
inline constexpr double STRENGTH = 25.0;
inline constexpr double SURE = 0.795;
inline constexpr double UPRIGHT = 3.0;
inline constexpr double WHOLE = 0.1;

}  // namespace frame::crop

namespace frame::restore {

inline constexpr double BLOCKS = 0.006;
inline constexpr double COARSEST = 12.0;
inline constexpr double COLOUR_SIGMA = 2.0;
inline constexpr double DRAWN = 0.7;
inline constexpr int FEWEST = 4;
inline constexpr double FINEST = 2.2;
inline constexpr double GRAIN_SIGMA = 1.0;
inline constexpr int HARMONICS = 6;
inline constexpr double LAID_MATCH = 0.85;
inline constexpr double LAID_SHIFT = 0.06;
inline constexpr int LAID_SIDE = 800;
inline constexpr int LEFT_FEWEST = 2;
inline constexpr double LEFT_STANDS = 2.5;
inline constexpr int LONGEST = 2048;
inline constexpr int LOOKED = 1024;
inline constexpr int MOST = 16;
inline constexpr double NEAREST = 5.0;
inline constexpr double NOTCH = 0.15;
inline constexpr double PAD = 0.04;
inline constexpr double SHARPEN = 0.3;
inline constexpr double SHARPEN_SPAN = 0.9;
inline constexpr double SKEW_FIXED = 0.005;
inline constexpr double SKEW_MAX = 0.04;
inline constexpr int SMALL = 1000;
inline constexpr double SOFT = 0.42;
inline constexpr double STANDS = 3.0;

}  // namespace frame::restore
