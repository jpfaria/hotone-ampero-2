import json
import subprocess
import sys

import pytest

from ampero2.catalog import Catalog
from ampero2.resolve import resolve, resolve_strict

CAT = Catalog.load()

GOLDEN = [
    ("AMP", "Marshall JTM45", "Marshell 45"),
    ("AMP", "Marshall JCM800", "Marshell 800"),
    ("AMP", "Fender Deluxe Reverb", "Black Deluxe"),
    ("AMP", "Fender Twin Reverb", "Black Twin"),
    ("AMP", "Vox AC30 top boost", "Voxy 30HW TB"),
    ("AMP", "Mesa Boogie Mark IIC+", "Messe IIC+"),
    ("AMP", "Mesa Dual Rectifier", "Rector Dual V"),
    ("AMP", "Peavey 5150", "Eddie 51"),
    ("AMP", "Dumble Overdrive Special", "Dumbell ODS 1"),
    ("AMP", "Fender Bassman", "Baseman Norm"),
    ("DRV", "Ibanez TS808 Tube Screamer", "Green Drive"),
    ("DRV", "Ibanez TS9", "Green 9"),
    ("DRV", "Klon Centaur", "Faun Drive"),
    ("DRV", "ProCo RAT", "Black Tail"),
    ("DRV", "Fulltone OCD", "Force Drive"),
    ("DRV", "Big Muff", "Big Pie"),
    ("DRV", "Fuzz Face", "Face Fuzz"),
    ("DRV", "Marshall Guv'nor", "Governor"),
    ("DYN", "ISP Decimator", "AI Gate"),
    ("DYN", "Ross compressor", "Comprosso"),
    ("DYN", "Xotic EP Booster", "Enhancer"),
    ("CAB", "Marshall 4x12 Greenback", "UK Green 4x12"),
    ("CAB", "Mesa Rectifier 4x12 oversized", "Rector 4x12 C"),
    ("CAB", "Fender Deluxe Reverb 1x12", "Black Dlx 1x12 A"),
    ("CAB", "Vox AC30 2x12 Alnico Blue", "Voxy 2x12 A"),
    ("MOD", "Arion SCH-1 chorus", "Aozora Chorus"),
]


@pytest.mark.parametrize("category,query,expected", GOLDEN)
def test_golden_top_match(category, query, expected):
    assert resolve(CAT, category, query)[0].name == expected


@pytest.mark.parametrize("category,query", [
    ("AMP", "Kemper Profiler"), ("DRV", "Zvex Fuzz Factory"), ("AMP", ""),
    ("CAB", "Leslie 122"), ("DYN", "Empress Compressor"),
])
def test_unresolved_when_nothing_matches(category, query):
    assert resolve_strict(CAT, category, query) is None


def test_strict_needs_a_clear_winner():
    assert resolve_strict(CAT, "AMP", "Marshall") is None
    assert resolve_strict(CAT, "AMP", "Marshall JTM45") is None            # 45 / 45 Jump tie: say the channel
    assert resolve_strict(CAT, "AMP", "Marshall JTM45 normal channel").name == "Marshell 45"
    assert resolve_strict(CAT, "AMP", "Marshall JCM800").name == "Marshell 800"
    assert resolve_strict(CAT, "AMP", "Dumble Overdrive Special overdrive section on").name == "Dumbell ODS 2"


def test_result_shape_and_limit():
    ms = resolve(CAT, "AMP", "Fender")
    assert len(ms) == 3 and all(0 <= m.score <= 1 for m in ms) and ms[0].score >= ms[1].score
    assert isinstance(ms[0].based_on, str) and ms[0].code > 0


def test_cli_json_and_strict_exit_code():
    out = subprocess.run([sys.executable, "-m", "ampero2", "resolve", "DRV", "Klon Centaur", "--strict", "--json"],
                         capture_output=True, text=True)
    assert out.returncode == 0 and json.loads(out.stdout)[0]["name"] == "Faun Drive"
    bad = subprocess.run([sys.executable, "-m", "ampero2", "resolve", "AMP", "Kemper", "--strict"],
                         capture_output=True, text=True)
    assert bad.returncode == 2 and "unresolved" in bad.stdout + bad.stderr
