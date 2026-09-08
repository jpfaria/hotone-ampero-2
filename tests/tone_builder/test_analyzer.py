import shutil
from pathlib import Path

from scripts import analyzer as A

FIX = Path(__file__).parent / "fixtures"


def fake_run(dest_name):
    def run(args, out_dir):
        shutil.copy(FIX / dest_name, Path(out_dir) / dest_name)
        return 0, ""
    return run


def test_fingerprint_reads_floor_and_degraded(tmp_path):
    fp = A.fingerprint("ref.wav", tmp_path, run=fake_run("fingerprint.json"))
    assert fp["self_floor_pct"] == 89.0 and fp["degraded"] is False


def test_compare_and_within(tmp_path):
    d = A.compare("ref.wav", "wet.wav", tmp_path, run=fake_run("diff.json"))
    assert d["proximity_pct"] == 84.2 and A.within(84.2, 89.0) is False and A.within(86.5, 89.0) is True


def test_eq_match_remaps_to_10_bands_and_caps(tmp_path):
    gains = A.eq_match("ref.wav", "wet.wav", [0.0] * 10, out_dir=tmp_path, run=fake_run("eq_match.json"))
    assert len(gains) == 10 and gains[1] == 1.0 and gains[6] == -6.0 and gains[0] == gains[1]  # 31 Hz takes 63 Hz's value


def test_command_lines(tmp_path):
    seen = []

    def run(args, out_dir):
        seen.append(args)
        shutil.copy(FIX / "diff.json", Path(out_dir) / "diff.json")
        return 0, ""

    A.compare("r.wav", "w.wav", tmp_path, run=run)
    assert seen[0][:3] == ["compare", "r.wav", "w.wav"] and "--out-dir" in seen[0]
