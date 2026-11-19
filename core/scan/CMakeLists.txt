# The scan's core for Linux: the library, and the tools that check it
# against the server's Python (tools/). The phone's is built by
# ios/scripts/build-scan.sh.
cmake_minimum_required(VERSION 3.20)
project(frame_scan CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()
# OpenCV 5.0.0 built static with core, imgproc, flann, geometry, features only.
set(OPENCV_ROOT "" CACHE PATH "Where that OpenCV is installed")
if(EXISTS ${OPENCV_ROOT}/include/opencv5)
  set(OPENCV_INCLUDE ${OPENCV_ROOT}/include/opencv5)
else()
  set(OPENCV_INCLUDE ${OPENCV_ROOT}/include)
endif()
file(GLOB OPENCV_3RDPARTY ${OPENCV_ROOT}/lib/opencv5/3rdparty/*.a ${OPENCV_ROOT}/lib/3rdparty/*.a)
add_library(opencv INTERFACE)
target_include_directories(opencv INTERFACE ${OPENCV_INCLUDE})
target_link_libraries(opencv INTERFACE
  ${OPENCV_ROOT}/lib/libopencv_features.a ${OPENCV_ROOT}/lib/libopencv_geometry.a
  ${OPENCV_ROOT}/lib/libopencv_flann.a ${OPENCV_ROOT}/lib/libopencv_imgproc.a
  ${OPENCV_ROOT}/lib/libopencv_core.a ${OPENCV_3RDPARTY} pthread dl m)
# Its own zlib where OpenCV was built with one, else the system's.
if(NOT OPENCV_3RDPARTY MATCHES "zlib")
  target_link_libraries(opencv INTERFACE z)
endif()
# No contraction of a*b+c into one step: the sums come out as NumPy's do.
add_compile_options(-O2 -ffp-contract=off -Wall -Wextra)
file(GLOB SCAN_SOURCES src/scan_*.cpp src/frame_scan.cpp)
add_library(scan STATIC ${SCAN_SOURCES})
target_include_directories(scan PUBLIC include)
target_link_libraries(scan PUBLIC opencv)
foreach(tool check merge made_up)
  add_executable(${tool} tools/${tool}.cpp)
  target_link_libraries(${tool} PRIVATE scan)
endforeach()
