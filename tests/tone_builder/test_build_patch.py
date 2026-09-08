import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import build_patch as B

FIX = Path(__file__).parent / "fixtures"


class RealRunner:
    """Runs the real offline ampero2 CLI (catalog only, no pedal)."""

    def run(self, args):
        p = subprocess.run([sys.executable, "-m", "ampero2", *args], capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr


@pytest.fixture
def research():
    return B.load_research(FIX / "deluxe_rhythm.json")


def test_plan_order_models_and_knobs(research):
    plan = B.build_plan(research, RealRunner())
    assert [s.role for s in plan.slots] == ["gate", "drive", "amp", "cab", "eq", "delay"]
    assert [s.slot for s in plan.slots] == [0, 1, 2, 3, 4, 5]
    drv, amp, cab, eq = plan.slots[1], plan.slots[2], plan.slots[3], plan.slots[4]
    assert amp.category == "AMP" and amp.model == "Black Deluxe"
    assert cab.model == "Black Dlx 1x12 A" and cab.provenance == "derived"   # research had cab: null
    assert {k.name: k.value for k in drv.knobs if k.origin == "research"} == {"Gain": 20, "Volume": 60}
    assert "Green Drive.unknown_knob" in plan.unmapped
    assert eq.model == "Graphic EQ" and all(k.value == 0 for k in eq.knobs if k.name != "Level")
    assert plan.tempo == 66 and "ISP Decimator noise gate" in plan.unverified


def test_gate_uncited_block_aborts(research):
    research["fx"].append({"type": "reverb", "name": "spring", "params": {}, "sources": []})
    with pytest.raises(B.BuildError) as e:
        B.build_plan(research, RealRunner())
    assert e.value.reason == "uncited"


def test_no_derivable_cab_aborts(research):
    research["amp"]["name"] = "Dumble Overdrive Special overdrive section on"   # no Dumble cab in the catalog
    with pytest.raises(B.BuildError) as e:
        B.build_plan(research, RealRunner())
    assert e.value.reason == "no_cab"


def test_gate_unresolved_aborts(research):
    research["amp"]["name"] = "Kemper Profiler"
    with pytest.raises(B.BuildError) as e:
        B.build_plan(research, RealRunner())
    assert e.value.reason == "unresolved" and "Kemper" in str(e.value)


def test_gate_forbidden_and_too_many(research):
    research["fx"].append({"type": "volume", "name": "volume pedal", "params": {}, "sources": ["x"]})
    with pytest.raises(B.BuildError) as e:
        B.build_plan(research, RealRunner())
    assert e.value.reason == "forbidden"
    research["fx"].pop()
    research["drives"] = [dict(research["drives"][0]) for _ in range(9)]
    with pytest.raises(B.BuildError) as e:
        B.build_plan(research, RealRunner())
    assert e.value.reason == "too_many"


def test_eq_gains_capped(research):
    plan = B.build_plan(research, RealRunner(), eq_gains=[9, -9, 1, 0, 0, 0, 0, 0, 0, 0])
    vals = [k.value for k in plan.slots[4].knobs if k.origin == "eq"]
    assert vals[:3] == [6, -6, 1] and len(vals) == 10


def test_plan_json_roundtrip(research):
    d = json.loads(B.build_plan(research, RealRunner()).to_json())
    assert d["slots"][0]["model"] and d["tempo"] == 66 and "unverified" in d
