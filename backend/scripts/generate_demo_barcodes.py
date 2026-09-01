"""Generate dependency-free EAN-13 PNGs for the opt-in demo products."""

from __future__ import annotations

import binascii
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.demo_data import DEMO_PRODUCTS

LEFT_ODD = {
    "0": "0001101", "1": "0011001", "2": "0010011", "3": "0111101", "4": "0100011",
    "5": "0110001", "6": "0101111", "7": "0111011", "8": "0110111", "9": "0001011",
}
LEFT_EVEN = {
    "0": "0100111", "1": "0110011", "2": "0011011", "3": "0100001", "4": "0011101",
    "5": "0111001", "6": "0000101", "7": "0010001", "8": "0001001", "9": "0010111",
}
RIGHT = {
    "0": "1110010", "1": "1100110", "2": "1101100", "3": "1000010", "4": "1011100",
    "5": "1001110", "6": "1010000", "7": "1000100", "8": "1001000", "9": "1110100",
}
PARITY = {
    "0": "LLLLLL", "1": "LLGLGG", "2": "LLGGLG", "3": "LLGGGL", "4": "LGLLGG",
    "5": "LGGLLG", "6": "LGGGLL", "7": "LGLGLG", "8": "LGLGGL", "9": "LGGLGL",
}


def _valid_ean13(value: str) -> bool:
    if len(value) != 13 or not value.isdigit():
        return False
    weighted_sum = sum(
        int(digit) * (1 if index % 2 == 0 else 3)
        for index, digit in enumerate(value[:12])
    )
    return (-weighted_sum) % 10 == int(value[-1])


def _encode(value: str) -> str:
    if not _valid_ean13(value):
        raise ValueError(f"Invalid EAN-13 value: {value}")
    parity = PARITY[value[0]]
    left = "".join(
        (LEFT_ODD if pattern == "L" else LEFT_EVEN)[digit]
        for digit, pattern in zip(value[1:7], parity)
    )
    right = "".join(RIGHT[digit] for digit in value[7:])
    return f"101{left}01010{right}101"


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    payload = kind + data
    return struct.pack(">I", len(data)) + payload + struct.pack(">I", binascii.crc32(payload) & 0xFFFFFFFF)


def _write_barcode(path: Path, value: str) -> None:
    modules = _encode(value)
    module_width = 4
    quiet_modules = 11
    width = (len(modules) + (quiet_modules * 2)) * module_width
    height = 180
    bar_top = 14
    bar_bottom = 154
    guard_bottom = 166
    guard_ranges = ((0, 3), (45, 50), (92, 95))

    rows = []
    for y in range(height):
        row = bytearray([255] * width)
        for module_index, bit in enumerate(modules):
            if bit != "1":
                continue
            is_guard = any(start <= module_index < end for start, end in guard_ranges)
            if bar_top <= y < (guard_bottom if is_guard else bar_bottom):
                start_x = (quiet_modules + module_index) * module_width
                row[start_x:start_x + module_width] = b"\x00" * module_width
        rows.append(b"\x00" + bytes(row))

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    path.write_bytes(
        signature
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(b"".join(rows), level=9))
        + _png_chunk(b"IEND", b"")
    )


def _slug(name: str) -> str:
    return "-".join(part.lower() for part in name.split())


def main() -> None:
    output_dir = Path(__file__).resolve().parents[1] / "demo_assets" / "barcodes"
    output_dir.mkdir(parents=True, exist_ok=True)
    for product in DEMO_PRODUCTS:
        filename = f"{_slug(product['name'])}-{product['barcode']}.png"
        _write_barcode(output_dir / filename, product["barcode"])
        print(f"Wrote {filename}")


if __name__ == "__main__":
    main()
