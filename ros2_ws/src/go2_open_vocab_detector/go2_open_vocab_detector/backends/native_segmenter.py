from .base import SegmenterBackend, SegmenterOutput

class NativeSegmenter(SegmenterBackend):
    """Masks come from the detector's own seg head (YOLOE-seg); nothing to do here."""
    name = "native"
    def load(self, device: str) -> None: ...
    def segment(self, image_bgr, boxes_xyxy):
        raise RuntimeError("native segmenter: masks must be supplied by the detector")