"""MobileCLIP image + text encoder (Apple ML Research).

MobileCLIP-S0/S2 matches OpenCLIP ViT-B/16 zero-shot accuracy at 3–5× the speed on
Jetson-class hardware. License is `apple-amlr` — research use OK; flag for any
commercial product deployment.

Loads via HuggingFace `timm` + `open_clip` hybrid path; the `mobileclip` pip
package is also supported if present.
"""

from __future__ import annotations

import time

import numpy as np

from .base import EncoderBackend, EncoderOutput
from .trt_image_encoder import _TrtImageEncoder

_MODEL_SPECS: dict[str, tuple[str, str, int]] = {
    # key → (open_clip arch, pretrained tag, embedding_dim)
    "mobileclip_s0": ("MobileCLIP-S0", "datacompdr", 512),
    "mobileclip_s1": ("MobileCLIP-S1", "datacompdr", 512),
    "mobileclip_s2": ("MobileCLIP-S2", "datacompdr", 512),
    "mobileclip_b": ("MobileCLIP-B", "datacompdr", 512),
    "mobileclip2_s0": ("MobileCLIP2-S0", "dfndr2b", 512),
    "mobileclip2_s2": ("MobileCLIP2-S2", "dfndr2b", 512),
    "mobileclip2_b":  ("MobileCLIP2-B",  "dfndr2b", 512),
}


class MobileClipEncoder(EncoderBackend):
    def __init__(self, name: str):
        if name not in _MODEL_SPECS:
            raise ValueError(f"Unknown MobileCLIP model: {name}")
        self.name = name
        self._arch, self._pretrained, self.embedding_dim = _MODEL_SPECS[name]
        self._model = None
        self._preprocess = None
        self._tokenizer = None
        self._device: str | None = None

    def _infer_image_size(self) -> int:
        """从 OpenCLIP 模型配置中推断输入图像尺寸，失败时回退到 256。"""
        try:
            # OpenCLIP 的视觉塔通常有 image_size 属性
            visual = getattr(self._model, "visual", None)
            if visual is not None and hasattr(visual, "image_size"):
                size = visual.image_size
                # image_size 可能是 int 或 (H, W)
                return size if isinstance(size, int) else int(size[0])
            # 部分版本存在 model.image_size
            size = getattr(self._model, "image_size", None)
            if size is not None:
                return size if isinstance(size, int) else int(size[0])
        except Exception:
            pass
        return 256

    def load(self, device: str) -> None:
        import os
        from pathlib import Path
        import open_clip, torch 

        model, _, preprocess = open_clip.create_model_and_transforms(self._arch, pretrained=self._pretrained)
        try:
            from timm.utils import reparameterize_model
            model = reparameterize_model(model)
        except ImportError:
            pass
        model.to(device).eval()   # ← 移到 reparameterize 之后

        self._model = model                 # text 塔继续用
        self._preprocess = preprocess
        self._tokenizer = open_clip.get_tokenizer(self._arch)
        self._device = device

        # ---- 图像塔：TRT engine 查找（文件名由模型名派生，不再硬编码） ----
        self._trt = None
        engine_name = f"{self.name}_img.engine"   # 例如 mobileclip2_s2_img.engine
        for base in (os.environ.get("GO2_MODEL_DIR"), str(Path.cwd() / "models")):
            if not base:
                continue
            engine_path = Path(base) / engine_name
            if engine_path.is_file():
                self._trt = _TrtImageEncoder(str(engine_path), device)
                break

        # ---- 预热：图像尺寸从模型自身读取，避免硬编码 ----
        with torch.no_grad():
            _ = self._model.encode_text(self._tokenizer(["warmup"]).to(device))
            if self._trt is None:
                image_size = self._infer_image_size()
                dummy = torch.zeros((1, 3, image_size, image_size), device=device)
                _ = self._model.encode_image(dummy)

    def encode_images(
        self,
        image_bgr: np.ndarray,
        boxes_xyxy: np.ndarray,
        masks: np.ndarray | None,
    ) -> EncoderOutput:
        import torch
        from PIL import Image

        if self._model is None:
            raise RuntimeError(f"{self.name}: load() must be called before encode_images()")
        start_ns = time.perf_counter_ns()

        n = int(boxes_xyxy.shape[0])
        if n == 0:
            return EncoderOutput(
                image_embeddings=np.zeros((0, self.embedding_dim), dtype=np.float32),
                latency_ms=(time.perf_counter_ns() - start_ns) / 1e6,
            )

        image_rgb = image_bgr[:, :, ::-1]
        pil_crops = []
        for i in range(n):
            x1, y1, x2, y2 = boxes_xyxy[i].astype(int)
            x1, y1 = max(0, x1), max(0, y1)
            x2 = min(image_rgb.shape[1], x2)
            y2 = min(image_rgb.shape[0], y2)
            if x2 <= x1 or y2 <= y1:
                crop = np.zeros((1, 1, 3), dtype=np.uint8)
            else:
                crop = image_rgb[y1:y2, x1:x2].copy()
                if masks is not None and masks.shape[0] > i:
                    mask = masks[i, y1:y2, x1:x2]
                    if mask.shape == crop.shape[:2]:
                        crop = crop * mask[..., None]
            pil_crops.append(Image.fromarray(crop))

        batch = torch.stack([self._preprocess(c) for c in pil_crops]).to(self._device)
        with torch.no_grad():
            if self._trt is not None:
                feats = self._trt.infer(batch)          # engine 内已含 L2 归一化
                feats = feats.float()
            else:
                feats = self._model.encode_image(batch)
                feats = feats / feats.norm(dim=-1, keepdim=True).clamp_min(1e-6)
        return EncoderOutput(
            image_embeddings=feats.detach().cpu().numpy().astype(np.float32),
            latency_ms=(time.perf_counter_ns() - start_ns) / 1e6,
        )

    def encode_text(self, texts: list[str]) -> np.ndarray:
        import torch

        if self._model is None or self._tokenizer is None:
            raise RuntimeError(f"{self.name}: load() must be called before encode_text()")
        if not texts:
            return np.zeros((0, self.embedding_dim), dtype=np.float32)
        tokens = self._tokenizer(texts).to(self._device)
        with torch.no_grad():
            feats = self._model.encode_text(tokens)
            feats = feats / feats.norm(dim=-1, keepdim=True).clamp_min(1e-6)
        return feats.detach().cpu().numpy().astype(np.float32)
