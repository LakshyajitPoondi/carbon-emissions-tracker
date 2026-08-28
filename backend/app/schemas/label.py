"""Pydantic schemas for ZPL label generation.

Matches docs/api-contract.md — Labels section. Read-only: a label is
derived from an emission source on demand, never stored.
"""

from typing import Optional

from pydantic import BaseModel


class LabelResponse(BaseModel):
    """GET /emission-sources/{id}/label response."""

    emission_source_id: int
    barcode_value: str

    # The deliverable: printer-ready ZPL II the user can copy or download.
    zpl_code: str

    # Geometry the ZPL was generated for, so a consumer knows what stock to
    # load without parsing ^PW/^LL back out of the code.
    label_width_inches: float
    label_height_inches: float
    print_density_dpmm: int

    # Optional cosmetic preview. Null whenever rendering was skipped or the
    # renderer could not be reached — preview_note then says which, and
    # zpl_code is unaffected either way.
    preview_png_base64: Optional[str] = None
    preview_note: Optional[str] = None
