"""ZPL label generation for emission sources.

Produces the ZPL II text a Zebra printer would consume, plus an optional
rendered PNG preview. There is no physical printer in this project, so the
deliverable is valid printer-ready text a user can copy or download — not
an actual print job.

Layout is fixed at a 4" x 2" asset label at 8 dots/mm (203 dpi), the
common Zebra desktop density, which works out to 812 x 406 dots. The label
carries the source name, its facility, the source type and unit, and the
barcode_value encoded as Code 128 (^BC) with its human-readable
interpretation line printed underneath.

The preview is rendered by Labelary (labelary.com), a free public
ZPL-to-image API. It is strictly optional decoration: any failure to reach
it degrades to "ZPL text only" with a note, and never fails the endpoint.
Note that using it means the label's contents (source name, facility name,
barcode) leave this machine for a third-party service — hence the ability
to turn it off per request or globally.
"""

import base64
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Label geometry. LABEL_WIDTH_DOTS/LABEL_HEIGHT_DOTS are derived rather
# than hardcoded so the ZPL and the size asked of the renderer can never
# drift apart. 1 inch = 25.4 mm, so dots = inches * 25.4 * dpmm.
PRINT_DENSITY_DPMM = 8
LABEL_WIDTH_INCHES = 4.0
LABEL_HEIGHT_INCHES = 2.0
LABEL_WIDTH_DOTS = int(LABEL_WIDTH_INCHES * 25.4 * PRINT_DENSITY_DPMM)
LABEL_HEIGHT_DOTS = int(LABEL_HEIGHT_INCHES * 25.4 * PRINT_DENSITY_DPMM)

# Character budgets per line at the font sizes used below, so a long
# source_name overflows the label edge as an ellipsis rather than as
# silently clipped print.
MAX_TITLE_CHARS = 32
MAX_DETAIL_CHARS = 46

LABELARY_BASE_URL = os.getenv("LABELARY_BASE_URL", "https://api.labelary.com")
LABELARY_TIMEOUT_SECONDS = float(os.getenv("LABELARY_TIMEOUT_SECONDS", "5"))

PREVIEW_DISABLED_NOTE = (
    "Preview rendering is disabled; the response is ZPL text only."
)
PREVIEW_UNAVAILABLE_NOTE = (
    "Preview renderer was unreachable; the response is ZPL text only. "
    "The ZPL below is unaffected and still valid."
)


def preview_enabled() -> bool:
    """Global kill switch, read at call time.

    Defaults on, but the test suite sets it to "false" (see conftest.py) so
    that a test which forgets to mock the renderer fails loudly on a missing
    preview rather than quietly making a real network call.
    """
    return os.getenv("LABEL_PREVIEW_ENABLED", "true").lower() != "false"


def labelary_url() -> str:
    """The render endpoint for exactly the label this module generates."""
    width = _format_inches(LABEL_WIDTH_INCHES)
    height = _format_inches(LABEL_HEIGHT_INCHES)
    return (
        f"{LABELARY_BASE_URL}/v1/printers/{PRINT_DENSITY_DPMM}dpmm"
        f"/labels/{width}x{height}/0/"
    )


def _format_inches(value: float) -> str:
    """4.0 -> "4", 2.5 -> "2.5" — Labelary's path wants the plain number."""
    return str(int(value)) if value.is_integer() else str(value)


def _escape_zpl(text: str) -> str:
    """Neutralize the three characters that would otherwise be read as ZPL
    commands inside a field.

    Every field below is emitted with ^FH_, which makes ZPL interpret _XX
    as a hex byte, so the escape is to rewrite each dangerous character as
    its own hex code. The underscore itself has to go first, or it would
    corrupt the escapes introduced after it. This applies to the barcode
    field too: ^FH decoding happens before the data is encoded, so the
    barcode still carries the true value.
    """
    return (
        text.replace("_", "_5F")
        .replace("^", "_5E")
        .replace("~", "_7E")
    )


def _fit(text: str, limit: int) -> str:
    """Trim to what physically fits on the label, marking the trim."""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def build_zpl(
    *,
    source_name: str,
    facility_name: str,
    source_type: str,
    unit_of_measurement: str,
    barcode_value: str,
) -> str:
    """Render the label as ZPL II text.

    ^CI28 selects UTF-8 input encoding, ^PW/^LL set the label size, ^BY
    sets the barcode module width and ratio, and ^BCN,...,Y prints the
    Code 128 barcode with its human-readable line beneath it.
    """
    title = _escape_zpl(_fit(source_name, MAX_TITLE_CHARS))
    facility = _escape_zpl(_fit(facility_name, MAX_DETAIL_CHARS))
    detail = _escape_zpl(
        _fit(f"{source_type} / {unit_of_measurement}", MAX_DETAIL_CHARS)
    )
    barcode = _escape_zpl(barcode_value.strip())

    return "\n".join(
        [
            "^XA",
            "^CI28",
            f"^PW{LABEL_WIDTH_DOTS}",
            f"^LL{LABEL_HEIGHT_DOTS}",
            "^LH0,0",
            f"^FO30,28^A0N,40,40^FH_^FD{title}^FS",
            f"^FO30,84^A0N,28,28^FH_^FD{facility}^FS",
            f"^FO30,122^A0N,28,28^FH_^FD{detail}^FS",
            "^BY3,3,100",
            f"^FO30,170^BCN,100,Y,N,N^FH_^FD{barcode}^FS",
            "^XZ",
        ]
    ) + "\n"


def render_preview(zpl_code: str, *, requested: bool = True) -> tuple[Optional[str], Optional[str]]:
    """Render *zpl_code* to a base64 PNG via Labelary.

    Returns ``(preview_png_base64, preview_note)``. Exactly one is None:
    on success the note is None, and on any failure the preview is None and
    the note explains why. Never raises — a cosmetic preview must not be
    able to fail a label request, which is why every httpx error and every
    non-200 response funnels into the same graceful outcome.
    """
    if not requested or not preview_enabled():
        return None, PREVIEW_DISABLED_NOTE

    try:
        response = httpx.post(
            labelary_url(),
            content=zpl_code.encode("utf-8"),
            headers={"Accept": "image/png"},
            timeout=LABELARY_TIMEOUT_SECONDS,
        )
    except Exception:  # noqa: BLE001 — offline, DNS, timeout, TLS, all equal here
        logger.warning("ZPL preview renderer unreachable", exc_info=True)
        return None, PREVIEW_UNAVAILABLE_NOTE

    if response.status_code != 200:
        logger.warning(
            "ZPL preview renderer returned HTTP %s", response.status_code
        )
        return None, PREVIEW_UNAVAILABLE_NOTE

    return base64.b64encode(response.content).decode("ascii"), None
