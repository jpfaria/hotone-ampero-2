"""Input source is borrowed state.

Chain A input node SOURCE must be "input" for normal playing; "usb34" (re-amp over
USB) makes the pedal ignore the guitar and go silent. Any code path that needs usb34
(currently only `ampero2 reamp`) MUST go through `borrowed_input_source`, which snapshots
the previous source, switches to the target, and restores the snapshot on the way out --
on normal completion, on an exception, and on SIGINT/SIGTERM. Nothing in this codebase
should call a raw setter to reach usb34 outside of this context manager.

Incident (2026-09-19/20): after a re-amp flow left a patch on usb34, the pedal's output
was silent and it took the user an hour to find why. This module exists so that can't
happen again without a bug in this file specifically.
"""
from __future__ import annotations

import signal
import struct
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol

from .patch import decompress_patch, parse_image
from .protocol import msg_get_patch, msg_query_global, msg_set_input_source, reply_body

RESTORE_HINT = "ampero2 input-source input"

_RESTORE_SIGNALS = (signal.SIGINT, signal.SIGTERM)


class InputSourcePort(Protocol):
    def get(self) -> str: ...
    def set(self, source: str) -> None: ...


class DeviceInputSource:
    """Adapts a live `Ampero` device (device.py) to the get/set port above."""

    def __init__(self, dev):
        self.dev = dev

    def get(self) -> str:
        index = struct.unpack("<I", reply_body(self.dev.request(msg_query_global(9))))[0]
        img = parse_image(decompress_patch(self.dev.request_dump(msg_get_patch(index))))
        return img.input_source

    def set(self, source: str) -> None:
        self.dev.send(msg_set_input_source(source))


@contextmanager
def borrowed_input_source(port: InputSourcePort, target: str = "usb34"):
    """Snapshot `port`'s current source, switch to `target` for the block, restore after.

    Restores in `finally` (covers normal return and any exception) and also on
    SIGINT/SIGTERM, so a killed process never leaves the pedal on `target`. If the
    restore write itself fails, prints a loud warning with the exact fix command --
    the caller's own exception/exit still proceeds.
    """
    previous = port.get()
    port.set(target)
    restored = False

    def restore() -> None:
        nonlocal restored
        if restored:
            return
        restored = True
        try:
            port.set(previous)
        except Exception:
            print(
                f"WARNING: failed to restore input source after re-amp. "
                f"The pedal is left on {target!r} and the guitar input is silent. "
                f"Fix: `{RESTORE_HINT}`",
                file=sys.stderr,
            )

    old_handlers = {sig: signal.getsignal(sig) for sig in _RESTORE_SIGNALS}

    def handle_signal(signum, frame):
        restore()
        for sig, old in old_handlers.items():
            signal.signal(sig, old)
        raise SystemExit(128 + signum)

    for sig in _RESTORE_SIGNALS:
        signal.signal(sig, handle_signal)
    try:
        yield previous
    finally:
        for sig, old in old_handlers.items():
            signal.signal(sig, old)
        restore()


@dataclass(frozen=True)
class DoctorReport:
    input_source: str
    ok: bool

    def describe(self) -> str:
        if self.ok:
            return "input source: input (ok)"
        return (f"input source: {self.input_source} -- pedal is silent for normal playing. "
                f"Fix: `{RESTORE_HINT}`")


def doctor(port: InputSourcePort) -> DoctorReport:
    """Reads the current patch's input source and reports whether it leaves the pedal silent."""
    source = port.get()
    return DoctorReport(source, source == "input")
