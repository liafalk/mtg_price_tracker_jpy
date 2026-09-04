# Card detector training

This directory contains the training scaffold for a card-segmentation model.
The model should learn the visible card outline, then OpenCV can use that
outline for perspective correction before OCR.

## Dataset layout

Put source images and YOLO segmentation labels here:

```text
ml/
  dataset.yaml
  images/
    train/
    val/
    test/
  labels/
    train/
    val/
    test/
```

Each image needs a matching `.txt` label. A label contains one line:

```text
0 x1 y1 x2 y2 x3 y3 x4 y4
```

The first value is the class (`0` means `card`); every coordinate is normalized
from `0` to `1` relative to the image width or height. List the four visible
card corners clockwise. For partially occluded cards, label the best estimate
of the complete card boundary only when the hidden edge can be inferred;
otherwise use the visible polygon and keep that image in the test set.

Use a labeling tool that exports YOLO segmentation format, such as CVAT,
Label Studio, or Roboflow. Keep the current files in `../test/` as evaluation
fixtures and do not copy them into training until the dataset is larger.

## Recommended dataset

Start with 50-100 labeled photos and reserve 15-20% for validation and test.
Include different card sets, languages, angles, distances, lighting, hands,
backgrounds, glare, and partial occlusion. More variation matters more than
many nearly identical photos.

## Train

From the repository root:

```bash
python -m venv .venv-card-detector
. .venv-card-detector/bin/activate
pip install ultralytics
yolo segment train \
  model=yolo11n-seg.pt \
  data=scanner/ml/dataset.yaml \
  epochs=100 \
  imgsz=640 \
  project=scanner/ml/runs \
  name=card-segmentation
```

Review the validation images and metrics before exporting. For browser use,
export the best checkpoint to ONNX:

```bash
yolo export \
  model=scanner/ml/runs/card-segmentation/weights/best.pt \
  format=onnx \
  imgsz=640 \
  simplify=True
```

The browser integration should load the resulting ONNX model with ONNX
Runtime Web, convert its card mask to a four-corner polygon, and then reuse
`detectCardAndRectify`/the existing OCR pipeline. Do not commit model runs or
large model files until the model has been evaluated against the held-out
test images.