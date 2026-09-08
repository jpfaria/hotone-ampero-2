from pathlib import Path

from ampero2.namb import upload_image
from ampero2.protocol import frames_for_upload, parse_frame
from ampero2.patch import decode_reply, reassemble

NAMB = (Path(__file__).parent / "fixtures" / "red01.namb").read_bytes()
CAPTURED = Path(__file__).parent / "fixtures" / "nam_upload_image.bin"


def test_upload_image_matches_editor_capture():
    img = upload_image(slot=1, name="bogner_ecstasy_r", namb=NAMB)
    assert img == CAPTURED.read_bytes()


def test_upload_frames_chunk_and_roundtrip():
    img = upload_image(slot=1, name="bogner_ecstasy_r", namb=NAMB)
    frames = frames_for_upload(bytes.fromhex("00000008"), img)
    parsed = [parse_frame(f) for f in frames]
    assert parsed[0].offset == 0 and parsed[1].offset == 183 and all(p.length == parsed[0].length for p in parsed)
    assert decode_reply(reassemble(parsed)) == img


def test_clone_image_matches_editor_capture():
    from ampero2.namb import clone_image
    clo = (Path(__file__).parent / "fixtures" / "ts9.clo").read_bytes()
    assert clone_image(slot=5, name="IBANEZ TS9( A05-", clo=clo) == (Path(__file__).parent / "fixtures" / "clo_upload_image.bin").read_bytes()
