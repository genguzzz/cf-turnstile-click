"""Geetest v3 word-click (文字点选) captcha recognition.

Recognition is NOT OCR. This package inherits the algorithm and model-loading
code from the open-source project MgArcher/Text_select_captcha:

  https://github.com/MgArcher/Text_select_captcha

Pipeline:
  1. YOLO object detector (best_v3.onnx) locates the prompt characters
     (class=0) and the characters inside the picture (class=2).
  2. Siamese network (pre_model_v7.onnx) computes the similarity matrix
     between every picture char and every prompt char.
  3. Greedy matching (find_overall_index_fast) assigns each prompt char to
     its most similar picture char.
  4. Click points are emitted in prompt order, as absolute pixel coordinates
     in the ORIGINAL image space.

The vendored implementation lives under `bypass/geetest/` so the plugin does
not depend on a checkout of the upstream repo at runtime.
"""

from .captcha import TextSelectCaptcha

__all__ = ["TextSelectCaptcha"]