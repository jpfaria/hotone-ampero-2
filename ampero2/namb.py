"""NAM captures on the pedal: .nam (JSON) -> .namb (binary, converted by the editor's own dylib) -> upload image."""
from __future__ import annotations

import ctypes
import struct
from pathlib import Path

EDITOR_DYLIB = Path("/Applications/Ampero II.app/Contents/Frameworks/HTUSBTools.dylib")
NAM_NAME_LEN = 16          # padded to 20 on the wire
_NAME_FIELD = 20
_CHECKSUM_MASK = 0xFFFF


def convert_nam(nam_path: Path, dylib: Path = EDITOR_DYLIB) -> bytes:
    """Write <nam_path>.namb next to the .nam using the editor's converter and return its bytes."""
    if not dylib.exists():
        raise FileNotFoundError(f"editor dylib not found at {dylib}; install the Ampero II editor to convert .nam files")
    lib = ctypes.CDLL(str(dylib))
    fn = lib.convertNamToNamb
    fn.argtypes = [ctypes.c_char_p]
    fn.restype = ctypes.c_void_p
    fn(str(nam_path).encode())
    out = nam_path.with_suffix(".namb")
    if not out.exists():
        raise RuntimeError(f"converter produced no {out}")
    return out.read_bytes()


def upload_image(slot: int, name: str, namb: bytes) -> bytes:
    """[sum16 of the rest][slot u32][name 20B][1 u32][namb]; slot is 0-based (NAM Slot 2 = 1)."""
    raw = name.encode("ascii")[:NAM_NAME_LEN]
    body = struct.pack("<I", slot) + raw.ljust(_NAME_FIELD, b"\0") + struct.pack("<I", 1) + namb
    return struct.pack("<I", sum(body) & _CHECKSUM_MASK) + body


def clone_image(slot: int, name: str, clo: bytes) -> bytes:
    """CLONE captures (.clo, 'HTSI' header) use the same envelope as NAM uploads; slot 0-based."""
    return upload_image(slot, name, clo)
