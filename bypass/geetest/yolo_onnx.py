"""YOLO ONNX inference (inherited from MgArcher/Text_select_captcha src/utils/yolo_onnx.py)."""

# !/usr/bin/env python
# -*-coding:utf-8 -*-
# Author: yujia (MgArcher/Text_select_captcha)
# version: python 3.6

from typing import List, Tuple, Union

import cv2
import numpy as np
import onnxruntime as ort


class YOLO:
    def __init__(self, model_path: str, conf_threshold: float = 0.3) -> None:
        """Initialize YOLO ONNX model."""
        self.session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self.conf_threshold = conf_threshold

        self.input_name = self.session.get_inputs()[0].name
        self.input_shape = self.session.get_inputs()[0].shape  # [1, 3, 640, 640]
        self.output_name = self.session.get_outputs()[0].name

    def letterbox(
        self, image: np.ndarray, target_size: Tuple[int, int] = (640, 640)
    ) -> Tuple[np.ndarray, float, Tuple[int, int, int, int]]:
        """Resize with aspect ratio preserved and pad (letterbox)."""
        img_h, img_w = image.shape[:2]
        target_w, target_h = target_size

        scale = min(target_w / img_w, target_h / img_h)
        new_w, new_h = int(img_w * scale), int(img_h * scale)

        resized_img = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        canvas = np.full((target_h, target_w, 3), 114, dtype=np.uint8)
        dw, dh = (target_w - new_w) // 2, (target_h - new_h) // 2
        canvas[dh:dh + new_h, dw:dw + new_w, :] = resized_img

        return canvas, scale, (dw, dh, new_w, new_h)

    def preprocess(self, image: np.ndarray) -> Tuple[np.ndarray, float, Tuple[int, int, int, int]]:
        """BGR->RGB, letterbox, normalize to [0,1], HWC->NCHW."""
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        padded_img, scale, pad_info = self.letterbox(
            image_rgb, target_size=(self.input_shape[3], self.input_shape[2])
        )
        padded_img = padded_img.astype(np.float32) / 255.0
        input_tensor = np.transpose(padded_img, (2, 0, 1))  # CHW
        input_tensor = np.expand_dims(input_tensor, axis=0)  # NCHW
        return input_tensor, scale, pad_info

    def inference(self, image: np.ndarray) -> List[List[Union[int, float]]]:
        """Run inference and map detections back to original image space.

        Returns a list of [x1, y1, x2, y2, conf, class_id].
        """
        input_tensor, scale, (dw, dh, new_w, new_h) = self.preprocess(image)
        outputs = self.session.run([self.output_name], {self.input_name: input_tensor})[0]

        detections = []
        for detection in outputs[0]:
            x1, y1, x2, y2, conf, class_id = detection.tolist()
            if conf < self.conf_threshold:
                continue

            x1 = max(0, (x1 - dw) / scale)
            y1 = max(0, (y1 - dh) / scale)
            x2 = min(image.shape[1], (x2 - dw) / scale)
            y2 = min(image.shape[0], (y2 - dh) / scale)

            detections.append([int(x1), int(y1), int(x2), int(y2), conf, int(class_id)])

        return detections