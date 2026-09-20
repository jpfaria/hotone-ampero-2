"""`ampero2 reamp` must never leave the pedal on input source usb34: it always restores
the previous source, even on failure. `ampero2 doctor` reports when it didn't.
Never opens a real MIDI port: Ampero and the input-source port are both faked."""
from pathlib import Path

import pytest

import ampero2.cli as cli
from ampero2.reamp import NoSignal, ReampResult


class FakeAmpero:
    """Stands in for device.Ampero: cli.py never calls its SysEx methods directly for
    reamp/doctor because those go through DeviceInputSource, which we also fake below."""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakePort:
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


@pytest.fixture
def fake_device(monkeypatch):
    monkeypatch.setattr(cli, "Ampero", lambda: FakeAmpero())
    port = FakePort("input")
    monkeypatch.setattr(cli, "DeviceInputSource", lambda dev: port)
    return port


def test_reamp_restores_input_source_after_success(fake_device, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "ampero2.reamp.reamp",
        lambda di, out, **kw: ReampResult(100, -10.0),
    )
    rc = cli.main(["ampero2", "reamp", "di.wav", str(tmp_path / "wet.wav")])
    assert rc == 0
    assert fake_device.source == "input"
    assert fake_device.sets == ["usb34", "input"]


def test_reamp_restores_input_source_after_no_signal(fake_device, monkeypatch, tmp_path):
    def boom(di, out, **kw):
        raise NoSignal("silence")

    monkeypatch.setattr("ampero2.reamp.reamp", boom)
    rc = cli.main(["ampero2", "reamp", "di.wav", str(tmp_path / "wet.wav")])
    assert rc == 3
    assert fake_device.source == "input"
    assert fake_device.sets == ["usb34", "input"]


def test_reamp_restores_input_source_after_unexpected_exception(fake_device, monkeypatch, tmp_path):
    def boom(di, out, **kw):
        raise RuntimeError("audio device vanished")

    monkeypatch.setattr("ampero2.reamp.reamp", boom)
    with pytest.raises(RuntimeError):
        cli.main(["ampero2", "reamp", "di.wav", str(tmp_path / "wet.wav")])
    assert fake_device.source == "input"
    assert fake_device.sets == ["usb34", "input"]


def test_doctor_reports_ok(fake_device, capsys):
    rc = cli.main(["ampero2", "doctor"])
    assert rc == 0
    assert "ok" in capsys.readouterr().out


def test_doctor_reports_stuck_on_usb34(fake_device, capsys):
    fake_device.source = "usb34"
    rc = cli.main(["ampero2", "doctor"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "usb34" in out
    assert "ampero2 input-source input" in out
