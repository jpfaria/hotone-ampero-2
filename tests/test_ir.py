from pathlib import Path

from ampero2.ir import IR_SAMPLES, ir_image, samples_from_wav

HERE = Path(__file__).parent


def test_ir_image_matches_editor_capture():
    samples = samples_from_wav(HERE / "fixtures" / "ir_normalized.wav")
    assert len(samples) == IR_SAMPLES
    assert ir_image(slot=30, name="tay816_m251_sb1", samples=samples) == (HERE / "fixtures" / "ir_upload_image.bin").read_bytes()
