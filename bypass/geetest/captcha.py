"""TextSelectCaptcha recognizer (inherited from MgArcher/Text_select_captcha).

This is a faithful port of `src/captcha.py` from the upstream repo. Kept as
close to upstream as possible so the recognition behaviour matches the
reported ~96% accuracy.
"""

# !/usr/bin/env python
# -*-coding:utf-8 -*-
# Author: yujia (MgArcher/Text_select_captcha)
# version: python 3.6

from typing import Any, Dict, List, Tuple

from . import matchingMode, ver_onnx, yolo_onnx


class TextSelectCaptcha(object):
    def __init__(
        self,
        per_path: str = "pre_model_v7.onnx",
        yolo_path: str = "best_v3.onnx",
        model_dir: str | None = None,
    ) -> None:
        """Load the YOLO + Siamese ONNX models.

        Args:
            per_path: character-matching model filename (PreONNX).
            yolo_path: YOLO detector model filename.
            model_dir: absolute path to the model directory. When None, the
                default `model/` folder next to this package is used.
        """
        import os

        if model_dir is None:
            model_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "model")
        path = lambda a, b: os.path.join(a, b)
        per_path = path(model_dir, per_path)
        yolo_path = path(model_dir, yolo_path)
        self.yolo = yolo_onnx.YOLO(yolo_path)
        self.pre = ver_onnx.PreONNX(per_path)

    def detection(self, image_path: str) -> List[List[float]]:
        img = matchingMode.open_image(image_path)
        data = self.yolo.inference(img)
        return data

    def run(self, image_path: str) -> List[List[float]]:
        img = matchingMode.open_image(image_path)
        data = self.yolo.inference(img)
        target_boxes = [item[:4] for item in data if len(item) >= 6 and item[5] == 0]
        char_boxes = [item[:4] for item in data if len(item) >= 6 and item[5] == 2]
        char_boxes.sort(key=lambda box: box[0])
        img_targets = [img[int(box[1]):int(box[3]), int(box[0]):int(box[2])] for box in target_boxes]
        chars = [img[int(box[1]):int(box[3]), int(box[0]):int(box[2])] for box in char_boxes]
        slys = self.pre.reason_all_batch(chars, img_targets)
        sorted_result = matchingMode.find_overall_index_fast(slys)
        result = [target_boxes[j] for i, j in sorted_result]
        return result

    def run_dict(self, image_path: str) -> Dict[str, Any]:
        img = matchingMode.open_image(image_path)
        h, w, _ = img.shape
        result = self.run(image_path)
        return {
            "imgW": w,
            "imgH": h,
            "point": [{"x_rel": (x1 + x2) / 2, "y_rel": (y1 + y2) / 2} for x1, y1, x2, y2 in result],
            "corp": [{"x1": x1, "y1": y1, "x2": x2, "y2": y2} for x1, y1, x2, y2 in result],
        }