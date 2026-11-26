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

`artsr-g3.onnx`: the restorer's own model, ArtSR G3 (`imaging/artsr.py`;
sha256 `de140408da2e9a9955a66f35c4c81921d2c7628a89dc92d3c487357ea8a9142c`).
Its base is LocalSR Photo M by Hermes Reisner (HerRei),
[github.com/HerRei/localsr-models](https://github.com/HerRei/localsr-models),
licensed CC BY 4.0. Modified: a FiLM layer added (led by a work's SigLIP 2
vector and its kind) and trained further on some 12,000 public-domain
museum works (NGA, SMK, Art Institute of Chicago, Smithsonian, Yale and
others). The fine-tune is a derivative of the base and carries the same
licence and attribution: CC BY 4.0,
[creativecommons.org/licenses/by/4.0](https://creativecommons.org/licenses/by/4.0/).
