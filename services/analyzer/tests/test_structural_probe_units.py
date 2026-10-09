from __future__ import annotations

import pytest

from app.demo.structural_probe import (
    ProbeError,
    _BitReader,
    _parse_wire,
    _snappy_raw_decompress,
)


def test_snappy_literal_only():
    # uncompressed length=3, literal tag length=3, bytes=abc
    encoded = bytes([3, 8]) + b"abc"
    assert _snappy_raw_decompress(encoded) == b"abc"


def test_snappy_overlapping_copy():
    # output abc + copy(offset=3, length=6) -> abcabcabc
    encoded = bytes([9, 8]) + b"abc" + bytes([0x16, 0x03, 0x00])
    assert _snappy_raw_decompress(encoded) == b"abcabcabc"


def test_snappy_rejects_bad_back_reference():
    encoded = bytes([4, 0x0E, 0x01, 0x00])
    with pytest.raises(ProbeError):
        _snappy_raw_decompress(encoded)


def test_wire_parser_handles_varint_string_float():
    payload = (
        bytes([0x08, 0x96, 0x01])
        + bytes([0x12, 0x03]) + b"abc"
        + bytes([0x1D, 0x00, 0x00, 0x80, 0x3F])
    )
    fields = _parse_wire(payload)
    assert fields[0] == (1, 0, 150)
    assert fields[1] == (2, 2, b"abc")
    assert fields[2][0:2] == (3, 5)


def test_bitreader_reads_small_ubitvar():
    # For value 5 (<16), ubitvar is the six LSB-first bits 000101.
    reader = _BitReader(bytes([5]))
    assert reader.read_ubitvar() == 5
