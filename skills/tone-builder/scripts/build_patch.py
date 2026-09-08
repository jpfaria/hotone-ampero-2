#!/usr/bin/env python3
"""research JSON -> resolve (ampero2 resolve) -> gate -> plan -> apply (ampero2 CLI).

Stdlib only. Talks to the pedal ONLY through the `ampero2` command line; never imports it.
Exit codes: 2 build aborted (see reason), 4 verify mismatch, 5 target patch is named (no --overwrite).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

SLOT_ORDER = ["gate", "comp", "wah", "drive", "amp", "cab", "eq", "mod", "delay", "reverb"]
CATEGORY_FOR = {"gate": ["DYN"], "comp": ["DYN"], "wah": ["WAH"], "drive": ["DRV", "DYN"],
                "amp": ["AMP", "PRE AMP"], "cab": ["CAB"], "mod": ["MOD"], "delay": ["DLY"], "reverb": ["RVB"]}
FORBIDDEN_TYPES = {"volume", "limiter"}
EQ_MODEL = ("EQ", "Graphic EQ")
EQ_CAP_DB = 6.0
MAX_SLOTS = 12
KNOB_ALIASES = {
    "gain": ("gain", "drive", "sustain", "fuzz"), "drive": ("drive", "gain"), "level": ("level", "volume", "output"),
    "volume": ("volume", "level", "output"), "output": ("output", "volume", "level"), "tone": ("tone",),
    "bass": ("bass", "low"), "low": ("low", "bass"), "mid": ("middle", "mid"), "middle": ("middle", "mid"),
    "treble": ("treble", "high"), "high": ("high", "treble"), "presence": ("presence",),
    "time": ("time",), "time_ms": ("time",), "feedback": ("feedback", "repeat"), "repeats": ("feedback", "repeat"),
    "mix": ("mix", "blend"), "blend": ("blend", "mix"), "depth": ("depth",), "rate": ("rate", "speed"),
    "speed": ("speed", "rate"), "threshold": ("threshold",), "attack": ("attack",), "release": ("release",),
}


class BuildError(SystemExit):
    def __init__(self, reason: str, detail: str):
        super().__init__(2)
        self.reason, self.detail = reason, detail

    def __str__(self):
        return f"{self.reason}: {self.detail}"


class Runner:
    """Runs `ampero2 ...`; injectable for tests."""
    exe = "ampero2"

    def run(self, args: list[str]) -> tuple[int, str]:
        p = subprocess.run([self.exe, *args], capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr


@dataclass
class Knob:
    index: int
    name: str
    value: float
    origin: str            # research | derived | default | eq


@dataclass
class Slot:
    slot: int
    category: str
    model: str
    role: str
    knobs: list[Knob]
    provenance: str
    sources: list[str]


@dataclass
class Plan:
    name: str
    slots: list[Slot]
    tempo: int | None
    unverified: list[str] = field(default_factory=list)
    unmapped: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def load_research(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def _last_json(out: str):
    for line in reversed(out.strip().splitlines()):
        if line.startswith("["):
            return json.loads(line)
    return []


def _resolve(runner: Runner, categories: list[str], name: str) -> tuple[str, str]:
    candidates = []
    for cat in categories:
        code, out = runner.run(["resolve", cat, name, "--strict", "--json"])
        if code == 0:
            return cat, _last_json(out)[0]["name"]
        candidates.append(out.strip())
    raise BuildError("unresolved", f"{name!r} in {categories}: " + " | ".join(candidates))


_PARAM_LINE = re.compile(r"^\s*(\d+)\s+(.+?)\s+default=\s*(\S+)\s+range=(\S+)\.\.(\S+)")


def _num(s: str) -> float:
    try:
        return float(s)
    except ValueError:
        return 0.0


def _params(runner: Runner, cat: str, model: str) -> list[tuple[int, str, float, float, float]]:
    code, out = runner.run(["params", cat, model])
    if code != 0:
        raise BuildError("unresolved", f"params of {cat} {model!r}: {out.strip()}")
    rows = []
    for line in out.splitlines():
        m = _PARAM_LINE.match(line)
        if m:
            rows.append((int(m[1]), m[2].strip(), _num(m[3]), _num(m[4]), _num(m[5])))
    return sorted(rows)


def _knobs(runner: Runner, cat: str, model: str, params: dict | None, unmapped: list[str], origin: str) -> list[Knob]:
    rows = _params(runner, cat, model)
    knobs = [Knob(idx, name, default, "default") for idx, name, default, _lo, _hi in rows]
    for key, value in (params or {}).items():
        target = None
        for cand in KNOB_ALIASES.get(key.lower(), (key.lower(),)):
            target = next((k for k in knobs if k.name.lower().startswith(cand)), None)
            if target:
                break
        if target is None:
            unmapped.append(f"{model}.{key}")
            continue
        _i, _n, _d, lo, hi = next(r for r in rows if r[0] == target.index)
        target.value = float(min(max(float(value), lo), hi))
        target.origin = origin
    return knobs


def _based_on(runner: Runner, cat: str, model: str) -> str:
    code, out = runner.run(["resolve", cat, model, "--json"])
    for m in _last_json(out) if code == 0 else []:
        if m["name"] == model:
            return m["based_on"]
    return model


def _cab_from_amp(runner: Runner, amp_based_on: str) -> str | None:
    """The amp's own combo cab: best non-strict CAB match with brand + model both hit (A/B/C variants tie: first)."""
    code, out = runner.run(["resolve", "CAB", amp_based_on, "--json"])
    top = _last_json(out)[:1] if code == 0 else []
    return top[0]["name"] if top and top[0]["hits"] >= 2 else None


def build_plan(research: dict, runner: Runner, eq_gains: list[float] | None = None) -> Plan:
    unverified: list[str] = []
    unmapped: list[str] = []
    blocks = []   # (role, name, cat, model, params, provenance, sources)

    def cite(entry: dict, role: str):
        if role != "gate" and not entry.get("sources"):
            raise BuildError("uncited", f"{role} {entry.get('name')!r} has no source")
        if (entry.get("provenance") or "unverified") == "unverified" and entry.get("params"):
            unverified.append(entry.get("name", role))

    for fx in research.get("fx", []):
        if fx["type"] in FORBIDDEN_TYPES:
            raise BuildError("forbidden", f"{fx['type']} block {fx.get('name')!r}")
    for d in research.get("drives", []):
        cite(d, "drive")
        cat, model = _resolve(runner, CATEGORY_FOR["drive"], d["name"])
        blocks.append(("drive", d["name"], cat, model, d.get("params"), d.get("provenance", "unverified"), d["sources"]))
    amp = research["amp"]
    cite(amp, "amp")
    acat, amodel = _resolve(runner, CATEGORY_FOR["amp"], amp["name"])
    blocks.append(("amp", amp["name"], acat, amodel, amp.get("params"), amp.get("provenance", "unverified"), amp["sources"]))
    cab = research.get("cab")
    if cab:
        cite(cab, "cab")
        ccat, cmodel = _resolve(runner, CATEGORY_FOR["cab"], cab["name"])
        blocks.append(("cab", cab["name"], ccat, cmodel, cab.get("params"), cab.get("provenance", "unverified"), cab["sources"]))
    else:
        derived = _cab_from_amp(runner, _based_on(runner, acat, amodel))
        if derived is None:
            raise BuildError("no_cab", f"AMP never includes a speaker; no cab researched and none derivable from {amodel!r}")
        blocks.append(("cab", f"cab of {amp['name']}", "CAB", derived, None, "derived", list(amp["sources"])))
    for fx in research.get("fx", []):
        role = fx["type"]
        cite(fx, role)
        cat, model = _resolve(runner, CATEGORY_FOR.get(role, [role.upper()]), fx["name"])
        blocks.append((role, fx["name"], cat, model, fx.get("params"), fx.get("provenance", "unverified"), fx.get("sources", [])))
    blocks.append(("eq", "Graphic EQ", *EQ_MODEL, None, "derived", []))
    if len(blocks) > MAX_SLOTS:
        raise BuildError("too_many", f"{len(blocks)} blocks, the pedal has {MAX_SLOTS} slots")

    blocks.sort(key=lambda b: SLOT_ORDER.index(b[0]))
    slots = []
    for i, (role, _name, cat, model, params, prov, sources) in enumerate(blocks):
        origin = "derived" if prov == "derived" else "research"
        knobs = _knobs(runner, cat, model, params, unmapped, origin)
        if role == "eq":
            gains = [max(-EQ_CAP_DB, min(EQ_CAP_DB, float(g))) for g in (eq_gains or [0.0] * 10)]
            for k, g in zip([k for k in knobs if k.name != "Level"], gains):
                k.value, k.origin = g, "eq"
        slots.append(Slot(i, cat, model, role, knobs, prov, list(sources)))
    return Plan(research.get("name", research.get("id", "tone")), slots, research.get("tempo_bpm"), unverified, unmapped)


def _fmt(v: float) -> str:
    return f"{v:g}"


def apply_plan(plan: Plan, patch: str, name: str, runner: Runner, overwrite: bool = False) -> list[list[str]]:
    """Push the plan into PATCH through the ampero2 CLI; returns every command run, in order."""
    cmds: list[list[str]] = [["patches"]]
    _code, out = runner.run(cmds[0])
    current = ""
    for line in out.splitlines():
        parts = line.split(None, 1)
        if parts and parts[0] == patch:
            current = parts[1].strip() if len(parts) > 1 else ""
    if current and not overwrite:
        print(f"{patch} is named {current!r}: pass --overwrite to replace it", file=sys.stderr)
        raise SystemExit(5)
    used = {s.slot for s in plan.slots}
    seq = [["load", patch]]
    for s in plan.slots:
        seq.append(["model", str(s.slot), s.category, s.model])
    for i in range(MAX_SLOTS):
        if i not in used:
            seq.append(["model", str(i), "none"])
    for s in plan.slots:
        for k in s.knobs:
            if k.origin != "default":
                seq.append(["param", str(s.slot), str(k.index), _fmt(k.value)])
    seq.append(["powers", "1", *["1" if i in used else "0" for i in range(MAX_SLOTS)]])
    if plan.tempo:
        seq.append(["tempo", str(int(plan.tempo))])
    seq.append(["save", patch, name[:16]])
    for c in seq:
        code, out = runner.run(c)
        if code != 0:
            raise SystemExit(f"ampero2 {' '.join(c)} failed: {out.strip()}")
    return cmds + seq


_SHOW = re.compile(r"^\s*slot\s+(\d+)\s+(\S+(?: \S+)?)\s+(.+?)\s+scenes=\S+\s*(.*)$")


def verify_plan(plan: Plan, patch: str, runner: Runner) -> list[str]:
    """Read PATCH back with `show` and list every model/knob that differs from the plan."""
    _code, out = runner.run(["show", patch])
    seen = {}
    for line in out.splitlines():
        m = _SHOW.match(line)
        if m:
            vals = dict(kv.split("=", 1) for kv in m[4].split() if "=" in kv)
            seen[int(m[1])] = (m[3].strip(), vals)
    problems = []
    for s in plan.slots:
        got = seen.get(s.slot)
        if got is None or got[0] != s.model:
            problems.append(f"slot {s.slot}: expected {s.model!r}, got {got[0] if got else 'empty'!r}")
            continue
        for k in s.knobs:
            if k.origin == "default":
                continue
            try:
                back = float(got[1][k.name])
            except (KeyError, ValueError):
                back = float("nan")
            if not abs(back - k.value) <= 0.5:
                problems.append(f"slot {s.slot} {k.name}: expected {k.value:g}, got {got[1].get(k.name)}")
    return problems


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--research", required=True, type=Path)
    ap.add_argument("--plan", type=Path, help="write the plan JSON here (default: stdout)")
    ap.add_argument("--eq-gains", help="10 comma-separated dB values for Graphic EQ 31Hz..16kHz, capped ±6")
    ap.add_argument("--apply", nargs=2, metavar=("PATCH", "NAME"), help="push the plan into PATCH and save it as NAME")
    ap.add_argument("--overwrite", action="store_true", help="allow --apply on a patch that already has a name")
    ap.add_argument("--ampero2", default="ampero2", help="ampero2 executable (default: ampero2 on PATH)")
    a = ap.parse_args(argv)
    runner = Runner()
    runner.exe = a.ampero2
    gains = [float(x) for x in a.eq_gains.split(",")] if a.eq_gains else None
    try:
        plan = build_plan(load_research(a.research), runner, gains)
    except BuildError as e:
        print("ABORT", e, file=sys.stderr)
        return 2
    if a.plan:
        a.plan.write_text(plan.to_json())
        print(f"plan -> {a.plan}")
    else:
        print(plan.to_json())
    if plan.unmapped:
        print("unmapped params (ignored):", ", ".join(plan.unmapped), file=sys.stderr)
    if plan.unverified:
        print("unverified params (defaults/guesses):", ", ".join(plan.unverified), file=sys.stderr)
    if a.apply:
        patch, name = a.apply
        apply_plan(plan, patch, name, runner, a.overwrite)
        runner.run(["load", "A1-2" if patch == "A1-1" else "A1-1"])
        runner.run(["load", patch])
        problems = verify_plan(plan, patch, runner)
        if problems:
            print("VERIFY FAILED\n" + "\n".join(problems), file=sys.stderr)
            return 4
        print(f"applied and verified {patch} {name!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
