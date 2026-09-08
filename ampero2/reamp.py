"""Play a DI through the pedal and record the result over its USB audio interface.

Routing (Ampero II Stage manual, firmware V1.5.1, pp. 65-69): USB Output 3/4 feeds chain A
when the patch's input node SOURCE is "USB OUT 3/4" (INPUT CH = L -> channel 3); chain A's
output (after slot A6) is USB Input 1/2. Needs the `reamp` extra: pip install "ampero2[reamp]".
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

DEVICE = "Ampero II Stage Audio"
DEVICE_RATE = 44100
CHANNELS = (8, 8)          # (in, out)
OUT_CHANNEL = 2            # USB Output 3 (0-based)
IN_CHANNELS = (0, 1)       # USB Input 1/2
BLOCK = 2048
SILENCE_DBFS = -60.0


class NoSignal(RuntimeError):
    pass


@dataclass(frozen=True)
class ReampResult:
    frames: int
    rms_db: float


def _load_mono_44k(path: Path) -> np.ndarray:
    data, rate = sf.read(path, dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if rate != DEVICE_RATE:
        n = int(round(len(mono) * DEVICE_RATE / rate))
        mono = np.interp(np.linspace(0, len(mono) - 1, n), np.arange(len(mono)), mono).astype(np.float32)
    return mono


def _default_stream(**kw):
    import sounddevice as sd
    return sd.Stream(dtype="float32", blocksize=BLOCK, **kw)


def reamp(di: Path, out: Path, *, tail_s: float = 2.0, mono: bool = False,
          device: str = DEVICE, stream_factory=None) -> ReampResult:
    factory = stream_factory or _default_stream
    signal = _load_mono_44k(Path(di))
    total = len(signal) + int(tail_s * DEVICE_RATE)
    play = np.zeros((total, CHANNELS[1]), np.float32)
    play[: len(signal), OUT_CHANNEL] = signal
    rec = np.zeros((total, len(IN_CHANNELS)), np.float32)
    with factory(device=device, samplerate=DEVICE_RATE, channels=CHANNELS) as stream:
        for start in range(0, total, BLOCK):
            block = play[start: start + BLOCK]
            stream.write(block)
            got, _ = stream.read(len(block))
            rec[start: start + len(block)] = np.asarray(got)[: len(block), list(IN_CHANNELS)]
    rms = float(np.sqrt(np.mean(rec ** 2)) + 1e-12)
    rms_db = 20 * float(np.log10(rms))
    if rms_db < SILENCE_DBFS:
        raise NoSignal(f"recorded {rms_db:.1f} dBFS: no signal came back. "
                       "Is the current patch's input source set to USB OUT 3/4?")
    sf.write(Path(out), rec[:, 0] if mono else rec, DEVICE_RATE, subtype="PCM_24")
    return ReampResult(total, round(rms_db, 1))
