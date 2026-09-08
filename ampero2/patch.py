"""Replies and patch images. Every 0x12 payload is [type 2B][op][tgt][len32] + an LZO1X stream
(short bodies are just a literal run + the 11 00 00 end marker). Patch images are 7705 bytes."""
from __future__ import annotations

import struct
from dataclasses import dataclass

import lzokay

from .protocol import SLOTS, Frame

_STREAM_OFFSET = 8
_MAX_IMAGE = 65536

# patch image layout (verified by diffing images after single edits, see docs/ampero-sysex.md)
_NAME = 34
_NAME_FIELD = 17
_FOOTSWITCHES = 153
FOOTSWITCH_COUNT = 7
_SLOT_TABLE = 200
_PARAMS = 256
_SCENE_STRIDE = 1200
_SLOT_STRIDE = 100
SCENES = 5
_POWERS = 6256
_TEMPOS = 6326
_SCENE_NAMES = 6655
_SCENE_NAME_FIELD = 8
SLOT_EMPTY_CODE = 0xFFFFFFFF

# inventories (reply of the queries listed in protocol.INVENTORY)
PATCH_COUNT = 300
_PATCH_NAMES = 600
PATCH_NAME_FIELD = 17
CAPTURE_NAME_FIELD = 17   # CLONE and NAM slots (30 each)
CAPTURE_SLOTS = 30
IR_NAME_FIELD = 32        # 50 user IR slots; an unused slot still holds "User IR n" leftovers
IR_SLOTS = 50


@dataclass(frozen=True)
class PatchHeader:
    index: int
    name: str


@dataclass(frozen=True)
class PatchImage:
    raw: bytes
    header: PatchHeader
    slot_codes: list[int | None]
    scene_names: list[str]
    tempos: list[int]
    powers: list[list[bool]]
    footswitches: list[int]

    def param(self, scene: int, slot: int, index: int) -> float:
        return struct.unpack_from("<f", self.raw, _PARAMS + _SCENE_STRIDE * scene + _SLOT_STRIDE * slot + 4 * index)[0]


def reassemble(frames: list[Frame]) -> bytes:
    out = bytearray()
    for f in sorted(frames, key=lambda f: f.offset):
        if f.offset != len(out):
            raise ValueError(f"chunk gap: have {len(out)} bytes, next chunk at {f.offset}")
        out += f.payload
    total = frames[0].length
    if len(out) != total:
        raise ValueError(f"dump incomplete: {len(out)}/{total} bytes")
    return bytes(out)


def _lzo(stream: bytes) -> bytes:
    """LZO1X raw streams carry no size: find the smallest buffer that fits (lzokay pads to the buffer)."""
    lo, hi = 1, _MAX_IMAGE
    while lo < hi:
        mid = (lo + hi) // 2
        try:
            lzokay.decompress(stream, mid)
            hi = mid
        except lzokay.OutputOverrunError:
            lo = mid + 1
    return lzokay.decompress(stream, lo)


def decode_reply(payload: bytes) -> bytes:
    return _lzo(payload[_STREAM_OFFSET:])


decompress_patch = decode_reply


def _cstr(raw: bytes, offset: int, field: int) -> str:
    return raw[offset:offset + field].split(b"\0", 1)[0].decode("ascii", "replace")


def parse_header(raw: bytes) -> PatchHeader:
    return PatchHeader(index=struct.unpack_from("<I", raw, 0)[0], name=_cstr(raw, _NAME, _NAME_FIELD))


def parse_image(raw: bytes) -> PatchImage:
    codes = [struct.unpack_from("<I", raw, _SLOT_TABLE + 4 * s)[0] for s in range(SLOTS)]
    return PatchImage(
        raw=raw,
        header=parse_header(raw),
        slot_codes=[None if c == SLOT_EMPTY_CODE else c for c in codes],
        scene_names=[_cstr(raw, _SCENE_NAMES + _SCENE_NAME_FIELD * i, _SCENE_NAME_FIELD) for i in range(SCENES)],
        tempos=[struct.unpack_from("<H", raw, _TEMPOS + 2 * i)[0] for i in range(SCENES)],
        powers=[[raw[_POWERS + SLOTS * i + s] == 1 for s in range(SLOTS)] for i in range(SCENES)],
        footswitches=list(raw[_FOOTSWITCHES:_FOOTSWITCHES + FOOTSWITCH_COUNT]),
    )


def name_table(raw: bytes, field: int) -> list[str]:
    return [_cstr(raw, i, field) for i in range(0, len(raw) - field + 1, field)]


def patch_names(raw: bytes) -> list[str]:
    return name_table(raw[_PATCH_NAMES:_PATCH_NAMES + PATCH_COUNT * PATCH_NAME_FIELD], PATCH_NAME_FIELD)


def firmware_version(raw: bytes) -> str:
    return _cstr(raw, 0, len(raw))


# Global EQ page (00 00 03 00): [on/off f32] then the field list below as f32, then [level f32][3 x 0][1.0]
GLOBAL_EQ_FIELDS = [
    ("low cut", "enabled"), ("low cut", "freq"), ("low cut", "q"),
    ("low shelf", "enabled"), ("low shelf", "freq"), ("low shelf", "q"), ("low shelf", "gain"),
    ("band 1", "enabled"), ("band 1", "freq"), ("band 1", "q"), ("band 1", "gain"),
    ("band 2", "enabled"), ("band 2", "freq"), ("band 2", "q"), ("band 2", "gain"),
    ("band 3", "enabled"), ("band 3", "freq"), ("band 3", "q"), ("band 3", "gain"),
    ("band 4", "enabled"), ("band 4", "freq"), ("band 4", "q"), ("band 4", "gain"),
    ("high shelf", "enabled"), ("high shelf", "freq"), ("high shelf", "q"), ("high shelf", "gain"),
    ("high cut", "enabled"), ("high cut", "freq"), ("high cut", "q"),
]


@dataclass(frozen=True)
class GlobalEq:
    enabled: bool
    bands: dict
    level: float


def parse_global_eq(page: bytes) -> GlobalEq:
    floats = struct.unpack_from(f"<{len(page) // 4}f", page)
    bands: dict = {}
    for i, (band, field) in enumerate(GLOBAL_EQ_FIELDS):
        v = floats[1 + i]
        bands.setdefault(band, {})[field] = (v != 0.0) if field == "enabled" else round(v, 4)
    return GlobalEq(enabled=floats[0] != 0.0, bands=bands, level=floats[1 + len(GLOBAL_EQ_FIELDS)])


TEMPLATE_SLOTS = 5
_TEMPLATE_ENTRY = 12      # 7-char name + NUL, then 4 bytes of leftovers


def template_names(raw: bytes) -> list[str]:
    return [_cstr(raw, i * _TEMPLATE_ENTRY, 8) for i in range(TEMPLATE_SLOTS)]
