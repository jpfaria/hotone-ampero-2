import numpy as np
import pytest
import soundfile as sf

from ampero2 import reamp as R


class FakeStream:
    """Duplex stream stand-in: 'processes' by copying the DI channel to both inputs at gain."""

    def __init__(self, gain=0.5, **kw):
        self.kw = kw
        self.gain = gain
        self.written = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def write(self, block):
        self.written.append(np.array(block, copy=True))

    def read(self, n):
        block = self.written.pop(0) if self.written else np.zeros((n, self.kw["channels"][1]), np.float32)
        out = np.zeros((len(block), self.kw["channels"][0]), np.float32)
        out[:, 0] = out[:, 1] = block[:, R.OUT_CHANNEL] * self.gain
        return out, False


def _di(tmp_path, seconds=1.0, rate=44100):
    t = np.arange(int(rate * seconds)) / rate
    p = tmp_path / "di.wav"
    sf.write(p, (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), rate)
    return p


def test_plays_on_usb_out_3_and_records_in_1_2(tmp_path):
    made = {}

    def factory(**kw):
        made.update(kw)
        return FakeStream(**kw)

    res = R.reamp(_di(tmp_path), tmp_path / "wet.wav", tail_s=0.5, stream_factory=factory)
    assert made["samplerate"] == 44100 and made["channels"] == (8, 8) and made["device"] == "Ampero II Stage Audio"
    wet, rate = sf.read(tmp_path / "wet.wav")
    assert rate == 44100 and wet.shape[1] == 2 and wet.shape[0] == res.frames == int(44100 * 1.5)
    assert abs(np.abs(wet[:44100, 0]).max() - 0.25) < 0.02       # DI * 0.5 came back on input 1


def test_mono_output_and_resample(tmp_path):
    di = _di(tmp_path, rate=48000)
    R.reamp(di, tmp_path / "wet.wav", tail_s=0.0, mono=True, stream_factory=lambda **kw: FakeStream(**kw))
    wet, rate = sf.read(tmp_path / "wet.wav")
    assert rate == 44100 and wet.ndim == 1 and abs(len(wet) - 44100) <= 2


def test_no_signal_raises(tmp_path):
    with pytest.raises(R.NoSignal):
        R.reamp(_di(tmp_path), tmp_path / "wet.wav", tail_s=0.0,
                stream_factory=lambda **kw: FakeStream(gain=0.0, **kw))
