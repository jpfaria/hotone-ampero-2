"""Patch MIDI (6 messages sent when the patch loads). Golden vectors captured from the editor
with MIDI Monitor on 2026-09-16; image fixture = A57-1 read from the pedal (msg 1 = ch 1, CC 56, 127)."""
from pathlib import Path

import pytest

from ampero2.patch import PATCH_MIDI_COUNT, PatchMidi, parse_image
from ampero2.protocol import PATCH_MIDI_PC, msg_set_patch_midi


def hx(s: str) -> bytes:
    return bytes(int(x, 16) for x in s.split())


# msg 1: channel 4, CC 0, data 0
CH4 = hx("F0 21 25 4D 50 00 00 27 12 13 00 00 00 00 02 00 00 00 0B 00 01 00 0B 00 00 00 00 00 00 01 08 00 "
         "00 00 00 00 00 00 00 00 03 00 00 00 00 01 01 00 00 00 00 F7")
# msg 2: channel OFF, CC 32, data 0
CC32 = hx("F0 21 25 4D 50 00 00 45 12 13 00 00 00 00 02 00 00 00 0B 00 01 00 0B 00 00 00 00 00 00 01 08 00 "
          "01 00 00 00 00 00 00 0F 0F 02 00 00 00 01 01 00 00 00 00 F7")
# msg 3: channel OFF, PC, data 0
PC = hx("F0 21 25 4D 50 00 00 4C 12 13 00 00 00 00 02 00 00 00 0B 00 01 00 0B 00 00 00 00 00 00 01 08 00 "
        "02 00 00 00 00 00 00 0F 0F 08 00 00 00 01 01 00 00 00 00 F7")


def test_set_patch_midi_channel():
    assert msg_set_patch_midi(1, channel=4, command=0, data=0) == CH4


def test_set_patch_midi_off_cc():
    assert msg_set_patch_midi(2, channel=None, command=32, data=0) == CC32


def test_set_patch_midi_program_change():
    assert msg_set_patch_midi(3, channel=None, command=PATCH_MIDI_PC, data=0) == PC


@pytest.mark.parametrize("kw", [dict(msg=0), dict(msg=7), dict(channel=0), dict(channel=17),
                                dict(command=129), dict(data=128)])
def test_set_patch_midi_rejects_out_of_range(kw):
    args = dict(msg=1, channel=1, command=56, data=127) | kw
    with pytest.raises(ValueError):
        msg_set_patch_midi(args.pop("msg"), **args)


def test_image_exposes_patch_midi():
    img = parse_image((Path(__file__).parent / "fixtures" / "patch_a57_1_midi_cc56.bin").read_bytes())
    assert len(img.patch_midi) == PATCH_MIDI_COUNT
    assert img.patch_midi[0] == PatchMidi(channel=1, command=56, data=127)
    assert all(m.channel is None for m in img.patch_midi[1:])


def test_patch_midi_label():
    assert PatchMidi(1, 56, 127).label() == "ch 1  CC 56  127"
    assert PatchMidi(16, PATCH_MIDI_PC, 5).label() == "ch 16  PC  5"
    assert PatchMidi(None, 0, 0).label() == "off"


def test_cli_patch_midi_set_args():
    from ampero2.cli import _patch_midi_msg
    assert _patch_midi_msg(["1", "4", "cc", "0", "0"]) == CH4
    assert _patch_midi_msg(["3", "off"]) == msg_set_patch_midi(3, None, 0, 0)
    assert _patch_midi_msg(["2", "1", "pc", "7"]) == msg_set_patch_midi(2, 1, PATCH_MIDI_PC, 7)
    with pytest.raises(ValueError):
        _patch_midi_msg(["1", "1", "cc", "56"])
