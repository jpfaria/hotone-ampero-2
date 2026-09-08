"""User IRs on the pedal: wav -> normalized 44.1 kHz/24-bit wav (editor dylib) -> 2048-sample upload image."""
from __future__ import annotations

import ctypes
import struct
import wave
from pathlib import Path

from .namb import EDITOR_DYLIB

IR_SAMPLES = 2048
IR_NAME_LEN = 31          # 32-byte field
_NAME_FIELD = 32
USER_IR_BASE = 30         # "User IR 1" is slot 30
_CHECKSUM_MASK = 0xFFFF


def normalize_wav(wav_path: Path, dylib: Path = EDITOR_DYLIB) -> Path:
    """Resample/normalize with the editor's converter; returns the temp wav it writes."""
    if not dylib.exists():
        raise FileNotFoundError(f"editor dylib not found at {dylib}")
    lib = ctypes.CDLL(str(dylib))
    fn = lib.getNormalWav
    fn.argtypes = [ctypes.c_char_p]
    fn.restype = ctypes.c_char_p
    out = fn(str(wav_path).encode())
    if not out:
        raise RuntimeError(f"getNormalWav failed for {wav_path}")
    return Path(out.decode())


def samples_from_wav(path: Path) -> list[int]:
    """First IR_SAMPLES frames as 24-bit signed ints (mono, as written by normalize_wav)."""
    with wave.open(str(path)) as w:
        if w.getsampwidth() != 3 or w.getnchannels() != 1:
            raise ValueError(f"expected mono 24-bit wav, got {w.getparams()}")
        raw = w.readframes(IR_SAMPLES)
    out = []
    for i in range(0, len(raw), 3):
        v = raw[i] | (raw[i + 1] << 8) | (raw[i + 2] << 16)
        out.append(v - (1 << 24) if v & 0x800000 else v)
    return out


def ir_image(slot: int, name: str, samples: list[int]) -> bytes:
    """[slot u32][name 32B][2048 x int32][sum16 of everything before]; slot = USER_IR_BASE + n-1."""
    raw = name.encode("ascii")[:IR_NAME_LEN]
    body = struct.pack("<I", slot) + raw.ljust(_NAME_FIELD, b"\0") + struct.pack(f"<{len(samples)}i", *samples)
    return body + struct.pack("<H", sum(body) & _CHECKSUM_MASK)
