"""Generate dependency-free EAN-13 PNGs for the opt-in demo products."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.demo_data import DEMO_PRODUCTS
from app.services.barcodes import render_ean13_png


def _slug(name: str) -> str:
    return "-".join(part.lower() for part in name.split())


def main() -> None:
    output_dir = Path(__file__).resolve().parents[1] / "demo_assets" / "barcodes"
    output_dir.mkdir(parents=True, exist_ok=True)
    for product in DEMO_PRODUCTS:
        filename = f"{_slug(product['name'])}-{product['barcode']}.png"
        (output_dir / filename).write_bytes(render_ean13_png(product["barcode"]))
        print(f"Wrote {filename}")


if __name__ == "__main__":
    main()
