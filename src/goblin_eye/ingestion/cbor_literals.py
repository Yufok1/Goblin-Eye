"""Minimal, bounded CBOR reader for inspected static addon metadata.

The QuestieDB artifact only uses definite-length CBOR.  Keeping the reader here
avoids executing Lua and preserves Goblin Eye's dependency-free installation.
"""
from __future__ import annotations

import struct
from typing import Any


class CborLiteralReader:
    def __init__(self, body: bytes, *, max_depth: int = 80):
        self.body = body
        self.position = 0
        self.max_depth = max_depth

    def _take(self, size: int) -> bytes:
        end = self.position + size
        if end > len(self.body):
            raise ValueError("Truncated CBOR value")
        value = self.body[self.position:end]
        self.position = end
        return value

    def _argument(self, value: int) -> int:
        if value < 24:
            return value
        widths = {24: 1, 25: 2, 26: 4, 27: 8}
        if value not in widths:
            raise ValueError("Indefinite or reserved CBOR length is unsupported")
        return int.from_bytes(self._take(widths[value]), "big")

    def read(self, depth: int = 0) -> Any:
        if depth > self.max_depth:
            raise ValueError("CBOR nesting is too deep")
        initial = self._take(1)[0]
        major, additional = initial >> 5, initial & 31
        if major in (0, 1):
            value = self._argument(additional)
            return value if major == 0 else -1 - value
        if major in (2, 3):
            raw = self._take(self._argument(additional))
            return raw if major == 2 else raw.decode("utf-8")
        if major == 4:
            return [self.read(depth + 1) for _ in range(self._argument(additional))]
        if major == 5:
            result = {}
            for _ in range(self._argument(additional)):
                key = self.read(depth + 1)
                if key in result:
                    raise ValueError("Duplicate CBOR map key")
                result[key] = self.read(depth + 1)
            return result
        if major == 6:
            self._argument(additional)  # Preserve the value, not an unused tag.
            return self.read(depth + 1)
        if major == 7:
            if additional in (20, 21, 22):
                return {20: False, 21: True, 22: None}[additional]
            if additional == 25:
                return struct.unpack(">e", self._take(2))[0]
            if additional == 26:
                return struct.unpack(">f", self._take(4))[0]
            if additional == 27:
                return struct.unpack(">d", self._take(8))[0]
        raise ValueError(f"Unsupported CBOR initial byte 0x{initial:02x}")


def loads(body: bytes) -> Any:
    reader = CborLiteralReader(body)
    value = reader.read()
    if reader.position != len(body):
        raise ValueError("Trailing bytes after CBOR value")
    return value
