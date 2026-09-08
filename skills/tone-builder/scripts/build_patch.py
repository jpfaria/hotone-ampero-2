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
