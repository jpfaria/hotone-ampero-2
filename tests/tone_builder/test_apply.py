import sys

import pytest

from scripts import build_patch as B
from test_build_patch import FIX, RealRunner


class RecordingRunner(RealRunner):
    """Real for catalog commands, recorded for pedal commands."""

    def __init__(self, patch_names=None, show=""):
        self.calls, self.names, self.show = [], patch_names or {}, show

    def run(self, args):
        if args[0] in ("resolve", "params"):
            return super().run(args)
        self.calls.append(list(args))
        if args[0] == "patches":
            return 0, "\n".join(f"{k:7s} {v}" for k, v in self.names.items())
        if args[0] == "show":
            return 0, self.show
        return 0, ""


@pytest.fixture
def plan():
    return B.build_plan(B.load_research(FIX / "deluxe_rhythm.json"), RealRunner())


def test_apply_sequence(plan):
    r = RecordingRunner({"A26-2": ""})
    cmds = B.apply_plan(plan, "A26-2", "GRAVITY", r)
    assert cmds[0] == ["patches"] and cmds[1] == ["load", "A26-2"]
    assert ["model", "2", "AMP", plan.slots[2].model] in cmds
    assert ["model", "6", "none"] in cmds and ["model", "11", "none"] in cmds
    assert ["param", "1", "0", "20"] in cmds                      # TS808 Gain=20 from research
    assert ["powers", "1", "1", "1", "1", "1", "1", "1", "0", "0", "0", "0", "0", "0"] in cmds
    assert ["tempo", "66"] in cmds and cmds[-1] == ["save", "A26-2", "GRAVITY"]
    assert not any(c[0] in ("volume", "footswitches", "exp", "quick-access", "global-set", "eq-set") for c in cmds)
    assert r.calls == cmds


def test_refuses_named_patch_without_overwrite(plan):
    with pytest.raises(SystemExit) as e:
        B.apply_plan(plan, "A26-2", "GRAVITY", RecordingRunner({"A26-2": "MY-PATCH"}))
    assert e.value.code == 5
    B.apply_plan(plan, "A26-2", "GRAVITY", RecordingRunner({"A26-2": "MY-PATCH"}), overwrite=True)


def _show(plan):
    return "\n".join(f"  slot {s.slot:2d} {s.category:7s} {s.model:20s} scenes=11111  " +
                     " ".join(f"{k.name}={k.value:g}" for k in s.knobs) for s in plan.slots)


def test_verify_reads_show_back(plan):
    good = _show(plan)
    assert B.verify_plan(plan, "A26-2", RecordingRunner(show=good)) == []
    bad = good.replace(plan.slots[2].model, "Tweed Chap")
    assert any("slot 2" in m for m in B.verify_plan(plan, "A26-2", RecordingRunner(show=bad)))
    wrong_knob = good.replace("Gain=20", "Gain=50")
    assert any("Gain" in m for m in B.verify_plan(plan, "A26-2", RecordingRunner(show=wrong_knob)))


def test_main_plan_only_and_exit_codes(tmp_path, monkeypatch):
    out = tmp_path / "plan.json"
    monkeypatch.setattr(B.Runner, "exe", f"{sys.executable} -m ampero2")
    assert B.main(["--research", str(FIX / "deluxe_rhythm.json"), "--plan", str(out)]) == 0
    assert '"Graphic EQ"' in out.read_text()
    bad = tmp_path / "bad.json"
    bad.write_text((FIX / "deluxe_rhythm.json").read_text().replace("Fender Blackface Deluxe Reverb normal channel", "Kemper"))
    assert B.main(["--research", str(bad)]) == 2
