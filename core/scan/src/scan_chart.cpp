// A photograph put in the colours a chart gives it: the server's
// `colorchecker._put`, by the tables its `colorchecker.tables` writes. The
// phone does this to its own photographs before it makes the scan of them:
// the server did it to its copies when the chart was read.
#include "scan.hpp"

#include <opencv2/core/utility.hpp>

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iterator>
#include <stdexcept>

namespace frame::scan {

namespace {

// `colorchecker.TABLES`.
const char HEAD[] = "FRAMECH1";
const size_t LIGHTS = 65536;

template <typename T>
void take(const std::vector<char>& from, size_t& at, T* into, size_t count) {
    std::memcpy(into, from.data() + at, count * sizeof(T));
    at += count * sizeof(T);
}

}  // namespace

Chart Chart::read(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("chart: no " + path);
    std::vector<char> all((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    const size_t head = sizeof(HEAD) - 1;
    const size_t whole = head + sizeof(float) * (3 * 256 + 256 + 9) + sizeof(uint32_t) + sizeof(double) * 3 + LIGHTS;
    if (all.size() != whole || std::memcmp(all.data(), HEAD, head) != 0)
        throw std::runtime_error("chart: not the tables this core knows");
    Chart chart;
    size_t at = head;
    take(all, at, &chart.curves[0][0], 3 * 256);
    take(all, at, chart.linear, 256);
    take(all, at, &chart.matrix[0][0], 9);
    uint32_t top = 0;
    take(all, at, &top, 1);
    chart.top = top != 0;
    take(all, at, chart.start, 3);
    chart.lit.resize(LIGHTS);
    take(all, at, chart.lit.data(), LIGHTS);
    return chart;
}

void put(cv::Mat& photo, const Chart& chart) {
    if (photo.type() != CV_8UC3) throw std::runtime_error("chart: the photograph is not rows × columns × 3 of 8 bits");
    if (chart.lit.size() != LIGHTS) throw std::runtime_error("chart: no tables");
    // As NumPy has them beside float32: the start and what is left above it.
    float start[3], above[3];
    for (int c = 0; c < 3; c++) {
        start[c] = static_cast<float>(chart.start[c]);
        above[c] = static_cast<float>(std::max(1.0 - chart.start[c], 1e-6));
    }
    const auto& m = chart.matrix;
    const uint8_t* lit = chart.lit.data();
    cv::parallel_for_(cv::Range(0, photo.rows), [&](const cv::Range& rows) {
        for (int y = rows.start; y < rows.end; y++) {
            uint8_t* p = photo.ptr<uint8_t>(y);
            for (int x = 0; x < photo.cols; x++, p += 3) {
                float light[3] = {chart.curves[0][p[0]], chart.curves[1][p[1]], chart.curves[2][p[2]]};
                if (chart.top) {
                    // `_at_top`: past the lightest grey the curves have, a
                    // channel is at least as light as the lighter of the
                    // other two say, the more so the nearer the top.
                    float lifted[3];
                    for (int c = 0; c < 3; c++) {
                        float near = (chart.linear[p[c]] - start[c]) / above[c];
                        near = std::min(std::max(near, 0.f), 1.f);
                        float others = std::max(light[(c + 1) % 3], light[(c + 2) % 3]);
                        lifted[c] = light[c] + near * std::max(others - light[c], 0.f);
                    }
                    std::memcpy(light, lifted, sizeof(light));
                }
                for (int c = 0; c < 3; c++) {
                    // One sum after another, nothing fused: the same on
                    // every processor (the server's OpenCV fuses where it
                    // can, and is a level off this in one value of 100 000).
                    float sum = m[c][0] * light[0] + m[c][1] * light[1];
                    sum = sum + m[c][2] * light[2];
                    sum = std::min(std::max(sum, 0.f), 1.f);
                    p[c] = lit[static_cast<uint16_t>(sum * 65535.f + 0.5f)];
                }
            }
        }
    });
}

}  // namespace frame::scan
