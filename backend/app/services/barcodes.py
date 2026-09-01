"""Dependency-free EAN-13 generation and PNG rendering.

Product-generated values use GS1's 20 restricted-circulation prefix. The
renderer deliberately stays pure computation: no external API, filesystem,
or optional imaging dependency is needed.
"""

from __future__ import annotations

import binascii
import struct
import zlib

LEFT_ODD = {
    "0": "0001101",
    "1": "0011001",
    "2": "0010011",
    "3": "0111101",
    "4": "0100011",
    "5": "0110001",
    "6": "0101111",
    "7": "0111011",
    "8": "0110111",
    "9": "0001011",
}
LEFT_EVEN = {
    "0": "0100111",
    "1": "0110011",
    "2": "0011011",
    "3": "0100001",
    "4": "0011101",
    "5": "0111001",
    "6": "0000101",
    "7": "0010001",
    "8": "0001001",
    "9": "0010111",
}
RIGHT = {
    "0": "1110010",
    "1": "1100110",
    "2": "1101100",
    "3": "1000010",
    "4": "1011100",
    "5": "1001110",
    "6": "1010000",
    "7": "1000100",
    "8": "1001000",
    "9": "1110100",
}
PARITY = {
    "0": "LLLLLL",
    "1": "LLGLGG",
    "2": "LLGGLG",
    "3": "LLGGGL",
    "4": "LGLLGG",
    "5": "LGGLLG",
    "6": "LGGGLL",
    "7": "LGLGLG",
    "8": "LGLGGL",
    "9": "LGGLGL",
}


def ean13_from_sequence(sequence: int) -> str:
    """Return ``20`` + a ten-digit sequence + the EAN-13 check digit."""
    if sequence < 0 or sequence > 9_999_999_999:
        raise ValueError("sequence must fit in ten digits")
    body = f"20{sequence:010d}"
    weighted_sum = sum(
        int(digit) * (1 if index % 2 == 0 else 3)
        for index, digit in enumerate(body)
    )
    return f"{body}{(-weighted_sum) % 10}"


def is_valid_ean13(value: str) -> bool:
    if len(value) != 13 or not value.isdigit():
        return False
    weighted_sum = sum(
        int(digit) * (1 if index % 2 == 0 else 3)
        for index, digit in enumerate(value)
    )
    return weighted_sum % 10 == 0


def internal_ean13_sequence(value: str) -> int | None:
    """Return the ten-digit sequence for a valid ``20`` EAN, else None."""
    if not value.startswith("20") or not is_valid_ean13(value):
        return None
    return int(value[2:12])


def _encode_ean13(value: str) -> str:
    if not is_valid_ean13(value):
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
    checksum = binascii.crc32(payload) & 0xFFFFFFFF
    return (
        struct.pack(">I", len(data))
        + payload
        + struct.pack(">I", checksum)
    )


def render_ean13_png(value: str) -> bytes:
    """Render a standards-compliant monochrome EAN-13 barcode as PNG."""
    modules = _encode_ean13(value)
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
            is_guard = any(
                start <= module_index < end for start, end in guard_ranges
            )
            if bar_top <= y < (guard_bottom if is_guard else bar_bottom):
                start_x = (quiet_modules + module_index) * module_width
                row[start_x : start_x + module_width] = b"\x00" * module_width
        rows.append(b"\x00" + bytes(row))

    signature = b"\x89PNG\r\n\x1a\n"
    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (
        signature
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(b"".join(rows), level=9))
        + _png_chunk(b"IEND", b"")
    )
