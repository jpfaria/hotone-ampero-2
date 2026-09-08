"""USB-MIDI transport for the Ampero II Stage (mido/rtmidi)."""
from __future__ import annotations

import time

import mido

from .patch import reassemble
from .protocol import CMD_DATA, Frame, parse_frame

PORT_NAME = "Ampero II Stage MIDI"
_POLL_S = 0.01


class Ampero:
    def __init__(self, port_name: str = PORT_NAME):
        self._in = mido.open_input(port_name)
        self._out = mido.open_output(port_name)

    def close(self) -> None:
        self._in.close()
        self._out.close()

    def __enter__(self) -> "Ampero":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def send(self, frame: bytes) -> None:
        self._out.send(mido.Message("sysex", data=frame[1:-1]))

    def receive(self, timeout: float = 1.0) -> Frame | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for m in self._in.iter_pending():
                if m.type == "sysex":
                    return parse_frame(bytes(m.bytes()))
            time.sleep(_POLL_S)
        return None

    def request(self, frame: bytes, timeout: float = 1.0) -> Frame:
        self.send(frame)
        reply = self.receive(timeout)
        if reply is None:
            raise TimeoutError("no reply from Ampero")
        return reply

    def send_frames(self, frames: list[bytes], timeout: float = 5.0) -> Frame:
        """Send a chunked upload and return the pedal's acknowledgement frame."""
        for f in frames:
            self.send(f)
        reply = self.receive(timeout)
        if reply is None:
            raise TimeoutError("no acknowledgement after upload")
        return reply

    def request_dump(self, frame: bytes, timeout: float = 2.0) -> bytes:
        """Send a query whose answer is a chunked 0x12 dump; returns the reassembled payload."""
        self.send(frame)
        first = self.receive(timeout)
        if first is None or first.cmd != CMD_DATA:
            raise TimeoutError("no dump from Ampero")
        chunks = [first]
        while sum(len(c.payload) for c in chunks) < first.length:
            nxt = self.receive(timeout)
            if nxt is None:
                raise TimeoutError(f"dump stalled after {len(chunks)} chunks")
            chunks.append(nxt)
        return reassemble(chunks)
