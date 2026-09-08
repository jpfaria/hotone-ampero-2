"""Hotone Ampero II Stage USB-MIDI SysEx protocol (reverse-engineered from the editor, 2026-09).

Frame:  F0 21 25 4D 50 00 00 CK CMD LEN(2×7-bit LE) OFF(2×7-bit LE) NIBBLES... F7
  CK      = sum of every byte from LEN's high byte up to (not including) F7, mod 128
  CMD     = 0x11 query (host→device), 0x12 data (both directions)
  LEN     = decoded payload length; OFF = decoded offset of this chunk (dumps come chunked)
  NIBBLES = each payload byte b as two bytes (b >> 4, b & 0x0F)

Payload: [type 2B] [op] [target] [len32 LE = LEN-8] [LEN+5] body [11 00 00]
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

SYSEX_START = 0xF0
SYSEX_END = 0xF7
HEADER = bytes.fromhex("2125 4D50 0000")  # after F0
CMD_QUERY = 0x11
CMD_DATA = 0x12
TRAILER = bytes.fromhex("110000")
SLOTS = 12
PATCHES_PER_BANK = 5
PATCH_NAME_LEN = 16   # plus a NUL terminator on the wire
MAX_CHUNK = 185  # decoded bytes per chunk observed in patch dumps

_CK_FROM = 10          # frame index where the checksum sum starts (LEN high byte)
_INNER_LEN_EXTRA = 8   # len32 = LEN - 8
_INNER_TAG_EXTRA = 5   # tag byte = LEN + 5


def encode_nibbles(data: bytes) -> bytes:
    out = bytearray()
    for b in data:
        out += bytes((b >> 4, b & 0x0F))
    return bytes(out)


def decode_nibbles(data: bytes) -> bytes:
    if len(data) % 2:
        raise ValueError(f"odd nibble stream length {len(data)}")
    return bytes((data[i] << 4) | data[i + 1] for i in range(0, len(data), 2))


def _u14(v: int) -> bytes:
    return bytes((v & 0x7F, (v >> 7) & 0x7F))


def checksum(frame: bytes) -> int:
    """Checksum of a full frame (F0..F7): sum from LEN's high byte, excluding F7."""
    return sum(frame[_CK_FROM:-1]) & 0x7F


@dataclass(frozen=True)
class Frame:
    cmd: int
    length: int
    offset: int
    payload: bytes


def build_frame(cmd: int, payload: bytes, offset: int = 0, total: int | None = None) -> bytes:
    total = len(payload) if total is None else total
    body = bytes((cmd,)) + _u14(total) + _u14(offset) + encode_nibbles(payload)
    frame = bytes((SYSEX_START,)) + HEADER + b"\0" + body + bytes((SYSEX_END,))
    return frame[:7] + bytes((checksum(frame),)) + frame[8:]


def parse_frame(frame: bytes) -> Frame:
    if frame[0] != SYSEX_START or frame[-1] != SYSEX_END or frame[1:7] != HEADER:
        raise ValueError("not an Ampero frame")
    cmd = frame[8]
    length = frame[9] | (frame[10] << 7)
    offset = frame[11] | (frame[12] << 7)
    return Frame(cmd, length, offset, decode_nibbles(frame[13:-1]))


def _payload(kind: bytes, body: bytes) -> bytes:
    """kind = [type 2B, op, target] (4 bytes) or [type 2B, op] (3 bytes, save)."""
    total = len(kind) + 4 + 1 + len(body) + len(TRAILER)
    return kind + struct.pack("<I", total - _INNER_LEN_EXTRA) + bytes((total + _INNER_TAG_EXTRA,)) + body + TRAILER


def _msg(cmd: int, kind: str, body: bytes) -> bytes:
    return build_frame(cmd, _payload(bytes.fromhex(kind), body))


def msg_scene(scene: int) -> bytes:
    return _msg(CMD_DATA, "01000003", bytes((scene,)))


def msg_set_param(slot: int, index: int, value: float) -> bytes:
    return _msg(CMD_DATA, "03000401", bytes((slot, 0, index, 0)) + struct.pack("<f", value))


def msg_query_param(slot: int, index: int) -> bytes:
    return _msg(CMD_QUERY, "03000A01", bytes((slot, 0, index, 0)))


def msg_scene_powers(scene: int, powers: list[int]) -> bytes:
    if len(powers) != SLOTS:
        raise ValueError(f"need {SLOTS} slot states")
    return _msg(CMD_DATA, "04000901", bytes((scene, *powers)))


def msg_load_patch(index: int) -> bytes:
    return _msg(CMD_DATA, "00000900", struct.pack("<I", index))


def msg_get_patch(index: int) -> bytes:
    return _msg(CMD_QUERY, "00000001", struct.pack("<I", index))


def msg_save_patch(index: int, name: str) -> bytes:
    raw = name.encode("ascii")
    if len(raw) > PATCH_NAME_LEN:
        raise ValueError(f"patch name longer than {PATCH_NAME_LEN}: {name!r}")
    return _msg(CMD_DATA, "00000005", struct.pack("<I", index) + raw.ljust(PATCH_NAME_LEN + 1, b"\0"))


def patch_index(label: str) -> int:
    """'A28-4' -> 138 (bank A, 5 patches per bank, both 1-based)."""
    bank, pos = label.upper().lstrip("A").split("-")
    return (int(bank) - 1) * PATCHES_PER_BANK + int(pos) - 1


def patch_label(index: int) -> str:
    return f"A{index // PATCHES_PER_BANK + 1}-{index % PATCHES_PER_BANK + 1}"


def msg_query_scene() -> bytes:
    """Reply payload byte 9 = current scene (0-based)."""
    return build_frame(CMD_QUERY, bytes.fromhex("01000003") + bytes(4))


SCENE_REPLY_INDEX = 9


SCENE_NAME_LEN = 7          # plus NUL, padded to 8 on the wire
FOOTSWITCHES = 7
SLOT_EMPTY = 0xFF


def msg_set_model(slot: int, category: int, code: int) -> bytes:
    """category = catalog category index (DYN 0 .. NAM 17), code = catalog model code; see catalog.py.
    A wrong category byte hangs the pedal's SysEx until power-cycle (seen with 0 + an AMP code)."""
    return _msg(CMD_DATA, "02000401", bytes((slot, category)) + struct.pack("<I", code) + b"\x01")


def msg_clear_slot(slot: int) -> bytes:
    return _msg(CMD_DATA, "02000401", bytes((slot,)) + bytes((SLOT_EMPTY,)) * 5 + b"\x01")


def msg_rename_scene(scene: int, name: str) -> bytes:
    raw = name.encode("ascii")
    if len(raw) > SCENE_NAME_LEN:
        raise ValueError(f"scene name longer than {SCENE_NAME_LEN}: {name!r}")
    return _msg(CMD_DATA, "07000901", struct.pack("<I", scene) + raw.ljust(SCENE_NAME_LEN + 1, b"\0"))


def msg_set_tempo(bpm: int) -> bytes:
    return _msg(CMD_DATA, "02000901", b"\0\0" + struct.pack("<H", bpm))


def msg_query_global(page: int) -> bytes:
    """Pages seen: 1 input/output, 2 usb audio, 3 global EQ, 6, 7 controls, 8 midi. Reply body via reply_body()."""
    return build_frame(CMD_QUERY, bytes((0, 0, page, 0)) + bytes(4))


GLOBAL_PARAMS = {   # (page, id) -> (byte in page, name); values are the dropdown's option index
    (1, 0x01): (0, "input mode L: 0 electric, 1 acoustic, 2 line"),
    (1, 0x02): (1, "input mode R"),
    (1, 0x03): (3, "unbalanced output (1 = line)"),
    (1, 0x04): (4, "balanced output"),
    (1, 0x07): (8, "unbalanced source: 0 normal, 1 usb only"),
    (1, 0x08): (9, "fx send source"),
    (1, 0x09): (6, "bypass mode: 0 true bypass, 1 dsp bypass"),
    (1, 0x0B): (10, "balanced source"),
    (1, 0x0C): (11, "power-on mode: 0 normal, 1 mute"),
    (1, 0x10): (15, "no cab mode L: 0 off, 1 cab only, 2 ir only"),
    (1, 0x11): (16, "no cab mode R"),
    (2, 0x06): (5, "usb audio: unbalanced output source: 1 usb out 1/2, 2 3/4, 3 5/6"),
    (7, 0x06): (15, "global tempo on/off"),
    (8, 0x01): (0, "auto cab match on/off"),
    (8, 0x02): (1, "patch display mode: 0 mode 1, 1 mode 2"),
    (8, 0x04): (3, "bank select mode: 0 initial, 1 wait"),
}
# page 7 (Controls) layout: [0] exp/ctrl 1 function (0 exp, 1 single fs, 2 dual fs), [1] exp/ctrl 2 function,
# [2]/[3] single-FS function code of ctrl 1/2 (0x29 = EXP 1/2, 0 = A1 on/off ...), [4..7] dual-FS codes,
# [15] global tempo on, [16] global tempo bpm. Set with 4-byte bodies: (7, 0x01) [ctrl 00 value 00],
# (7, 0x02) [ctrl 00 code 00]. Page 6 (MIDI): [0] in source (3 mixed), [1..3] channel TRS/BT/USB (0-15,
# 16 omni), [5] clock out TRS, [7] clock source — ids unknown; an out-of-range value HANGS the pedal.


def msg_set_global(param: int, value: int, page: int = 1) -> bytes:
    """Global Settings field `param` on `page` (see GLOBAL_PARAMS) = option index `value`.
    Only send (page, id, value) combinations listed above: unknown ids or out-of-range values hang the pedal."""
    return _msg(CMD_DATA, bytes((param, 0, page, 0)).hex(), bytes((value,)))


def msg_set_control_function(ctrl: int, function: int) -> bytes:
    """EXP/CTRL `ctrl` (0/1) function: 0 exp, 1 single fs, 2 dual fs (page 7 id 1)."""
    return _msg(CMD_DATA, "01000700", bytes((ctrl, 0, function, 0)))


def msg_set_control_fs_code(ctrl: int, code: int) -> bytes:
    """Single-FS function of EXP/CTRL `ctrl` (page 7 id 2), e.g. 0x29 = EXP 1/2."""
    return _msg(CMD_DATA, "02000700", bytes((ctrl, 0, code, 0)))


def msg_query_footswitches() -> bytes:
    return build_frame(CMD_QUERY, bytes.fromhex("00000301") + bytes(4))


def msg_set_footswitches(functions: list[int]) -> bytes:
    """One byte per footswitch: 0xFF off, 0x1D = Scene 3 (other codes not mapped yet)."""
    if len(functions) != FOOTSWITCHES:
        raise ValueError(f"need {FOOTSWITCHES} footswitch functions")
    return _msg(CMD_DATA, "01000301", bytes(functions))


_REPLY_BODY_START = 9   # after [type 2B][op][tgt][len32][tag]


def reply_body(frame: Frame) -> bytes:
    """Data bytes of a 0x12 reply: strips the inner header and the 11 00 00 trailer."""
    return frame.payload[_REPLY_BODY_START:-len(TRAILER)]


INVENTORY = {
    "patches": "00000801",   # 300 names (patch.patch_names)
    "irs": "03000004",       # 100 user IR names, 16 bytes each
    "clones": "03000007",    # 30 CLONE capture names, 18 bytes each
    "nams": "03000008",      # 30 NAM names, 18 bytes each
    "firmware": "05000003",  # "V1.7.0"
}


def msg_query_inventory(kind: str) -> bytes:
    return build_frame(CMD_QUERY, bytes.fromhex(INVENTORY[kind]) + bytes(4))


FOOTSWITCH_FUNCTIONS = {
    "off": 0xFF, "scene 1": 0x1B, "scene 2": 0x1C, "scene 3": 0x1D, "scene 4": 0x1E, "scene 5": 0x1F,
    "bank -": 0x10, "patch +": 0x26, "tap tempo": 0x0D, "tuner": 0x12, "looper": 0x11, "exp 1/2": 0x29,
    "slot a2": 0x0C,   # toggling the block in slot 1; other slot codes not captured (bank +, patch - either)
}


def msg_set_patch_volume(volume: int) -> bytes:
    """The output volume next to the speaker icon (0-100)."""
    return _msg(CMD_DATA, "01000901", b"\0\0" + struct.pack("<H", volume))


def msg_set_quick_access(para: int, slot: int, category: int, code: int, param: int) -> bytes:
    return _msg(CMD_DATA, "01000201", bytes((para, slot, category)) + struct.pack("<I", code) + bytes((param,)))


def msg_clear_quick_access(para: int) -> bytes:
    return _msg(CMD_DATA, "01000201", bytes((para,)) + bytes((SLOT_EMPTY,)) * 7)


def msg_set_exp_target(exp: int, target: int, slot: int, category: int, code: int, param: int) -> bytes:
    """exp 0..2 = EXP1..3 tabs, target 0..3. Range min/max and curve not captured yet."""
    return _msg(CMD_DATA, "02000601", bytes((target, exp, slot, category)) + struct.pack("<I", code) + bytes((param,)))


def msg_clear_exp_target(exp: int, target: int) -> bytes:
    return _msg(CMD_DATA, "02000601", bytes((target, exp)) + bytes((SLOT_EMPTY,)) * 7)


TEMPLATE_NAME_LEN = 11        # padded to 12 on the wire
_USER_TEMPLATE_BASE = 4       # user template position 1 is sent as 5


def msg_query_templates() -> bytes:
    return build_frame(CMD_QUERY, bytes.fromhex("04000002") + bytes(4))


def msg_save_template(position: int, name: str) -> bytes:
    """Store the edit buffer as user template `position` (1-5)."""
    raw = name.encode("ascii")
    if len(raw) > TEMPLATE_NAME_LEN:
        raise ValueError(f"template name longer than {TEMPLATE_NAME_LEN}: {name!r}")
    return _msg(CMD_DATA, "02000002", struct.pack("<I", position + _USER_TEMPLATE_BASE) + raw.ljust(TEMPLATE_NAME_LEN + 1, b"\0"))


PATCH_DUMP_KIND = bytes.fromhex("00000001")


def is_patch_dump(payload: bytes) -> bool:
    """True for a patch image reply — also what the pedal broadcasts by itself after a footswitch patch change."""
    return payload[:4] == PATCH_DUMP_KIND


def msg_load_template(position: int) -> bytes:
    """Load user template `position` (1-5) into the edit buffer; the pedal answers with a 00 00 00 02 template image."""
    return _msg(CMD_DATA, "03000002", struct.pack("<I", position + _USER_TEMPLATE_BASE))


UPLOAD_CHUNK = 183
NAM_UPLOAD_KIND = bytes.fromhex("00000008")


def frames_for_upload(kind: bytes, image: bytes) -> list[bytes]:
    """Compress `image` (LZO1X) behind [kind][len32] and split into chunked 0x12 frames like the editor does."""
    import lzokay  # local import: only uploads need it

    stream = lzokay.compress(image)
    payload = kind + struct.pack("<I", len(stream)) + stream
    return [build_frame(CMD_DATA, payload[o:o + UPLOAD_CHUNK], offset=o, total=len(payload))
            for o in range(0, len(payload), UPLOAD_CHUNK)]


NAM_NAME_LEN = 16


def msg_rename_nam(slot: int, name: str) -> bytes:
    """slot is 0-based (NAM Slot 3 = 2)."""
    raw = name.encode("ascii")
    if len(raw) > NAM_NAME_LEN:
        raise ValueError(f"NAM name longer than {NAM_NAME_LEN}: {name!r}")
    return _msg(CMD_DATA, "02000008", struct.pack("<I", slot) + raw.ljust(NAM_NAME_LEN, b"\0"))


def msg_delete_nam(slot: int) -> bytes:
    return _msg(CMD_DATA, "01000008", struct.pack("<I", slot))


IR_UPLOAD_KIND = bytes.fromhex("00000004")


CLONE_UPLOAD_KIND = bytes.fromhex("00000007")


def msg_delete_clone(slot: int) -> bytes:
    """By analogy with NAM (verified live: the slot reads back empty)."""
    return _msg(CMD_DATA, "01000007", struct.pack("<I", slot))


def msg_set_global_eq(index: int, value: float) -> bytes:
    """Global EQ field by index in the page-3 field list (low cut enabled = 0 ... band 1 gain = 10); see patch.GLOBAL_EQ_FIELDS."""
    return _msg(CMD_DATA, "02000300", struct.pack("<If", index, value))
