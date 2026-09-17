"""Input node SOURCE of chain A, captured 2026-09-17 from the Ampero II editor with MIDI Monitor
(A58-2, Source Input -> USB Out 3/4) and verified live by setting it back and forth over USB."""
from pathlib import Path

import pytest

from ampero2.patch import parse_image
from ampero2.protocol import INPUT_SOURCES, msg_set_input_source

FIX = Path(__file__).parent / "fixtures"
# the editor's frame, byte for byte (MIDI Monitor, 46 bytes)
EDITOR_USB34 = bytes.fromhex(
    "F0 21 25 4D 50 00 00 19 12 10 00 00 00 00 01 00 00 00 05 00 01 00 08 00 00 00 00 00 00 01 05 00"
    " 00 00 00 00 02 00 00 01 01 00 00 00 00 F7".replace(" ", ""))


def test_message_matches_the_editor():
    assert msg_set_input_source("usb34") == EDITOR_USB34


def test_sources():
    assert INPUT_SOURCES == {"input": 0, "fx-return": 1, "usb34": 2}


def test_unknown_source_is_refused():
    with pytest.raises(ValueError):
        msg_set_input_source("usb56")


def test_image_reads_the_source():
    assert parse_image((FIX / "patch_input_source_input.bin").read_bytes()).input_source == "input"
    assert parse_image((FIX / "patch_input_source_usb34.bin").read_bytes()).input_source == "usb34"
