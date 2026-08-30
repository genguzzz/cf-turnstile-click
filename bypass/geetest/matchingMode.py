"""Greedy matching + image IO helpers (inherited from MgArcher/Text_select_captcha src/utils/matchingMode.py)."""

# !/usr/bin/env python
# -*-coding:utf-8 -*-
# Author: yujia (MgArcher/Text_select_captcha)
# version: python 3.6

from typing import List, Tuple

import cv2
import numpy as np


def find_overall_index_fast(matrix: List[List[float]]) -> List[Tuple[int, int]]:
    """Greedy global-optimum matching over a similarity matrix."""
    if not matrix:
        return []

    mat = np.array(matrix, dtype=np.float64)
    n_rows, n_cols = mat.shape
    k = min(n_rows, n_cols)
    index = []
    for _ in range(k):
        flat_idx = np.argmax(mat)
        row, col = divmod(flat_idx, n_cols)
        index.append((row, col))
        mat[row, :] = -np.inf
        mat[:, col] = -np.inf
    index.sort(key=lambda x: x[0])
    return index


def open_image(file, flags=cv2.IMREAD_COLOR):
    """Read an image with OpenCV, supporting paths, numpy arrays and bytes."""
    if isinstance(file, np.ndarray):
        return file
    elif isinstance(file, bytes):
        data = np.frombuffer(file, dtype=np.uint8)
        return cv2.imdecode(data, flags)
    else:
        path = str(file)
        with open(path, "rb") as f:
            data = np.frombuffer(f.read(), dtype=np.uint8)
        return cv2.imdecode(data, flags)