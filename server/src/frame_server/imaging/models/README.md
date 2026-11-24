# Models

`face_detection_yunet_2023mar.onnx`: YuNet face detector from
[opencv_zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet)
(sha256 `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`),
used through `cv2.FaceDetectorYN` to keep faces in automatic crops.

MIT License, Copyright (c) 2020 Shiqi Yu.

`kadr-11s.onnx`, `kadr-10p.onnx`: the museum photographs' crop models, the
app's `ios/Models/Kadr.mlpackage` and `KadrPainting.mlpackage` (trained on
the Mac) exported to ONNX with the same weights (float16, used as float32)
for the server's night (`crop_night.py`). Each names its model in its
metadata (`model`), held to `crop_model.MODEL` and `PAINTING_MODEL`: a new
model comes on both sides at once.
