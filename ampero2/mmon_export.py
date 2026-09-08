"""Export a MIDI Monitor document (.mmon) to text: time, direction, decoded Ampero payload.

The .mmon is a plist whose `messageData` is an NSKeyedArchiver archive of SMSystemExclusiveMessage
objects; `data` there excludes F0/F7. Use it because MIDI Monitor's Copy truncates long SysEx.
"""
from __future__ import annotations

import plistlib
import sys
from dataclasses import dataclass

from .protocol import Frame, parse_frame


@dataclass(frozen=True)
class Captured:
    clock: float
    endpoint: str
    frame: Frame | None   # None when the bytes are not an Ampero data frame (e.g. the connect probe)
    raw: bytes


def _deref(objs, v):
    return objs[v.data] if isinstance(v, plistlib.UID) else v


def load(path: str) -> list[Captured]:
    doc = plistlib.load(open(path, "rb"))
    objs = plistlib.loads(doc["messageData"])["$objects"]
    out = []
    for o in objs:
        if not (isinstance(o, dict) and "$class" in o):
            continue
        if _deref(objs, o["$class"]).get("$classname") != "SMSystemExclusiveMessage":
            continue
        raw = b"\xf0" + _deref(objs, o["data"]) + b"\xf7"
        try:
            frame = parse_frame(raw)
        except ValueError:
            frame = None
        out.append(Captured(o["clockTimeStamp"], _deref(objs, o["originatingEndpoint"]), frame, raw))
    return sorted(out, key=lambda c: c.clock)


if __name__ == "__main__":
    t0 = None
    for c in load(sys.argv[1]):
        t0 = t0 if t0 is not None else c.clock
        arrow = "->" if c.endpoint.startswith("To") else "<-"
        if c.frame is None:
            print(f"{c.clock - t0:8.3f} {arrow} RAW {c.raw.hex(' ')}")
            continue
        f = c.frame
        print(f"{c.clock - t0:8.3f} {arrow} cmd={f.cmd:02X} len={f.length:4d} off={f.offset:4d} {f.payload.hex(' ')}")
