from pathlib import Path

from ampero2 import protocol as P
from ampero2.patch import PatchHeader, decompress_patch, parse_header, reassemble
from ampero2.protocol import Frame, build_frame

FIXTURE = bytes.fromhex((Path(__file__).parent / "fixtures" / "patch138.hex").read_text())


def test_reassemble_orders_chunks_by_offset():
    frames = [Frame(0x12, 5, 3, b"de"), Frame(0x12, 5, 0, b"abc")]
    assert reassemble(frames) == b"abcde"


def test_reassemble_rejects_gap():
    import pytest
    with pytest.raises(ValueError):
        reassemble([Frame(0x12, 5, 0, b"ab"), Frame(0x12, 5, 3, b"de")])


def test_decompress_fixture_exposes_name_and_index():
    raw = decompress_patch(FIXTURE)
    hdr = parse_header(raw)
    assert hdr == PatchHeader(index=138, name="PIT-TETO")
    assert len(raw) == 7705


def test_build_frame_chunks_large_payload_with_offsets():
    payload = bytes(range(256)) * 2
    frames = [build_frame(0x12, payload[o:o + 185], offset=o, total=len(payload)) for o in range(0, len(payload), 185)]
    assert len(frames) == 3 and reassemble([P.parse_frame(f) for f in frames]) == payload


def test_parse_patch_image_slots_scenes_tempo():
    from ampero2.patch import parse_image
    img = parse_image(decompress_patch(FIXTURE))
    assert img.header == PatchHeader(index=138, name="PIT-TETO")
    assert img.slot_codes[:6] == [None, 0x03000001, None, 0x06000000, 0x07000035, 0x09000020]
    assert img.slot_codes[6:] == [None] * 6
    assert img.scene_names == ["Scene 1", "Scene 2", "Scene 3", "Scene 4", "Scene 5"]
    assert img.tempos == [120] * 5
    assert img.powers[0][3] is True and img.powers[0][0] is False
    assert img.footswitches == [0xFF] * 7
    assert img.param(scene=0, slot=4, index=0) == 58.0   # AMP slot, first knob


def test_decode_reply_is_lzo_after_len32():
    from ampero2.patch import decode_reply
    reply = bytes.fromhex("05000003 10000000 1d 56312e372e30000000000000 110000".replace(" ", ""))
    assert decode_reply(reply) == b"V1.7.0\0\0\0\0\0\0"


def test_inventory_parsers():
    from ampero2.patch import firmware_version, name_table
    assert firmware_version(b"V1.7.0\0\0\0\0\0\0") == "V1.7.0"
    assert name_table(b"IBANEZ TS9( A05-\0MAYERX DUMB CL\0\0\0", 17) == ["IBANEZ TS9( A05-", "MAYERX DUMB CL"]


def test_parse_global_eq_page():
    from ampero2.patch import parse_global_eq
    page = bytes.fromhex(
        "00000000 00000000 0000a041 8fc2353f 00000000 0000a041 8fc2353f 00000000 0000803f 0000c842 8fc2353f 00004040"
        "0000803f 0000fa43 8fc2353f 00000000 0000803f 0000c844 8fc2353f 00000000 0000803f 00409c45 8fc2353f 00000000"
        "00000000 00409c46 8fc2353f 00000000 00000000 00409c46 8fc2353f 0000c842 00000000 00000000 00000000 0000803f".replace(" ", ""))
    eq = parse_global_eq(page)
    assert eq.enabled is False and eq.level == 100.0
    assert eq.bands["band 1"] == {"enabled": True, "freq": 100.0, "q": 0.71, "gain": 3.0}
    assert eq.bands["low cut"] == {"enabled": False, "freq": 20.0, "q": 0.71}
    assert eq.bands["high cut"]["freq"] == 20000.0


def test_template_names_from_decoded_list():
    from ampero2.patch import template_names
    raw = bytes.fromhex("55534254504c0000a4460020" "55534254504c320001000000" "456d70747900ffff00000000" "456d7074790097 80fba00120".replace(" ", "") + "456d707479000000" "54c7e380")
    assert template_names(raw) == ["USBTPL", "USBTPL2", "Empty", "Empty", "Empty"]
