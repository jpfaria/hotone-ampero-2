"""The only file that knows the `tone-analyzer` CLI (jpfaria/tone-analyzer).

Assumed interface (the OpenRig tone-analyzer schema). When the real CLI differs, fix it HERE only:
  tone-analyzer analyze REF --out-dir D            -> D/fingerprint.json  (global.self_floor_pct, global.top_octave_dead, global.reliable_range_hz)
  tone-analyzer compare REF WET --out-dir D        -> D/diff.json         (proximity_pct, ref_top_octave_dead)
  tone-analyzer eq-match REF WET --gains g,.. --bands hz,.. --output F -> F (new_gains, proximity_pct, bands_hz)
Override the executable with $TONE_ANALYZER.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

TONE_ANALYZER = os.environ.get("TONE_ANALYZER", "tone-analyzer")
GRAPHIC_EQ_HZ = [31, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
DEFAULT_BANDS_HZ = [63, 125, 250, 500, 1000, 2000, 4000, 8000]     # OpenRig's 8 octave centres
EQ_CAP_DB = 6.0
WITHIN_MARGIN = 3.0
DEGRADED_ROLLOFF_HZ = 800


def _run(args: list[str], out_dir) -> tuple[int, str]:
    p = subprocess.run([TONE_ANALYZER, *args], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def _call(run, args: list[str], out_dir, result_name: str) -> dict:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    code, out = run(args, out_dir)
    if code != 0:
        raise SystemExit(f"{TONE_ANALYZER} {' '.join(args)} failed: {out.strip()}")
    return json.loads((Path(out_dir) / result_name).read_text())


def fingerprint(ref, out_dir, run=_run) -> dict:
    """self_floor_pct (the per-song ceiling), top_octave_dead, degraded (-> flat-EQ path, no loop)."""
    fp = _call(run, ["analyze", str(ref), "--out-dir", str(out_dir)], out_dir, "fingerprint.json")
    g = fp.get("global", fp)
    dead = bool(g.get("top_octave_dead", False))
    hi = (g.get("reliable_range_hz") or [0, 20000])[1]
    return {"self_floor_pct": float(g.get("self_floor_pct", 100.0)), "top_octave_dead": dead,
            "degraded": dead or hi < DEGRADED_ROLLOFF_HZ}


def compare(ref, wet, out_dir, run=_run) -> dict:
    d = _call(run, ["compare", str(ref), str(wet), "--out-dir", str(out_dir)], out_dir, "diff.json")
    return {"proximity_pct": float(d["proximity_pct"]), "ref_top_octave_dead": bool(d.get("ref_top_octave_dead", False))}


def within(proximity_pct: float, self_floor_pct: float) -> bool:
    """The acceptance bar: within 3 points of the reference's own self-similarity floor."""
    return proximity_pct >= self_floor_pct - WITHIN_MARGIN


def _remap(gains: list[float], bands: list[float]) -> list[float]:
    """Nearest-centre remap of N band gains onto the 10 Graphic EQ bands."""
    return [gains[min(range(len(bands)), key=lambda j: abs(bands[j] - hz))] for hz in GRAPHIC_EQ_HZ]


def eq_match(ref, wet, gains: list[float], out_dir=".", run=_run) -> list[float]:
    """Next 10 Graphic EQ gains (dB, capped ±6) that move WET's spectral shape toward REF."""
    args = ["eq-match", str(ref), str(wet), "--gains", ",".join(f"{g:g}" for g in gains),
            "--bands", ",".join(str(h) for h in GRAPHIC_EQ_HZ), "--output", str(Path(out_dir) / "eq_match.json")]
    r = _call(run, args, out_dir, "eq_match.json")
    new = [float(x) for x in r["new_gains"]]
    if len(new) != len(GRAPHIC_EQ_HZ):
        new = _remap(new, [float(b) for b in r.get("bands_hz", DEFAULT_BANDS_HZ)])
    return [max(-EQ_CAP_DB, min(EQ_CAP_DB, g)) for g in new]
