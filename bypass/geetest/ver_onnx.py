"""Siamese network ONNX inference (inherited from MgArcher/Text_select_captcha src/utils/ver_onnx.py)."""

# !/usr/bin/env python
# -*-coding:utf-8 -*-
# Author: yujia (MgArcher/Text_select_captcha)
# version: python 3.6

from typing import List

import cv2
import numpy as np
import onnxruntime as ort


def cvtColor(image_np):
    """Ensure image is 3-channel RGB."""
    if len(image_np.shape) == 3 and image_np.shape[2] == 3:
        return cv2.cvtColor(image_np, cv2.COLOR_BGR2RGB)
    elif len(image_np.shape) == 3 and image_np.shape[2] == 4:
        bgr = cv2.cvtColor(image_np, cv2.COLOR_BGRA2BGR)
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    else:
        return cv2.cvtColor(image_np, cv2.COLOR_GRAY2RGB)


def letterbox_image(image_np, target_size):
    h, w = target_size
    ih, iw = image_np.shape[:2]
    scale = min(w / iw, h / ih)
    nw = int(iw * scale)
    nh = int(ih * scale)
    resized = cv2.resize(image_np, (nw, nh), interpolation=cv2.INTER_CUBIC)
    new_image = np.full((h, w, 3), 128, dtype=np.uint8)
    dx = (w - nw) // 2
    dy = (h - nh) // 2
    new_image[dy:dy + nh, dx:dx + nw] = resized
    return new_image


def preprocess_input(x):
    return x.astype(np.float32) / 255.0


def preprocess_image(img: np.ndarray, input_size=(112, 112)) -> np.ndarray:
    """Preprocess an image into a [1, 3, H, W] array."""
    img = cvtColor(img)
    img = letterbox_image(img, input_size)
    img = preprocess_input(img)
    img = np.transpose(img, (2, 0, 1)).astype(np.float32)
    return np.expand_dims(img, axis=0)


class PreONNX:
    def __init__(self, onnx_path: str, device: str = "cpu", input_size=(112, 112)):
        self.input_size = input_size

        providers = ["CPUExecutionProvider"]
        if device == "cuda":
            providers.insert(0, "CUDAExecutionProvider")

        self.session = ort.InferenceSession(onnx_path, providers=providers)
        self.input_names = [inp.name for inp in self.session.get_inputs()]
        self.output_names = [out.name for out in self.session.get_outputs()]

    def predict_pair(self, img1: np.ndarray, img2: np.ndarray) -> float:
        """Compare two images, return similarity probability (0~1)."""
        img1 = preprocess_image(img1, self.input_size)
        img2 = preprocess_image(img2, self.input_size)

        ort_inputs = {
            self.input_names[0]: img1,
            self.input_names[1]: img2,
        }
        logits = self.session.run(self.output_names, ort_inputs)[0]  # [1, 1]
        prob = 1.0 / (1.0 + np.exp(-logits))
        return float(prob[0, 0])

    def _reason_all_batch(self, img1_paths: list, img2_paths: list) -> np.ndarray:
        """Batch-predict pairs (requires dynamic batch support)."""
        imgs1 = np.vstack([preprocess_image(p, self.input_size) for p in img1_paths])
        imgs2 = np.vstack([preprocess_image(p, self.input_size) for p in img2_paths])

        ort_inputs = {
            self.input_names[0]: imgs1,
            self.input_names[1]: imgs2,
        }
        logits = self.session.run(self.output_names, ort_inputs)[0]
        probs = 1.0 / (1.0 + np.exp(-logits))
        return probs.flatten()

    def reason_all_batch(self, image_1_list: list, image_2_list: list) -> list:
        """Compute all-pair similarity scores between two lists of images.

        :param image_1_list: prompt char crops (length N)
        :param image_2_list: picture char crops (length M)
        :return: scores[N][M] where scores[i][j] = similarity between image_1[i] and image_2[j]
        """
        N = len(image_1_list)
        M = len(image_2_list)
        processed_1 = [preprocess_image(img) for img in image_1_list]
        processed_2 = [preprocess_image(img) for img in image_2_list]
        x1_list = []
        x2_list = []
        for p1 in processed_1:
            x1_list.extend([p1] * M)
            x2_list.extend(processed_2)
        x1_batch = np.concatenate(x1_list, axis=0)
        x2_batch = np.concatenate(x2_list, axis=0)
        ort_inputs = {self.input_names[0]: x1_batch, self.input_names[1]: x2_batch}
        logits = self.session.run(self.output_names, ort_inputs)[0]
        probs = 1.0 / (1.0 + np.exp(-logits))
        probs = probs.flatten().tolist()
        scores = [probs[i * M:(i + 1) * M] for i in range(N)]
        return scores