// NumPy's .npy files read into and written from cv::Mat: what the Python
// merge worked out at each step is checked against this way.
#pragma once

#include <opencv2/core.hpp>

#include <cstdint>
#include <cstring>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace npy {

struct Array {
    std::vector<int> shape;
    int depth = CV_8U;  // CV_8U, CV_32S, CV_32F, CV_64F (bool is CV_8U)
    std::vector<uint8_t> data;

    size_t count() const {
        size_t n = 1;
        for (int s : shape) n *= static_cast<size_t>(s);
        return n;
    }

    // H × W (× C): the last of three axes is the channels.
    cv::Mat mat() const {
        if (shape.empty()) return cv::Mat(1, 1, CV_MAKETYPE(depth, 1), const_cast<uint8_t*>(data.data())).clone();
        if (shape.size() == 1) return cv::Mat(shape[0], 1, CV_MAKETYPE(depth, 1), const_cast<uint8_t*>(data.data())).clone();
        if (shape.size() == 2) return cv::Mat(shape[0], shape[1], CV_MAKETYPE(depth, 1), const_cast<uint8_t*>(data.data())).clone();
        if (shape.size() == 3) return cv::Mat(shape[0], shape[1], CV_MAKETYPE(depth, shape[2]), const_cast<uint8_t*>(data.data())).clone();
        throw std::runtime_error("npy: more than three axes are no one picture");
    }

    // N × H × W (× C): one picture each.
    std::vector<cv::Mat> mats() const {
        if (shape.size() < 3) throw std::runtime_error("npy: no pictures");
        int channels = shape.size() == 4 ? shape[3] : 1;
        size_t each = static_cast<size_t>(shape[1]) * shape[2] * channels * CV_ELEM_SIZE1(depth);
        std::vector<cv::Mat> out;
        for (int n = 0; n < shape[0]; n++)
            out.push_back(cv::Mat(shape[1], shape[2], CV_MAKETYPE(depth, channels),
                                  const_cast<uint8_t*>(data.data() + n * each)).clone());
        return out;
    }
};

inline Array load(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("npy: no " + path);
    char magic[6];
    in.read(magic, 6);
    if (std::memcmp(magic, "\x93NUMPY", 6) != 0) throw std::runtime_error("npy: not one: " + path);
    uint8_t version[2];
    in.read(reinterpret_cast<char*>(version), 2);
    uint32_t length = 0;
    if (version[0] == 1) {
        uint16_t l;
        in.read(reinterpret_cast<char*>(&l), 2);
        length = l;
    } else {
        in.read(reinterpret_cast<char*>(&length), 4);
    }
    std::string header(length, ' ');
    in.read(header.data(), length);
    Array out;
    auto at = header.find("'descr':");
    auto from = header.find('\'', at + 8) + 1;
    std::string descr = header.substr(from, header.find('\'', from) - from);
    if (descr == "|u1" || descr == "|b1") out.depth = CV_8U;
    else if (descr == "<i4") out.depth = CV_32S;
    else if (descr == "<f4") out.depth = CV_32F;
    else if (descr == "<f8") out.depth = CV_64F;
    else throw std::runtime_error("npy: " + descr + " in " + path);
    if (header.find("'fortran_order': False") == std::string::npos)
        throw std::runtime_error("npy: fortran order in " + path);
    from = header.find('(', header.find("'shape':")) + 1;
    std::string shape = header.substr(from, header.find(')', from) - from);
    size_t pos = 0;
    while (pos < shape.size()) {
        while (pos < shape.size() && (shape[pos] == ' ' || shape[pos] == ',')) pos++;
        if (pos >= shape.size()) break;
        size_t used = 0;
        out.shape.push_back(std::stoi(shape.substr(pos), &used));
        pos += used;
    }
    out.data.resize(out.count() * CV_ELEM_SIZE1(out.depth));
    in.read(reinterpret_cast<char*>(out.data.data()), static_cast<std::streamsize>(out.data.size()));
    if (!in) throw std::runtime_error("npy: cut short: " + path);
    return out;
}

inline void save(const std::string& path, const cv::Mat& given) {
    cv::Mat mat = given.isContinuous() ? given : given.clone();
    const char* descr = nullptr;
    switch (mat.depth()) {
        case CV_8U: descr = "|u1"; break;
        case CV_32S: descr = "<i4"; break;
        case CV_32F: descr = "<f4"; break;
        case CV_64F: descr = "<f8"; break;
        default: throw std::runtime_error("npy: this depth is not written");
    }
    std::string shape = std::to_string(mat.rows) + ", " + std::to_string(mat.cols);
    if (mat.channels() > 1) shape += ", " + std::to_string(mat.channels());
    std::string header = std::string("{'descr': '") + descr + "', 'fortran_order': False, 'shape': (" + shape + "), }";
    size_t total = 10 + header.size() + 1;
    header += std::string((64 - total % 64) % 64, ' ') + "\n";
    std::ofstream out(path, std::ios::binary);
    out.write("\x93NUMPY\x01\x00", 8);
    uint16_t length = static_cast<uint16_t>(header.size());
    out.write(reinterpret_cast<const char*>(&length), 2);
    out.write(header.data(), static_cast<std::streamsize>(header.size()));
    out.write(reinterpret_cast<const char*>(mat.data), static_cast<std::streamsize>(mat.total() * mat.elemSize()));
}

}  // namespace npy
