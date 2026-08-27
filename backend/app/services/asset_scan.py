"""Asset Scan pipeline: decode a barcode from an uploaded frame, and — only
when no barcode decodes — run a cheap YOLO presence check to give a more
useful error message.

Design note (see docs/asset-scan-plan.md, Decision B): a pretrained YOLOv8n
has no "barcode" class (it's COCO-trained), so it cannot literally localize a
barcode region. pyzbar/zbar does the actual decoding and localization on its
own — it doesn't need an upstream object detector. YOLO's role here is
intentionally limited to a presence gate: "was anything at all in frame,"
used only to make the NO_BARCODE_DETECTED message more useful, never to
produce a fabricated "confidence" on a successful decode.
"""

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
from pyzbar.pyzbar import decode as zbar_decode


@dataclass
class BoundingBox:
    x: int
    y: int
    width: int
    height: int


@dataclass
class DecodedBarcode:
    value: str
    bounding_box: BoundingBox


@dataclass
class PresenceGateResult:
    found: bool
    confidence: Optional[float]


def _imdecode(image_bytes: bytes) -> Optional[np.ndarray]:
    """Bytes -> BGR image array via OpenCV, or None if unreadable."""
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return image if image is not None and image.size > 0 else None


def decode_barcode(image_bytes: bytes) -> Optional[DecodedBarcode]:
    """OpenCV preprocessing (grayscale) + pyzbar decode. Grayscale is the
    useful, safe preprocessing step here — zbar does its own adaptive
    binarization internally, so heavier manual thresholding tends to hurt
    real-world decode rates more than it helps, and isn't applied."""
    image = _imdecode(image_bytes)
    if image is None:
        return None

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    symbols = zbar_decode(gray)
    if not symbols:
        return None

    symbol = symbols[0]
    rect = symbol.rect
    return DecodedBarcode(
        value=symbol.data.decode("utf-8", errors="replace"),
        bounding_box=BoundingBox(x=rect.left, y=rect.top, width=rect.width, height=rect.height),
    )


def run_presence_gate(model, image_bytes: bytes) -> PresenceGateResult:
    """Cheap "is anything in frame at all" check via YOLOv8n, used only when
    decode_barcode already found nothing. Not barcode-specific (see module
    docstring) — just informs whether the NO_BARCODE_DETECTED message should
    say "no object at all" or "an object was there but unreadable"."""
    image = _imdecode(image_bytes)
    if image is None:
        return PresenceGateResult(found=False, confidence=None)

    results = model.predict(image, verbose=False)
    if not results:
        return PresenceGateResult(found=False, confidence=None)

    confidences = results[0].boxes.conf
    if confidences is None or len(confidences) == 0:
        return PresenceGateResult(found=False, confidence=None)

    top_confidence = float(max(confidences))
    return PresenceGateResult(found=True, confidence=top_confidence)
