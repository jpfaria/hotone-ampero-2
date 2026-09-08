"""Golden vectors: bytes captured from the Ampero II editor with MIDI Monitor (2026-09-07)."""
import struct

import pytest

from ampero2 import protocol as P

from ampero2.protocol import (
    PATCH_NAME_LEN,
    Frame,
    build_frame,
    checksum,
    decode_nibbles,
    encode_nibbles,
    msg_get_patch,
    msg_load_patch,
    msg_query_param,
    msg_save_patch,
    msg_scene,
    msg_scene_powers,
    msg_set_param,
    parse_frame,
    patch_index,
    patch_label,
)


def hx(s: str) -> bytes:
    return bytes(int(x, 16) for x in s.split())


SCENE2 = hx("F0 21 25 4D 50 00 00 10 12 0D 00 00 00 00 01 00 00 00 00 00 03 00 05 00 00 00 00 00 00 01 02 00 02 01 01 00 00 00 00 F7")
MIX21 = hx("F0 21 25 4D 50 00 00 3D 12 14 00 00 00 00 03 00 00 00 04 00 01 00 0C 00 00 00 00 00 00 01 09 00 06 00 00 00 00 00 00 00 00 00 00 0A 08 04 01 01 01 00 00 00 00 F7")
TIME501 = hx("F0 21 25 4D 50 00 00 4F 12 14 00 00 00 00 03 00 00 00 04 00 01 00 0C 00 00 00 00 00 00 01 09 00 06 00 00 00 01 00 00 00 00 08 00 0F 0A 04 03 01 01 00 00 00 00 F7")
QUERY_S4 = hx("F0 21 25 4D 50 00 00 22 11 10 00 00 00 00 03 00 00 00 0A 00 01 00 08 00 00 00 00 00 00 01 05 00 04 00 00 00 00 00 00 01 01 00 00 00 00 F7")
POW_S2_AMPOFF = hx("F0 21 25 4D 50 00 00 25 12 19 00 00 00 00 04 00 00 00 09 00 01 01 01 00 00 00 00 00 00 01 0E 00 01 00 00 00 01 00 00 00 00 00 00 00 01 00 01 00 00 00 00 00 00 00 00 00 00 01 01 00 00 00 00 F7")
LOAD138 = hx("F0 21 25 4D 50 00 00 2B 12 10 00 00 00 00 00 00 00 00 09 00 00 00 08 00 00 00 00 00 00 01 05 08 0A 00 00 00 00 00 00 01 05 08 0A 00 00 00 00 00 00 01 01 00 00 00 00 F7")
LOAD138 = hx("F0 21 25 4D 50 00 00 2B 12 10 00 00 00 00 00 00 00 00 09 00 00 00 08 00 00 00 00 00 00 01 05 08 0A 00 00 00 00 00 00 01 01 00 00 00 00 F7")
GET138 = hx("F0 21 25 4D 50 00 00 23 11 10 00 00 00 00 00 00 00 00 00 00 01 00 08 00 00 00 00 00 00 01 05 08 0A 00 00 00 00 00 00 01 01 00 00 00 00 F7")
SAVE138 = hx("F0 21 25 4d 50 00 00 03 12 21 00 00 00 00 00 00 00 00 00 00 05 01 09 00 00 00 00 00 00 02 06 08 0a 00 00 00 00 00 00 05 00 04 09 05 04 02 0d 05 04 04 05 05 04 04 0f 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 01 01 00 00 00 00 F7")
DUMP_CHUNK2_HEAD = hx("F0 21 25 4D 50 00 00 01 12 64 03 39 01 02 0A 00 0C")


def test_nibbles_roundtrip_float():
    raw = struct.pack("<f", 21.0)
    assert encode_nibbles(raw) == hx("00 00 00 00 0A 08 04 01")
    assert decode_nibbles(encode_nibbles(raw)) == raw


def test_checksum_is_sum_of_bytes_after_offset_field():
    assert checksum(MIX21) == 0x3D
    assert checksum(SCENE2) == 0x10


def test_parse_frame_reads_len_offset_and_payload():
    f = parse_frame(DUMP_CHUNK2_HEAD + b"\x00\x00\xf7")
    assert f.cmd == 0x12 and f.length == 484 and f.offset == 185


def test_parse_frame_payload_matches_captured_param_set():
    f = parse_frame(MIX21)
    assert f == Frame(cmd=0x12, length=20, offset=0, payload=hx("03 00 04 01 0C 00 00 00 19 06 00 00 00 00 00 A8 41 11 00 00"))


def test_build_frame_roundtrips_capture():
    f = parse_frame(MIX21)
    assert build_frame(f.cmd, f.payload) == MIX21


@pytest.mark.parametrize("msg,expected", [
    (msg_scene(2), SCENE2),
    (msg_set_param(slot=6, index=0, value=21.0), MIX21),
    (msg_set_param(slot=6, index=1, value=501.0), TIME501),
    (msg_query_param(slot=4, index=0), QUERY_S4),
    (msg_scene_powers(scene=1, powers=[0, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0]), POW_S2_AMPOFF),
    (msg_load_patch(138), LOAD138),
    (msg_get_patch(138), GET138),
])
def test_builders_reproduce_captures(msg, expected):
    assert msg == expected


def test_save_matches_capture():
    assert msg_save_patch(138, "PIT-TETO") == SAVE138


def test_save_rejects_long_name():
    with pytest.raises(ValueError):
        msg_save_patch(0, "X" * (PATCH_NAME_LEN + 1))


def test_patch_index_from_label():
    assert patch_index("A28-4") == 138
    assert patch_index("A30-3") == 147
    assert patch_label(138) == "A28-4"


def test_query_scene_matches_capture():
    from ampero2.protocol import msg_query_scene
    assert msg_query_scene() == hx("F0 21 25 4D 50 00 00 04 11 08 00 00 00 00 01 00 00 00 00 00 03 00 00 00 00 00 00 00 00 F7")


# --- second capture (2026-09-07, editor actions on scratch patch A26-1) ---
def payload(msg: bytes) -> bytes:
    return parse_frame(msg).payload


@pytest.mark.parametrize("msg,expected", [
    (P.msg_set_model(0, 0, 0x23), "02 00 04 01 0b 00 00 00 18 00 00 23 00 00 00 01 11 00 00"),
    (P.msg_set_model(2, 4, 0x07000000), "02 00 04 01 0b 00 00 00 18 02 04 00 00 00 07 01 11 00 00"),
    (P.msg_set_model(7, 6, 0x09000000), "02 00 04 01 0b 00 00 00 18 07 06 00 00 00 09 01 11 00 00"),
    (P.msg_set_model(8, 9, 0x04000000), "02 00 04 01 0b 00 00 00 18 08 09 00 00 00 04 01 11 00 00"),
    (P.msg_clear_slot(0), "02 00 04 01 0b 00 00 00 18 00 ff ff ff ff ff 01 11 00 00"),
    (P.msg_rename_scene(0, "USBSCN"), "07 00 09 01 10 00 00 00 1d 00 00 00 00 55 53 42 53 43 4e 00 00 11 00 00"),
    (P.msg_set_tempo(121), "02 00 09 01 08 00 00 00 15 00 00 79 00 11 00 00"),
    (P.msg_query_global(1), "00 00 01 00 00 00 00 00"),
    (P.msg_set_global(0x10, 1), "10 00 01 00 05 00 00 00 12 01 11 00 00"),
    (P.msg_set_global(0x09, 1), "09 00 01 00 05 00 00 00 12 01 11 00 00"),
    (P.msg_query_footswitches(), "00 00 03 01 00 00 00 00"),
    (P.msg_set_footswitches([0x1D, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]), "01 00 03 01 0b 00 00 00 18 1d ff ff ff ff ff ff 11 00 00"),
])
def test_second_capture_builders(msg, expected):
    assert payload(msg) == hx(expected)


def test_global_reply_body_strips_header_and_trailer():
    from ampero2.protocol import reply_body
    frame = parse_frame(build_frame(0x12, hx("00 00 01 00 18 00 00 00 25 02 02 01 01 11 00 00")))
    assert reply_body(frame) == hx("02 02 01 01")


@pytest.mark.parametrize("msg,expected", [
    (P.msg_set_patch_volume(99), "01 00 09 01 08 00 00 00 15 00 00 63 00 11 00 00"),
    (P.msg_set_quick_access(0, 4, 4, 0x0700003E, 0), "01 00 02 01 0c 00 00 00 19 00 04 04 3e 00 00 07 00 11 00 00"),
    (P.msg_clear_quick_access(0), "01 00 02 01 0c 00 00 00 19 00 ff ff ff ff ff ff ff 11 00 00"),
    (P.msg_set_exp_target(0, 0, 4, 4, 0x0700003E, 1), "02 00 06 01 0d 00 00 00 1a 00 00 04 04 3e 00 00 07 01 11 00 00"),
    (P.msg_clear_exp_target(0, 0), "02 00 06 01 0d 00 00 00 1a 00 00 ff ff ff ff ff ff ff 11 00 00"),
])
def test_patch_settings_builders(msg, expected):
    assert payload(msg) == hx(expected)


def test_footswitch_function_codes():
    from ampero2.protocol import FOOTSWITCH_FUNCTIONS
    assert FOOTSWITCH_FUNCTIONS["scene 1"] == 0x1B and FOOTSWITCH_FUNCTIONS["scene 3"] == 0x1D
    assert FOOTSWITCH_FUNCTIONS["off"] == 0xFF and FOOTSWITCH_FUNCTIONS["tap tempo"] == 0x0D


def test_template_builders():
    from ampero2.protocol import msg_query_templates, msg_save_template
    assert payload(msg_query_templates()) == hx("04 00 00 02 00 00 00 00")
    assert payload(msg_save_template(1, "USBTPL")) == hx("02 00 00 02 14 00 00 00 21 05 00 00 00 55 53 42 54 50 4c 00 00 00 00 00 00 11 00 00")


def test_classify_unsolicited_patch_dump():
    from ampero2.protocol import is_patch_dump
    assert is_patch_dump(hx("00 00 00 01 c1 01 00 00 00 24 92")) is True
    assert is_patch_dump(hx("03 00 08 00 08 00 00 00 15 01 00 00 00 11 00 00")) is False


def test_load_template_builder():
    from ampero2.protocol import msg_load_template
    assert payload(msg_load_template(1)) == hx("03 00 00 02 08 00 00 00 15 05 00 00 00 11 00 00")


def test_nam_rename_and_delete():
    from ampero2.protocol import msg_delete_nam, msg_rename_nam
    assert payload(msg_rename_nam(2, "usb_red02")) == hx("02 00 00 08 18 00 00 00 25 02 00 00 00 75 73 62 5f 72 65 64 30 32 00 00 00 00 00 00 00 11 00 00")
    assert payload(msg_delete_nam(2)) == hx("01 00 00 08 08 00 00 00 15 02 00 00 00 11 00 00")


def test_global_set_on_other_pages_and_control_functions():
    from ampero2.protocol import msg_set_control_fs_code, msg_set_control_function
    assert payload(P.msg_set_global(0x04, 1, page=8)) == hx("04 00 08 00 05 00 00 00 12 01 11 00 00")
    assert payload(P.msg_set_global(0x06, 2, page=2)) == hx("06 00 02 00 05 00 00 00 12 02 11 00 00")
    assert payload(msg_set_control_function(0, 1)) == hx("01 00 07 00 08 00 00 00 15 00 00 01 00 11 00 00")
    assert payload(msg_set_control_fs_code(1, 0x29)) == hx("02 00 07 00 08 00 00 00 15 01 00 29 00 11 00 00")


def test_global_eq_set_matches_capture():
    from ampero2.protocol import msg_set_global_eq
    assert payload(msg_set_global_eq(10, 3.0)) == hx("02 00 03 00 0c 00 00 00 19 0a 00 00 00 00 00 40 40 11 00 00")
