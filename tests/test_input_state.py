"""Input source is borrowed state: usb34 (re-amp over USB) makes the guitar input silent.
Any code path that switches to it must restore the previous source -- on success, on
exception, and on SIGINT/SIGTERM. See docs/learnings.md and skills/ampero2/SKILL.md."""
import os
import signal

import pytest

from ampero2.state import DoctorReport, RESTORE_HINT, borrowed_input_source, doctor


class FakePort:
    """Stands in for a live Ampero device: in-memory current input source, no MIDI."""

    def __init__(self, initial="input"):
        self.source = initial
        self.sets = []
        self.fail = False

    def get(self):
        return self.source

    def set(self, source):
        if self.fail:
            raise RuntimeError("device unreachable")
        self.sets.append(source)
        self.source = source


def test_switches_to_target_inside_the_block():
    port = FakePort("input")
    with borrowed_input_source(port, "usb34"):
        assert port.get() == "usb34"


def test_restores_on_normal_completion():
    port = FakePort("input")
    with borrowed_input_source(port, "usb34"):
        pass
    assert port.get() == "input"
    assert port.sets == ["usb34", "input"]


def test_restores_on_exception():
    port = FakePort("input")
    with pytest.raises(ValueError):
        with borrowed_input_source(port, "usb34"):
            raise ValueError("boom")
    assert port.get() == "input"


def test_restores_on_sigint():
    port = FakePort("input")
    with pytest.raises(SystemExit):
        with borrowed_input_source(port, "usb34"):
            os.kill(os.getpid(), signal.SIGINT)
    assert port.get() == "input"


def test_restores_on_sigterm():
    port = FakePort("input")
    with pytest.raises(SystemExit):
        with borrowed_input_source(port, "usb34"):
            os.kill(os.getpid(), signal.SIGTERM)
    assert port.get() == "input"


def test_restore_failure_warns_loudly_on_stderr(capsys):
    port = FakePort("input")
    with borrowed_input_source(port, "usb34"):
        port.fail = True
    err = capsys.readouterr().err
    assert "usb34" in err
    assert RESTORE_HINT in err


def test_doctor_detects_silent_pedal():
    report = doctor(FakePort("usb34"))
    assert report.ok is False
    assert RESTORE_HINT in report.describe()


def test_doctor_reports_ok_when_input():
    report = doctor(FakePort("input"))
    assert report == DoctorReport("input", True)
