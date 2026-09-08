# tone-builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `tone-builder` skill that turns cited gear research into a validated patch on the Ampero II Stage, using `ampero2` (device) and `tone-analyzer` (audio) as tools.

**Architecture:** Two device capabilities are added to the `ampero2` CLI (`resolve` = catalog query, `reamp` = USB audio through the pedal). Everything tone-related lives in `skills/tone-builder/`: `build_patch.py` (research JSON → resolve → gate → plan → apply through the `ampero2` CLI), `analyzer.py` (the only file that knows the `tone-analyzer` CLI), `SKILL.md` + `reference.md`.

**Tech Stack:** Python ≥ 3.10, stdlib only for the skill scripts; `sounddevice` + `soundfile` + `numpy` as the optional `ampero2[reamp]` extra; pytest.

**Spec:** `docs/superpowers/specs/2026-09-07-tone-builder-design.md`

## Global Constraints

- Layer rule: `ampero2` never learns research/policy; the skill never imports `ampero2` internals (subprocess only).
- Slots and knob indices are 0-based; patch labels, scenes, NAM/IR slots 1-based.
- `build_patch.py` never touches `volume`, footswitches, EXP, quick access, Global Settings/EQ.
- Never overwrite a named patch without `--overwrite`.
- EQ block = `Graphic EQ` (10 bands 31 Hz…16 kHz, −12…+12 dB); gains capped ±6 dB; `Level` untouched (50).
- English in code, comments, docs, JSON; chat stays in the user's language.
- After every task: `pytest -q` green, commit.

---

### Task 1: `ampero2 resolve` — catalog query, offline

**Files:**
- Create: `ampero2/resolve.py`
- Modify: `ampero2/cli.py` (docstring "Catalog" block; `main()` — handle offline commands before `with Ampero()`)
- Test: `tests/test_resolve.py`
- Regenerate: `skills/ampero2/reference.md` via `python3 tools/build_reference.py`

**Interfaces:**
- Produces: `resolve(catalog: Catalog, category: str, query: str) -> list[Match]` where `Match(name: str, index: int, code: int, score: float, based_on: str)`, sorted by score desc, max 3; `strict(matches, margin=0.15) -> Match | None` (top must beat runner-up by `margin` and score ≥ 0.5). CLI: `ampero2 resolve CAT "query" [--strict] [--json]`; exit 2 + `unresolved` when strict finds nothing. JSON = `[{"name","index","code","score","based_on"}]` (one element with `--strict`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_resolve.py
import json, subprocess, sys
import pytest
from ampero2.catalog import Catalog
from ampero2.resolve import resolve, strict

CAT = Catalog.load()

GOLDEN = [
    ("AMP", "Marshall JTM45", "Marshell 45"),
    ("AMP", "Marshall JCM800", "Marshell 800"),
    ("AMP", "Fender Deluxe Reverb", "Black Deluxe"),
    ("AMP", "Fender Twin Reverb", "Black Twin"),
    ("AMP", "Vox AC30 top boost", "Voxy 30HW TB"),
    ("AMP", "Mesa Boogie Mark IIC+", "Messe IIC+"),
    ("AMP", "Mesa Dual Rectifier", "Rector Dual M"),
    ("AMP", "Peavey 5150", "Eddie 51"),
    ("AMP", "Dumble Overdrive Special", "Dumbell ODS 2"),
    ("AMP", "Fender Bassman", "Baseman Norm"),
    ("DRV", "Ibanez TS808 Tube Screamer", "Green Drive"),
    ("DRV", "Ibanez TS9", "Green 9"),
    ("DRV", "Klon Centaur", "Faun Drive"),
    ("DRV", "ProCo RAT", "Black Tail"),
    ("DRV", "Fulltone OCD", "Force Drive"),
    ("DRV", "Big Muff", "Big Pie"),
    ("DRV", "Fuzz Face", "Face Fuzz"),
    ("DRV", "Boss DS-1", "Smooth Dist"),
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
    assert strict(resolve(CAT, category, query)) is None


def test_strict_needs_a_clear_winner():
    # "Marshall" alone hits every Marshell model: no margin, not strict.
    assert strict(resolve(CAT, "AMP", "Marshall")) is None
    assert strict(resolve(CAT, "AMP", "Marshall JCM800")).name == "Marshell 800"


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_resolve.py -q`
Expected: ImportError `ampero2.resolve`.

- [ ] **Step 3: Implement `ampero2/resolve.py`**

```python
"""Which catalog model is *based on* a real-world unit (token match on name + based_on)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .catalog import Catalog, Model

# real-world token -> tokens the catalog uses (name and based_on are both searched)
ALIASES: dict[str, tuple[str, ...]] = {
    "marshall": ("marshell", "marshall", "uk"), "fender": ("fender", "tweed", "black", "silver", "brown", "baseman"),
    "vox": ("vox", "voxy"), "mesa": ("mesa", "messe", "rector"), "boogie": ("mesa", "messe", "rector"),
    "rectifier": ("rectifier", "rector"), "bogner": ("bogner", "boger"), "orange": ("orange", "tang"),
    "diezel": ("diezel", "dizzle"), "friedman": ("friedman", "fryman"), "engl": ("engl", "engle"),
    "evh": ("evh", "eddie"), "peavey": ("peavey", "eddie", "5150"), "5150": ("5150", "51", "eddie"),
    "dumble": ("dumble", "dumbell"), "soldano": ("soldano", "soloist"), "ampeg": ("ampeg", "ampage"),
    "klon": ("klon", "faun"), "centaur": ("centaur", "faun"), "rat": ("rat", "rat2", "black tail"),
    "ts808": ("ts-808", "808"), "ts9": ("ts-9", "ts9"), "tubescreamer": ("tube", "screamer"),
    "bigmuff": ("muff", "pie"), "muff": ("muff", "pie"), "fuzzface": ("fuzz", "face"),
    "ds1": ("70's", "distortion"), "ocd": ("ocd",), "decimator": ("decimator",), "ross": ("ross",),
    "jcm800": ("800", "jcm800"), "jcm900": ("900", "jcm900"), "jtm45": ("jtm", "45"), "plexi": ("slp", "plexi", "1959"),
    "deluxe": ("deluxe", "dlx"), "reverb": ("reverb",), "twin": ("twin",), "bassman": ("bassman", "baseman"),
    "ac30": ("ac30", "30hw", "30"), "ac15": ("ac15", "15"), "greenback": ("greenback", "green", "grn"),
    "v30": ("vintage 30", "v30"), "oversized": ("oversized",), "topboost": ("tb", "top boost"),
    "iic+": ("iic+",), "mark": ("mark", "iic+", "iv"), "dual": ("dual",), "overdrive": ("overdrive", "ods"),
    "special": ("special", "ods"), "ods": ("ods",), "ep": ("ep",), "booster": ("booster", "boost"),
}
_STRIP = re.compile(r"[®™*©]|\(.*?\)")
_TOKEN = re.compile(r"[a-z0-9+'-]+")


def _tokens(text: str) -> set[str]:
    text = _STRIP.sub(" ", text.lower()).replace("-", "")
    return set(_TOKEN.findall(text))


def _query_tokens(query: str) -> set[str]:
    q = _tokens(query)
    q |= {t for base in list(q) for t in _tokens(" ".join(ALIASES.get(base, ())))}
    return q


@dataclass(frozen=True)
class Match:
    name: str
    index: int
    code: int
    score: float
    based_on: str


def _score(model: Model, q: set[str]) -> float:
    hay = _tokens(model.name) | _tokens(model.based_on or "")
    hit = len(q & hay)
    if hit == 0:
        return 0.0
    return round(hit / len(q) * 0.7 + hit / max(len(hay), 1) * 0.3, 3)


def resolve(catalog: Catalog, category: str, query: str, limit: int = 3) -> list[Match]:
    q = _query_tokens(query)
    if not q:
        return []
    scored = sorted(((_score(m, q), m) for m in catalog.category(category).models),
                    key=lambda t: (-t[0], t[1].index))
    return [Match(m.name, m.index, m.code, s, (m.based_on or "").strip()) for s, m in scored if s > 0][:limit]


def strict(matches: list[Match], margin: float = 0.15, floor: float = 0.5) -> Match | None:
    if not matches or matches[0].score < floor:
        return None
    if len(matches) > 1 and matches[0].score - matches[1].score < margin:
        return None
    return matches[0]
```

Tune `ALIASES`/`_score` until every golden passes; the goldens are the contract, the
weights are not. Keep unresolved cases unresolved (no alias for kemper/zvex/leslie/empress).

- [ ] **Step 4: Wire the CLI, offline**

In `ampero2/cli.py` `main()`, before `with Ampero() as dev:` add:

```python
    if cmd in ("models", "params", "resolve"):
        return _offline(cmd, args)
```

and the helper (move the existing `models`/`params` branches into it):

```python
def _offline(cmd: str, args: list[str]) -> int:
    import json
    from .resolve import resolve, strict
    cat = Catalog.load()
    if cmd == "models":
        for m in cat.category(args[0]).models:
            print(f"{m.index:3d} 0x{m.code:08X} {m.name:24s} {m.based_on or ''}")
    elif cmd == "params":
        for p in cat.find(args[0], args[1]).params:
            print(f"{p.index:2d} {p.name:16s} default={p.default:>6s} range={p.min}..{p.max} type={p.type}")
    elif cmd == "resolve":
        flags = {a for a in args[2:] if a.startswith("--")}
        matches = resolve(cat, args[0], args[1])
        if "--strict" in flags:
            m = strict(matches)
            if m is None:
                print("unresolved", args[0], repr(args[1]), "candidates:", [x.name for x in matches])
                return 2
            matches = [m]
        if "--json" in flags:
            print(json.dumps([m.__dict__ for m in matches]))
        else:
            for m in matches:
                print(f"{m.score:5.2f} {m.index:3d} {m.name:24s} {m.based_on}")
    return 0
```

Docstring, Catalog block, add:
```
  ampero2 resolve DRV "Klon Centaur"   which models are based on a real unit: score, index, name; --strict = one or exit 2 "unresolved"; --json
```

- [ ] **Step 5: Run tests, regenerate reference, commit**

Run: `pytest -q && python3 tools/build_reference.py && git diff --stat`
Expected: all green, `skills/ampero2/reference.md` shows the new line.

```bash
git add ampero2/resolve.py ampero2/cli.py tests/test_resolve.py skills/ampero2/reference.md
git commit -m "ampero2 resolve: catalog query by real-world gear name (offline, --strict/--json)"
```

---

### Task 2: `ampero2 reamp` — DI through the pedal over USB audio

**Files:**
- Create: `ampero2/reamp.py`
- Modify: `pyproject.toml` (`[project.optional-dependencies] reamp = ["sounddevice>=0.5", "soundfile>=0.12", "numpy>=1.26"]`), `ampero2/cli.py` (offline dispatch + docstring), `README.md` (one line under Covered + the extra)
- Test: `tests/test_reamp.py`

**Interfaces:**
- Produces: `reamp(di: Path, out: Path, *, tail_s=2.0, mono=False, device="Ampero II Stage Audio", stream_factory=None) -> ReampResult(frames: int, rms_db: float)`; raises `NoSignal` (subclass of `RuntimeError`) when the recorded RMS is below −60 dBFS; `DEVICE_RATE = 44100`, `OUT_CHANNEL = 2` (USB Output 3), `IN_CHANNELS = (0, 1)` (USB Input 1/2). CLI: `ampero2 reamp DI.wav OUT.wav [--tail S] [--mono]`, exit 3 on `NoSignal` with the hint "is the patch's input source USB OUT 3/4?".

- [ ] **Step 1: Write the failing tests (fake stream, no hardware)**

```python
# tests/test_reamp.py
import numpy as np
import pytest
import soundfile as sf

from ampero2 import reamp as R


class FakeStream:
    """Duplex stream stand-in: 'processes' by copying the DI channel to both inputs at gain."""
    def __init__(self, gain=0.5, **kw):
        self.kw = kw; self.gain = gain; self.written = []
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def write(self, block):
        self.written.append(block.copy())
    def read(self, n):
        block = self.written.pop(0) if self.written else np.zeros((n, self.kw["channels"][1]), np.float32)
        out = np.zeros((n, self.kw["channels"][0]), np.float32)
        out[:, 0] = out[:, 1] = block[:, R.OUT_CHANNEL] * self.gain
        return out, False


def _di(tmp_path, seconds=1.0, rate=44100):
    t = np.arange(int(rate * seconds)) / rate
    p = tmp_path / "di.wav"
    sf.write(p, (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), rate)
    return p


def test_plays_on_usb_out_3_and_records_in_1_2(tmp_path):
    made = {}
    def factory(**kw):
        made.update(kw); return FakeStream(**kw)
    res = R.reamp(_di(tmp_path), tmp_path / "wet.wav", tail_s=0.5, stream_factory=factory)
    assert made["samplerate"] == 44100 and made["channels"] == (8, 8) and made["device"] == "Ampero II Stage Audio"
    wet, rate = sf.read(tmp_path / "wet.wav")
    assert rate == 44100 and wet.shape[1] == 2 and wet.shape[0] == res.frames == int(44100 * 1.5)
    assert abs(np.abs(wet[:44100, 0]).max() - 0.25) < 0.02       # DI * 0.5 came back on input 1


def test_mono_output_and_resample(tmp_path):
    di = _di(tmp_path, rate=48000)
    R.reamp(di, tmp_path / "wet.wav", tail_s=0.0, mono=True, stream_factory=lambda **kw: FakeStream(**kw))
    wet, rate = sf.read(tmp_path / "wet.wav")
    assert rate == 44100 and wet.ndim == 1 and abs(len(wet) - 44100) <= 2


def test_no_signal_raises(tmp_path):
    with pytest.raises(R.NoSignal):
        R.reamp(_di(tmp_path), tmp_path / "wet.wav", tail_s=0.0, stream_factory=lambda **kw: FakeStream(gain=0.0, **kw))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pip install -e ".[dev,reamp]" && pytest tests/test_reamp.py -q`
Expected: ImportError `ampero2.reamp`.

- [ ] **Step 3: Implement `ampero2/reamp.py`**

```python
"""Play a DI through the pedal and record the result over its USB audio interface.

Routing (manual V1.5.1 pp. 65-69): USB Output 3/4 feeds chain A when the patch's input node
SOURCE is "USB OUT 3/4" (INPUT CH = L -> channel 3); chain A's output is USB Input 1/2.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

DEVICE = "Ampero II Stage Audio"
DEVICE_RATE = 44100
CHANNELS = (8, 8)          # (in, out)
OUT_CHANNEL = 2            # USB Output 3 (0-based)
IN_CHANNELS = (0, 1)       # USB Input 1/2
BLOCK = 2048
SILENCE_DBFS = -60.0


class NoSignal(RuntimeError):
    pass


@dataclass(frozen=True)
class ReampResult:
    frames: int
    rms_db: float


def _load_mono_44k(path: Path) -> np.ndarray:
    data, rate = sf.read(path, dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if rate != DEVICE_RATE:
        n = int(round(len(mono) * DEVICE_RATE / rate))
        mono = np.interp(np.linspace(0, len(mono) - 1, n), np.arange(len(mono)), mono).astype(np.float32)
    return mono


def _default_stream(**kw):
    import sounddevice as sd
    return sd.Stream(dtype="float32", blocksize=BLOCK, **kw)


def reamp(di: Path, out: Path, *, tail_s: float = 2.0, mono: bool = False,
          device: str = DEVICE, stream_factory=None) -> ReampResult:
    factory = stream_factory or _default_stream
    signal = _load_mono_44k(Path(di))
    total = len(signal) + int(tail_s * DEVICE_RATE)
    play = np.zeros((total, CHANNELS[1]), np.float32)
    play[: len(signal), OUT_CHANNEL] = signal
    rec = np.zeros((total, len(IN_CHANNELS)), np.float32)
    with factory(device=device, samplerate=DEVICE_RATE, channels=CHANNELS) as stream:
        for start in range(0, total, BLOCK):
            block = play[start: start + BLOCK]
            stream.write(block)
            got, _ = stream.read(len(block))
            rec[start: start + len(block)] = np.asarray(got)[:, list(IN_CHANNELS)]
    rms = float(np.sqrt(np.mean(rec ** 2)) + 1e-12)
    rms_db = 20 * np.log10(rms)
    if rms_db < SILENCE_DBFS:
        raise NoSignal(f"recorded {rms_db:.1f} dBFS: no signal came back. "
                       "Is the current patch's input source set to USB OUT 3/4?")
    sf.write(Path(out), rec[:, 0] if mono else rec, DEVICE_RATE, subtype="PCM_24")
    return ReampResult(total, round(rms_db, 1))
```

(The fake stream echoes what was just written; the real one has a latency of a few blocks
— the trailing `tail_s` absorbs it and `tone-analyzer` trims leading silence.)

- [ ] **Step 4: Wire the CLI**

`_offline` gains:

```python
    elif cmd == "reamp":
        from pathlib import Path
        try:
            from .reamp import NoSignal, reamp
        except ImportError:
            raise SystemExit('reamp needs the audio extra: pip install "ampero2[reamp]"')
        tail = float(args[args.index("--tail") + 1]) if "--tail" in args else 2.0
        try:
            r = reamp(Path(args[0]), Path(args[1]), tail_s=tail, mono="--mono" in args)
        except NoSignal as e:
            print(e)
            return 3
        print(f"wrote {args[1]}: {r.frames} frames, {r.rms_db} dBFS")
```

Add `"reamp"` to the offline command tuple. Docstring, new block:

```
USB audio (pip install "ampero2[reamp]"; the patch's input node SOURCE must be USB OUT 3/4)
  ampero2 reamp di.wav wet.wav [--tail S] [--mono]   play di.wav into chain A (USB out 3), record chain A (USB in 1/2)
```

- [ ] **Step 5: Run, regenerate, commit**

Run: `pytest -q && python3 tools/build_reference.py`

```bash
git add ampero2/reamp.py ampero2/cli.py pyproject.toml tests/test_reamp.py skills/ampero2/reference.md README.md
git commit -m "ampero2 reamp: DI through the pedal over USB audio (out 3 -> chain A -> in 1/2)"
```

---

### Task 3: Spike — is the input node SOURCE settable over SysEx? (needs the pedal)

**Files:**
- Modify: `docs/protocol.md` (record the finding either way), `skills/ampero2/SKILL.md` ("Not possible over USB" list or a new recipe)
- Maybe create: `ampero2 input-source usb34|input` in `cli.py` + `protocol.py` if the byte is found.

**Interfaces:**
- Produces: a documented answer. If settable: `msg_set_input_source(source: int)` and the CLI command. If not: the fallback in `reference.md` of the tone-builder (Task 6) stays.

- [ ] **Step 1: Capture two images**

```bash
ampero2 load A26-2 && ampero2 dump A26-2 /tmp/src-input.bin
# on the touchscreen: Input node > SOURCE = USB OUT 3/4, INPUT CH = L (do not save)
ampero2 load A26-1 && ampero2 load A26-2   # no: this would drop the edit — instead save first:
# touchscreen: SAVE to A26-2 as REAMP, then:
ampero2 load A26-1 && ampero2 load A26-2 && ampero2 dump A26-2 /tmp/src-usb34.bin
cmp -l /tmp/src-input.bin /tmp/src-usb34.bin
```

- [ ] **Step 2: Decide**

One or two differing bytes in the header/node area → try setting them with the existing
`msg_set_param` path on the input node (slot id of the node is unknown: try the same
message with the differing offset while MIDI Monitor captures what the editor sends when
the SOURCE is changed there — the editor's message is authoritative). Verify with `dump`
after a reload. Any timeout → stop, power-cycle, record "not settable" (README rule).

- [ ] **Step 3: Record and commit**

`docs/protocol.md`: a paragraph "Input node SOURCE" with the offset and the message, or
"not found — set on the screen". `skills/ampero2/SKILL.md`: add the command to the recipes
or "input node source" to the "Not possible over USB" list.

```bash
git add docs/protocol.md skills/ampero2/SKILL.md ampero2/
git commit -m "protocol: input node SOURCE (USB OUT 3/4) — <settable via …|not settable over USB>"
```

---

### Task 4: `build_patch.py` — research JSON → resolve → gate → plan

**Files:**
- Create: `skills/tone-builder/scripts/build_patch.py`, `skills/tone-builder/scripts/__init__.py` (empty)
- Test: `tests/tone_builder/test_build_patch.py`, `tests/tone_builder/conftest.py`, `tests/tone_builder/fixtures/gravity_rhythm.json`

**Interfaces:**
- Consumes: `ampero2 resolve CAT NAME --strict --json` (Task 1) through `Runner.run(args) -> (code, stdout)`; `ampero2 params CAT "Model"` output lines `INDEX NAME default=… range=MIN..MAX`.
- Produces: `load_research(path) -> dict`; `build_plan(research, runner) -> Plan` with `Plan.slots: list[Slot]` (`Slot(slot: int, category: str, model: str, role: str, knobs: list[Knob], provenance: str, sources: list[str])`, `Knob(index: int, name: str, value: float, origin: "research"|"derived"|"default"|"eq")`), `Plan.tempo: int|None`, `Plan.unverified: list[str]`, `Plan.unmapped: list[str]`, `Plan.to_json()`; `BuildError(reason)` with `.reason` in {`unresolved`, `uncited`, `forbidden`, `too_many`, `no_cab`}. `SLOT_ORDER = ["gate","comp","wah","drive","amp","cab","eq","mod","delay","reverb"]`; `EQ_MODEL = ("EQ", "Graphic EQ")`; `KNOB_ALIASES` dict.

- [ ] **Step 1: Fixture + conftest**

```json
// tests/tone_builder/fixtures/gravity_rhythm.json
{ "song": "Gravity", "artist": "John Mayer", "role": "rhythm", "id": "john_mayer_gravity_rhythm",
  "name": "John Mayer - Gravity (rhythm)", "tempo_bpm": 66,
  "amp": { "name": "Dumble Overdrive Special", "brand": "dumble", "params": {"gain": 35, "treble": 55}, "sources": ["https://tonedb.co/x"] },
  "drives": [ { "name": "Ibanez TS808", "brand": "ibanez", "params": {"drive": 20, "level": 60, "unknown_knob": 1}, "provenance": "sourced", "sources": ["https://tonedb.co/x"] } ],
  "cab": null,
  "fx": [ { "type": "gate", "name": "noise gate", "params": {"threshold": 38}, "provenance": "unverified", "sources": [] },
          { "type": "delay", "name": "analog delay", "params": {"time_ms": 454, "feedback": 28, "mix": 30}, "provenance": "derived", "sources": ["https://tonedb.co/x"] } ] }
```

```python
# tests/tone_builder/conftest.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills" / "tone-builder"))
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/tone_builder/test_build_patch.py
import json
from pathlib import Path
import pytest
from scripts import build_patch as B

FIX = Path(__file__).parent / "fixtures"


class RealRunner:
    """Runs the real offline ampero2 CLI (catalog only, no pedal)."""
    def run(self, args):
        import subprocess, sys
        p = subprocess.run([sys.executable, "-m", "ampero2", *args], capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr


@pytest.fixture
def research():
    return B.load_research(FIX / "gravity_rhythm.json")


def test_plan_order_models_and_knobs(research):
    plan = B.build_plan(research, RealRunner())
    roles = [s.role for s in plan.slots]
    assert roles == ["gate", "drive", "amp", "cab", "eq", "delay"]
    assert [s.slot for s in plan.slots] == [0, 1, 2, 3, 4, 5]
    amp = plan.slots[2]; cab = plan.slots[3]; drv = plan.slots[1]; eq = plan.slots[4]
    assert amp.category == "AMP" and amp.model.startswith("Dumbell")
    assert cab.category == "CAB" and cab.provenance == "derived"        # derived from the amp, research had null
    assert {k.name: k.value for k in drv.knobs if k.origin == "research"} == {"Gain": 20, "Volume": 60}
    assert "unknown_knob" in plan.unmapped
    assert eq.model == "Graphic EQ" and all(k.value == 0 for k in eq.knobs if k.name != "Level")
    assert plan.tempo == 66 and "noise gate" in plan.unverified


def test_gate_uncited_block_aborts(research):
    research["fx"].append({"type": "reverb", "name": "spring", "params": {}, "sources": []})
    with pytest.raises(B.BuildError) as e:
        B.build_plan(research, RealRunner())
    assert e.value.reason == "uncited"


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


def test_plan_json_roundtrip(research, tmp_path):
    plan = B.build_plan(research, RealRunner())
    d = json.loads(plan.to_json())
    assert d["slots"][0]["model"] and d["tempo"] == 66 and "unverified" in d
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/tone_builder -q` → ImportError.

- [ ] **Step 4: Implement `build_patch.py` (plan part)**

```python
#!/usr/bin/env python3
"""research JSON -> resolve (ampero2 resolve) -> gate -> plan -> apply (ampero2 CLI).

Stdlib only. Talks to the pedal ONLY through the `ampero2` command line.
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
    """Runs `ampero2 …`; injectable for tests."""
    def run(self, args: list[str]) -> tuple[int, str]:
        p = subprocess.run(["ampero2", *args], capture_output=True, text=True)
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


def _resolve(runner: Runner, categories: list[str], name: str) -> tuple[str, str]:
    for cat in categories:
        code, out = runner.run(["resolve", cat, name, "--strict", "--json"])
        if code == 0:
            m = json.loads(out.strip().splitlines()[-1])[0]
            return cat, m["name"]
    raise BuildError("unresolved", f"{name!r} in {categories}")


_PARAM_LINE = re.compile(r"^\s*(\d+)\s+(.+?)\s+default=\s*(\S+)\s+range=(\S+)\.\.(\S+)")


def _params(runner: Runner, cat: str, model: str) -> list[tuple[int, str, float, float, float]]:
    code, out = runner.run(["params", cat, model])
    if code != 0:
        raise BuildError("unresolved", f"params of {cat} {model!r}: {out.strip()}")
    rows = []
    for line in out.splitlines():
        m = _PARAM_LINE.match(line)
        if m:
            rows.append((int(m[1]), m[2].strip(), _num(m[3]), _num(m[4]), _num(m[5])))
    return rows


def _num(s: str) -> float:
    try:
        return float(s)
    except ValueError:
        return 0.0


def _knobs(runner: Runner, cat: str, model: str, params: dict, unmapped: list[str], origin: str) -> list[Knob]:
    rows = _params(runner, cat, model)
    knobs = []
    for idx, name, default, lo, hi in rows:
        knobs.append(Knob(idx, name, default, "default"))
    by_name = {k.name.lower(): k for k in knobs}
    for key, value in (params or {}).items():
        target = None
        for cand in KNOB_ALIASES.get(key.lower(), (key.lower(),)):
            target = next((k for n, k in by_name.items() if n.startswith(cand)), None)
            if target:
                break
        if target is None:
            unmapped.append(f"{model}.{key}")
            continue
        row = next(r for r in rows if r[0] == target.index)
        target.value = float(min(max(float(value), row[3]), row[4]))
        target.origin = origin
    return knobs


def _cab_from_amp(runner: Runner, amp_based_on: str) -> str | None:
    code, out = runner.run(["resolve", "CAB", amp_based_on, "--strict", "--json"])
    return json.loads(out.strip().splitlines()[-1])[0]["name"] if code == 0 else None


def _based_on(runner: Runner, cat: str, model: str) -> str:
    code, out = runner.run(["resolve", cat, model, "--json"])
    for m in json.loads(out.strip().splitlines()[-1]) if code == 0 else []:
        if m["name"] == model:
            return m["based_on"]
    return model


def build_plan(research: dict, runner: Runner, eq_gains: list[float] | None = None) -> Plan:
    unverified, unmapped, blocks = [], [], []   # blocks: (role, name, cat, model, params, provenance, sources)

    def cite(entry: dict, role: str):
        if role != "gate" and not entry.get("sources"):
            raise BuildError("uncited", f"{role} {entry.get('name')!r} has no source")
        if (entry.get("provenance") or "unverified") == "unverified" and entry.get("params"):
            unverified.append(entry.get("name", role))

    for fx in research.get("fx", []):
        if fx["type"] in FORBIDDEN_TYPES:
            raise BuildError("forbidden", f"{fx['type']} block {fx.get('name')!r}")
    for d in research.get("drives", []):
        cite(d, "drive"); cat, model = _resolve(runner, CATEGORY_FOR["drive"], d["name"])
        blocks.append(("drive", d["name"], cat, model, d.get("params"), d.get("provenance", "unverified"), d["sources"]))
    amp = research["amp"]; cite(amp, "amp")
    acat, amodel = _resolve(runner, CATEGORY_FOR["amp"], amp["name"])
    blocks.append(("amp", amp["name"], acat, amodel, amp.get("params"), amp.get("provenance", "unverified"), amp["sources"]))
    cab = research.get("cab")
    if cab:
        cite(cab, "cab"); ccat, cmodel = _resolve(runner, ["CAB"], cab["name"])
        blocks.append(("cab", cab["name"], ccat, cmodel, cab.get("params"), cab.get("provenance", "unverified"), cab["sources"]))
    else:
        derived = _cab_from_amp(runner, _based_on(runner, acat, amodel))
        if derived is None:
            raise BuildError("no_cab", f"AMP never includes a speaker; no cab researched and none derivable from {amodel!r}")
        blocks.append(("cab", f"cab of {amp['name']}", "CAB", derived, None, "derived", amp["sources"]))
    for fx in research.get("fx", []):
        role = fx["type"]; cite(fx, role)
        cat, model = _resolve(runner, CATEGORY_FOR.get(role, [role.upper()]), fx["name"])
        blocks.append((role, fx["name"], cat, model, fx.get("params"), fx.get("provenance", "unverified"), fx.get("sources", [])))
    blocks.append(("eq", "Graphic EQ", *EQ_MODEL, None, "derived", []))
    if len(blocks) > MAX_SLOTS:
        raise BuildError("too_many", f"{len(blocks)} blocks, the pedal has {MAX_SLOTS} slots")

    blocks.sort(key=lambda b: SLOT_ORDER.index(b[0]))
    slots = []
    for i, (role, name, cat, model, params, prov, sources) in enumerate(blocks):
        origin = "derived" if prov == "derived" else "research"
        knobs = _knobs(runner, cat, model, params, unmapped, origin)
        if role == "eq":
            gains = [max(-EQ_CAP_DB, min(EQ_CAP_DB, g)) for g in (eq_gains or [0.0] * 10)]
            for k, g in zip([k for k in knobs if k.name != "Level"], gains):
                k.value, k.origin = float(g), "eq"
        slots.append(Slot(i, cat, model, role, knobs, prov, list(sources)))
    return Plan(research.get("name", research.get("id", "tone")), slots, research.get("tempo_bpm"), unverified, unmapped)
```

- [ ] **Step 5: Run, iterate until green, commit**

Run: `pytest tests/tone_builder -q`

```bash
git add skills/tone-builder/scripts tests/tone_builder
git commit -m "tone-builder: build_patch plan — research JSON -> ampero2 resolve -> gate -> slots/knobs"
```

---

### Task 5: `build_patch.py --apply` — push the plan through the `ampero2` CLI and verify

**Files:**
- Modify: `skills/tone-builder/scripts/build_patch.py` (add `apply_plan`, `verify_plan`, `main`)
- Test: `tests/tone_builder/test_apply.py`

**Interfaces:**
- Consumes: Task 4 `Plan`; `ampero2 load|model|param|powers|tempo|save|show|patches`.
- Produces: `apply_plan(plan, patch: str, name: str, runner, overwrite=False) -> list[list[str]]` (the command list, in order); `verify_plan(plan, patch, runner) -> list[str]` (mismatches, empty = ok); CLI `build_patch.py --research r.json [--plan out.json] [--eq-gains g,…] [--apply PATCH NAME] [--overwrite] [--ampero2 PATH]`; exit 2 on `BuildError`, 4 on verify mismatch, 5 when the target patch is named and `--overwrite` is absent.

- [ ] **Step 1: Write the failing tests**

```python
# tests/tone_builder/test_apply.py
import pytest
from scripts import build_patch as B
from test_build_patch import RealRunner, FIX


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
    return B.build_plan(B.load_research(FIX / "gravity_rhythm.json"), RealRunner())


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


def test_refuses_named_patch_without_overwrite(plan):
    with pytest.raises(SystemExit) as e:
        B.apply_plan(plan, "A26-2", "GRAVITY", RecordingRunner({"A26-2": "MY-PATCH"}))
    assert e.value.code == 5
    B.apply_plan(plan, "A26-2", "GRAVITY", RecordingRunner({"A26-2": "MY-PATCH"}), overwrite=True)


def test_verify_reads_show_back(plan):
    good = "\n".join(f"  slot {s.slot:2d} {s.category:7s} {s.model:20s} scenes=11111  " +
                     " ".join(f"{k.name}={k.value:g}" for k in s.knobs) for s in plan.slots)
    assert B.verify_plan(plan, "A26-2", RecordingRunner(show=good)) == []
    bad = good.replace(plan.slots[2].model, "Tweed Chap")
    assert any("slot 2" in m for m in B.verify_plan(plan, "A26-2", RecordingRunner(show=bad)))
```

- [ ] **Step 2: Run to verify failure** — `pytest tests/tone_builder/test_apply.py -q` → AttributeError `apply_plan`.

- [ ] **Step 3: Implement**

Append to `build_patch.py`:

```python
def _fmt(v: float) -> str:
    return f"{v:g}"


def apply_plan(plan: Plan, patch: str, name: str, runner: Runner, overwrite: bool = False) -> list[list[str]]:
    cmds: list[list[str]] = [["patches"]]
    code, out = runner.run(cmds[0])
    current = next((line.split(None, 1)[1].strip() if len(line.split(None, 1)) > 1 else ""
                    for line in out.splitlines() if line.startswith(patch + " ")), "")
    if current and not overwrite:
        print(f"{patch} is named {current!r}: pass --overwrite to replace it", file=sys.stderr)
        raise SystemExit(5)
    seq = [["load", patch]]
    used = {s.slot for s in plan.slots}
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


_SHOW = re.compile(r"^\s*slot\s+(\d+)\s+(\S+(?: \S+)?)\s+(.+?)\s+scenes=\S+\s+(.*)$")


def verify_plan(plan: Plan, patch: str, runner: Runner) -> list[str]:
    code, out = runner.run(["show", patch])
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
            if k.origin != "default" and abs(float(got[1].get(k.name, "nan") or "nan") - k.value) > 0.5:
                problems.append(f"slot {s.slot} {k.name}: expected {k.value:g}, got {got[1].get(k.name)}")
    return problems


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--research", required=True, type=Path)
    ap.add_argument("--plan", type=Path)
    ap.add_argument("--eq-gains", help="10 comma-separated dB values for Graphic EQ (31Hz..16kHz), capped ±6")
    ap.add_argument("--apply", nargs=2, metavar=("PATCH", "NAME"))
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--ampero2", default="ampero2")
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
    print(plan.to_json() if not a.plan else f"plan -> {a.plan}")
    if a.apply:
        apply_plan(plan, a.apply[0], a.apply[1], runner, a.overwrite)
        runner.run(["load", "A1-1" if a.apply[0] != "A1-1" else "A1-2"])
        runner.run(["load", a.apply[0]])
        problems = verify_plan(plan, a.apply[0], runner)
        if problems:
            print("VERIFY FAILED\n" + "\n".join(problems), file=sys.stderr)
            return 4
        print(f"applied and verified {a.apply[0]} {a.apply[1]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Make `Runner.run` use `self.exe` (default `"ampero2"`): `subprocess.run([getattr(self, "exe", "ampero2"), *args], …)`.
Also make `_knobs` skip the `Level` knob of the EQ when `eq` sets gains (already done by the `!= "Level"` filter).

- [ ] **Step 4: Run tests, commit**

Run: `pytest -q`

```bash
git add skills/tone-builder/scripts/build_patch.py tests/tone_builder/test_apply.py
git commit -m "tone-builder: build_patch --apply pushes the plan through ampero2 and verifies with show"
```

---

### Task 6: `analyzer.py` — adapter to the `tone-analyzer` CLI

**Files:**
- Create: `skills/tone-builder/scripts/analyzer.py`
- Test: `tests/tone_builder/test_analyzer.py`, `tests/tone_builder/fixtures/fingerprint.json`, `tests/tone_builder/fixtures/diff.json`, `tests/tone_builder/fixtures/eq_match.json`

**Interfaces:**
- Consumes: the `tone-analyzer` CLI (assumed, OpenRig schema): `tone-analyzer analyze REF --out-dir D` → `D/fingerprint.json` (`global.self_floor_pct`, `global.top_octave_dead`, `global.reliable_range_hz`); `tone-analyzer compare REF WET --out-dir D` → `D/diff.json` (`proximity_pct`, `ref_top_octave_dead`); `tone-analyzer eq-match REF WET --gains g,… --bands hz,… --output F` → `{new_gains, proximity_pct}`.
- Produces: `fingerprint(ref, out_dir, run=…) -> dict(self_floor_pct, top_octave_dead, degraded: bool)`; `compare(ref, wet, out_dir) -> dict(proximity_pct, ref_top_octave_dead)`; `eq_match(ref, wet, gains: list[float]) -> list[float]` (10 values, ±6 capped, remapped from N bands by nearest centre when the CLI returns a different count); `within(proximity, floor) -> bool`; `GRAPHIC_EQ_HZ = [31, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]`; `TONE_ANALYZER = os.environ.get("TONE_ANALYZER", "tone-analyzer")`.

- [ ] **Step 1: Fixtures + failing tests**

`fingerprint.json`: `{"schema": 3, "global": {"self_floor_pct": 89.0, "top_octave_dead": false, "reliable_range_hz": [80, 9000]}}`
`diff.json`: `{"proximity_pct": 84.2, "ref_top_octave_dead": false}`
`eq_match.json`: `{"new_gains": [1.0, 2.0, -1.0, 0.0, 3.0, -8.0, 2.0, 1.0], "proximity_pct": 86.0, "bands_hz": [63, 125, 250, 500, 1000, 2000, 4000, 8000]}`

```python
# tests/tone_builder/test_analyzer.py
import json, shutil
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
        seen.append(args); shutil.copy(FIX / "diff.json", Path(out_dir) / "diff.json"); return 0, ""
    A.compare("r.wav", "w.wav", tmp_path, run=run)
    assert seen[0][:3] == ["compare", "r.wav", "w.wav"] and "--out-dir" in seen[0]
```

- [ ] **Step 2: Run to verify failure** — ImportError.

- [ ] **Step 3: Implement**

```python
"""The only file that knows the `tone-analyzer` CLI. Assumed OpenRig schema; adjust here only."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

TONE_ANALYZER = os.environ.get("TONE_ANALYZER", "tone-analyzer")
GRAPHIC_EQ_HZ = [31, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
EQ_CAP_DB = 6.0
WITHIN_MARGIN = 3.0


def _run(args: list[str], out_dir) -> tuple[int, str]:
    p = subprocess.run([TONE_ANALYZER, *args], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def _call(run, args, out_dir, result_name):
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    code, out = run(args, out_dir)
    if code != 0:
        raise SystemExit(f"{TONE_ANALYZER} {' '.join(args)} failed: {out.strip()}")
    return json.loads((Path(out_dir) / result_name).read_text())


def fingerprint(ref, out_dir, run=_run) -> dict:
    fp = _call(run, ["analyze", str(ref), "--out-dir", str(out_dir)], out_dir, "fingerprint.json")
    g = fp.get("global", fp)
    dead = bool(g.get("top_octave_dead", False))
    hi = (g.get("reliable_range_hz") or [0, 20000])[1]
    return {"self_floor_pct": float(g.get("self_floor_pct", 100.0)), "top_octave_dead": dead,
            "degraded": dead or hi < 800}


def compare(ref, wet, out_dir, run=_run) -> dict:
    d = _call(run, ["compare", str(ref), str(wet), "--out-dir", str(out_dir)], out_dir, "diff.json")
    return {"proximity_pct": float(d["proximity_pct"]), "ref_top_octave_dead": bool(d.get("ref_top_octave_dead", False))}


def within(proximity_pct: float, self_floor_pct: float) -> bool:
    return proximity_pct >= self_floor_pct - WITHIN_MARGIN


def _remap(gains: list[float], bands: list[float]) -> list[float]:
    out = []
    for hz in GRAPHIC_EQ_HZ:
        i = min(range(len(bands)), key=lambda j: abs(bands[j] - hz))
        out.append(gains[i])
    return out


def eq_match(ref, wet, gains: list[float], out_dir=".", run=_run) -> list[float]:
    args = ["eq-match", str(ref), str(wet), "--gains", ",".join(f"{g:g}" for g in gains),
            "--bands", ",".join(str(h) for h in GRAPHIC_EQ_HZ), "--output", str(Path(out_dir) / "eq_match.json")]
    r = _call(run, args, out_dir, "eq_match.json")
    new = [float(x) for x in r["new_gains"]]
    if len(new) != len(GRAPHIC_EQ_HZ):
        new = _remap(new, [float(b) for b in r.get("bands_hz", [63, 125, 250, 500, 1000, 2000, 4000, 8000])])
    return [max(-EQ_CAP_DB, min(EQ_CAP_DB, g)) for g in new]
```

- [ ] **Step 4: Run, commit**

```bash
git add skills/tone-builder/scripts/analyzer.py tests/tone_builder
git commit -m "tone-builder: tone-analyzer adapter (fingerprint/compare/eq-match, 10-band remap)"
```

When jpfaria/tone-analyzer lands, re-check its README against this file and fix only here.

---

### Task 7: `SKILL.md` + `reference.md` + plugin wiring

**Files:**
- Create: `skills/tone-builder/SKILL.md`, `skills/tone-builder/reference.md`
- Modify: `skills/ampero2/SKILL.md` (one pointer line), `README.md` (skill list), `.claude-plugin/plugin.json` (version 0.2.0, description mentions both skills), `.claude-plugin/marketplace.json` (description)

**Interfaces:**
- Consumes: everything above by command line.

- [ ] **Step 1: Invoke `superpowers:writing-skills` and `claude-plugin:skill-rules` before writing** (baseline: ask a subagent to "build a tone for Gravity on the Ampero" with only the `ampero2` skill; record what it gets wrong — that is what the skill must prevent).

- [ ] **Step 2: Write `reference.md`** — sections: research JSON schema (copy from the spec, every field explained), knob alias table (`KNOB_ALIASES` verbatim), catalog rules (AMP never includes a speaker; CAB mandatory; `Graphic EQ` bands; forbidden `VOL`/`Limiter`), `build_patch.py` and `analyzer.py` command lines and exit codes (2 build, 4 verify, 5 named patch), the REAMP precondition + fallback as decided in Task 3, the `tone-analyzer` assumed commands.

- [ ] **Step 3: Write `SKILL.md`** (frontmatter `name: tone-builder`, description with the triggers "timbre da X", "preset do Y", "tom da música", "recreate the [song] sound", and "Use ampero2 for anything that is not creating a tone"). Body = the FORM from the spec, as numbered steps with the exact commands:

```
0. Ask once: destination patch (empty, or explicit --overwrite), working REAMP patch, reference WAV?
1. Fingerprint:  tone-analyzer analyze REF.wav --out-dir EVAL/   → floor; degraded → flat path
2. Research (cited, tonedb.co first, then groundguitar, killerrig, musicstrive, guitarchalk, rig rundowns).
   A block needs a NAMED unit or it does not exist (gate excepted). Never from memory.
3. Write EVAL/research/<role>-v<N>.json  (schema in reference.md). Re-walk both directions.
4. python3 ${CLAUDE_PLUGIN_ROOT}/skills/tone-builder/scripts/build_patch.py --research … --plan EVAL/plan.json --apply REAMP NAME
   unresolved → fix the research NAME; never type a model.
5. Validate (reference, not degraded): ampero2 reamp DI.wav EVAL/wet-v<N>.wav → tone-analyzer compare → within?
   Regulate: amp/drive gain knob one step (research params in the JSON), then eq-match → --eq-gains → re-apply → reamp → compare.
   Plateau below floor → report both numbers, stop. Never a different amp model.
6. Persist: ampero2 load REAMP && ampero2 save DEST NAME && ampero2 show DEST. Input source note (fallback).
7. Ear feedback: one complaint → one bounded move → stop.
```

Hard rules block (verbatim list from the spec), red flags table, "what this skill never does" (volume, Global EQ, footswitches, batch, overwrite).

- [ ] **Step 4: Wire the plugin and docs**

`skills/ampero2/SKILL.md`, after the first paragraph: `Want a tone for a song or artist? That is the **tone-builder** skill; this one only talks to the pedal.`
`README.md` "Claude Code plugin": "Two skills: `ampero2` (configure the pedal) and `tone-builder` (research → build → re-amp → measure)."
`plugin.json`: `"version": "0.2.0"`.

- [ ] **Step 5: Verify the skill triggers, commit**

Run: `pytest -q`; then a subagent dry run: "timbre da Gravity na Ampero, sem referência" — it must produce a research JSON, run `build_patch.py --plan`, and stop at the flat-EQ statement without touching the pedal (no `--apply` without a confirmed patch).

```bash
git add skills/tone-builder skills/ampero2/SKILL.md README.md .claude-plugin
git commit -m "tone-builder skill: research -> build_patch -> reamp -> tone-analyzer loop on the Ampero"
```

---

## Self-review

- Spec coverage: `reamp` (T2), `resolve` (T1), input-source spike (T3), research JSON + build/gate/plan (T4), apply/verify + slot policy (T5), analyzer adapter (T6), SKILL/reference/plugin (T7), tests per component (T1–T6), writing-skills gate (T7 step 1). Out-of-scope items untouched.
- Names: `resolve`/`strict`/`Match` (T1) ↔ `_resolve` in T4 parses `--strict --json`; `Runner.run` signature identical in T4/T5; `GRAPHIC_EQ_HZ`/`EQ_CAP_DB` in T6 match `EQ_CAP_DB`/`Graphic EQ` in T4; `verify_plan` parses the exact `show` line format of `cli.py`.
- Assumption flagged: `tone-analyzer` CLI shape (T6 only).
