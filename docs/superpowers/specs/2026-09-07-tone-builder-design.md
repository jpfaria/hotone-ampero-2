# tone-builder — design

Date: 2026-09-07. Status: approved in chat, pending spec review.

## Goal

A second skill in this repo's plugin, **`tone-builder`**, that creates a tone for a song/artist on
the Hotone Ampero II Stage. It ports the OpenRig tone-builder FORM (research → research
JSON → deterministic build → measured validation → persist) and uses two tools it does not
own:

- **`ampero2`** — the device layer (this repo). Reads/writes the pedal.
- **`tone-analyzer`** — the audio layer (jpfaria/tone-analyzer, built in parallel by
  another agent). Fingerprint / compare / eq-match, pure functions on WAV files.

## Two layers, never mixed

| Layer | Owns | Does NOT own |
|---|---|---|
| `ampero2` (device) | SysEx, patches, knobs, models, catalog queries, USB audio through the pedal (`reamp`) | research, gear policy, build loop, EQ regulation, slot policy |
| `tone-builder` (tone) | research, research JSON, gear resolution policy, build plan, validation loop, persistence policy, the skill | any SysEx, any audio DSP |

The tone-builder shells out to the two CLIs. It never imports `ampero2` internals.

## Changes to `ampero2` (device capabilities only)

### `ampero2 reamp DI.wav OUT.wav [--tail S] [--mono]`

Plays `DI.wav` into the pedal and records the processed output, over the pedal's own USB
audio interface ("Ampero II Stage Audio", 8 in / 8 out, 44.1 kHz). Manual (firmware
V1.5.1, pp. 65–69) routing:

- USB **Output 3/4** → chain A input, when the patch's input node `SOURCE = USB OUT 3/4`
  (`INPUT CH = L` → channel 3).
- USB **Input 1/2** ← chain A output (after slot A6).
- USB Input 7/8 = dry input jacks (not used here).

Implementation: one duplex `sounddevice` stream on that device; DI (mono, resampled to
44.1 kHz if needed) written to output channel index 2, input channels 0–1 captured;
`OUT.wav` = stereo 44.1 kHz 24-bit (or mono `--mono` = channel 0). Length = DI length +
`--tail` (default 2 s). Optional extra `pip install "ampero2[reamp]"` =
`sounddevice`, `soundfile`, `numpy`. Errors: device not found → clear message; sample
rate mismatch → resample DI, never change the device rate.

**Precondition — input node source.** `SOURCE` is a per-patch input-node setting.
`docs/protocol.md` records that chain topology is not settable over USB; whether the
input node source is, is unknown. Plan step (spike, needs the pedal): dump a patch with
`SOURCE = Input`, switch it to `USB OUT 3/4` on the touchscreen, dump again, diff the
7705-byte image. If the byte is found and writable through the existing knob/param path
→ `ampero2 input-source usb34|input`. If not → documented fallback: the user prepares one
working patch ("REAMP", slot chosen by the user) with `SOURCE = USB OUT 3/4` once, on the
screen; the tone-builder always builds inside that patch and copies the result to the
destination slot at the end (the destination keeps `SOURCE = USB OUT 3/4` — the user
flips it on the screen when saving; the skill says so plainly). `reamp` itself only
checks that audio comes back (RMS above a floor) and otherwise reports "no signal:
is the patch's input source USB OUT 3/4?".

### `ampero2 resolve CAT "Marshall JTM 45"` (catalog query)

Which catalog model is *based on* a real-world unit. Deterministic token match against
`name` + `based_on` (strip ®™*, lowercase, brand aliases such as marshall/marshell,
fender/tweed|black|silver, vox/voxy, mesa|boogie/messe|rector, bogner/boger, orange/tang,
diezel/dizzle, friedman/fryman, engl/engle, evh/eddie, dumble/dumbell, ibanez ts/green,
klon/faun, rat/black tail…). Output: top 3 `{index, name, score, based_on}`; `--strict`
prints exactly one when the top score clears the runner-up by a margin, otherwise exits
2 with `unresolved`. `--json` for machine use. No policy here: it answers "what matches",
not "what to use".

## The `tone-builder` skill

Second skill of the same `ampero2` plugin (one plugin, two skills: `ampero2` = configure
the pedal, `tone-builder` = create a tone). Layout:

```
skills/ampero2/                         (unchanged)
skills/tone-builder/SKILL.md
skills/tone-builder/reference.md        (research JSON schema, knob alias map, catalog rules)
skills/tone-builder/scripts/build_patch.py   (stdlib only; shells out to `ampero2`)
skills/tone-builder/scripts/analyzer.py      (adapter to the `tone-analyzer` CLI)
tests/tone_builder/                     (pytest, alongside the ampero2 tests)
```

The `ampero2` skill stays about the device; nothing about research or tones goes into it.
`skills/ampero2/SKILL.md` gains one line pointing "want a tone for a song → tone-builder".

### Research JSON (hand-authored by the agent, the ONLY judgment input)

Same schema as OpenRig's, so research is reusable across devices:

```json
{ "song": "...", "artist": "...", "role": "rhythm", "id": "slug", "name": "Artist - Song (rhythm)",
  "tempo_bpm": 120,
  "amp":    { "name": "Marshall JTM45", "brand": "marshall", "sources": ["<url>"] },
  "drives": [ { "name": "Ibanez TS9", "brand": "ibanez", "params": {"gain": 40}, "provenance": "sourced", "sources": ["<url>"] } ],
  "cab":    { "name": "Marshall 4x12 Greenback", "sources": ["<url>"] } | null,
  "fx":     [ { "type": "gate|comp|mod|delay|reverb|wah|eq", "name": "...", "params": {...},
                "provenance": "sourced|derived|unverified", "sources": [] } ] }
```

Model names and slot numbers never appear in it.

### `build_patch.py`

`build_patch.py --research r.json [--apply PATCH NAME] [--plan out.json] [--eq-gains g1..g10]`

1. **Resolve** every element with `ampero2 resolve --strict --json`: amp → `AMP` (then
   `PRE AMP`), drives → `DRV` (boosts also `DYN`), cab → `CAB`, fx by type → `DYN` (gate,
   comp), `MOD`, `DLY`, `RVB`, `WAH`, `EQ`. Any `unresolved` → abort, exit 2, listing the
   names. The agent fixes the research; it never types a model name.
2. **Gate** (abort with the reason):
   - a block whose `sources` is empty, except the noise gate;
   - `VOL` or `Limiter` anywhere;
   - more than 12 blocks;
   - amp resolved in `AMP`/`PRE AMP` with no cab → **Ampero rule: AMP never includes a
     speaker, a CAB is mandatory.** If the research names none, derive it from the amp's
     own combo (`resolve CAB` with the amp's `based_on` amp name; e.g. Deluxe Reverb →
     "Black Dlx 1x12 A") with `provenance: derived`; if that also fails → abort.
3. **Plan**: slot order gate → comp → wah → drive(s) → amp → cab → EQ → mod → delay →
   reverb, slots 0..n. Knobs by **name**: the research `params` keys map to the model's
   knob `Name` case-insensitively with a small alias table (`gain|drive`, `level|volume|
   output`, `tone`, `bass|low`, `mid|middle`, `treble|high`, `presence`, `time|time_ms`,
   `feedback|repeats`, `mix|blend`, `depth`, `rate|speed`, `threshold`); unmapped keys are
   reported, never guessed; unset knobs stay at the catalog default. Delay `time_ms` is
   derived from `tempo_bpm` when the research gives a note value. The EQ block is always
   `Graphic EQ` (10 bands 31 Hz…16 kHz, knobs −12…+12 dB, `Level` left at 50), all 0 dB
   unless `--eq-gains` is passed (capped ±6 dB). Scene 1 powers: every planned slot on. Output: `plan.json` = slots, models,
   knob (index, value, source-of-value), provenance list, unverified list, tempo.
4. **Apply** (`--apply PATCH NAME`): `ampero2 load PATCH`, `model` per slot (`none` for
   the rest), `param` per knob, `powers 1 …`, `tempo`, `save PATCH NAME`, then `load`
   another patch + `load PATCH` + `show PATCH` and check every model/knob came back.
   Never touches `volume`, footswitches, EXP, quick access or global settings.

### `analyzer.py` (adapter)

The only file that knows the `tone-analyzer` CLI. Assumed interface (OpenRig schema),
to be confirmed against the real repo when it lands:

- `tone-analyzer analyze ref.wav --out-dir D` → `fingerprint.json` with
  `self_floor_pct`, `top_octave_dead`, `reliable_range_hz`.
- `tone-analyzer compare ref.wav wet.wav --out-dir D` → `diff.json` with
  `proximity_pct`, `ref_top_octave_dead`.
- `tone-analyzer eq-match ref.wav wet.wav --gains g1,…,gN --bands 31,63,…,16000` →
  `new_gains`, `proximity_pct`. (Band centres must be parameterisable; if the real CLI
  cannot, the adapter maps its 8 octave gains onto the 10 Graphic EQ bands by nearest
  centre and says so in the report.)

Exposes `fingerprint(ref)`, `compare(ref, wet)`, `eq_match(ref, wet, gains)` returning
dicts; `within(proximity, floor) = proximity >= floor - 3`.

### SKILL.md — the FORM on the Ampero

1. **Ask once up front:** destination patch (must be empty or explicitly confirmed —
   never overwrite a named patch silently), the working REAMP patch, and whether a
   reference WAV exists.
2. **Fingerprint** the reference (isolated guitar only; a full mix or a wrong-instrument
   stem is refused and explained). Degraded (`top_octave_dead` / low rolloff) → flat
   path.
3. **Research** the rig for THIS song, cited, `tonedb.co` first then the ladder. Every
   element. A block needs a NAMED unit or it does not exist (gate excepted). Never from
   memory.
4. **Write the research JSON**; re-walk it element by element in both directions.
5. **Build**: `build_patch.py --research … --apply REAMP …`. `unresolved` → fix the
   research.
6. **Validate** (reference present, not degraded): `ampero2 reamp DI.wav wet.wav` with the
   bundled DI (the tone-analyzer's fixture DI or the user's; the skill never asks the user
   to record one), `compare`, then regulate — amp/drive gain knobs first (one step at a
   time on the researched model, never a different model), then `eq-match` → `--eq-gains`
   → re-apply → `reamp` → `compare` — until `within`; plateau below the floor → report
   both numbers, stop. Reference-less or degraded: **flat EQ, no loop**, say so.
7. **Persist**: `ampero2 load REAMP && ampero2 save DEST NAME`, then `show DEST`. Tell the
   user to set the input source back to `Input` on the screen if the fallback is in use.
8. **Ear feedback**: one explicit complaint → one bounded move (≈ ±2–3 dB on one band, or
   one gain-knob step, or one researched cab swap), then stop.

Hard rules carried over verbatim in spirit: no invented block; no EQ by ear; never touch
patch `volume` or Global EQ; one tone per run; never batch; report `unverified` params;
`ampero2 show` is the source of truth. Ampero-specific: CAB mandatory after AMP/PRE AMP;
slots and knob indices are 0-based; a knob set on scene 1 propagates to all scenes.

## Testing

- `ampero2 resolve`: golden table (≥ 20 real-world names → expected model, incl. brand
  aliases) and ≥ 5 `unresolved` cases; no hardware.
- `ampero2 reamp`: channel mapping and WAV writing against a fake `sounddevice` stream;
  a "no signal" detection test.
- `build_patch.py`: research JSON → plan goldens; each gate failure; knob alias map;
  cab derivation; `--apply` against a recorded fake `ampero2` (subprocess stub that logs
  the command sequence).
- `analyzer.py`: parses the fixture JSONs; band remapping.
- Skill: reviewed with `superpowers:writing-skills` (baseline test with a subagent first).

## Out of scope

Chain topology, parallel chains, scenes beyond scene 1, NAM/IR-based tones (the
research resolves only to catalog models; NAM uploads remain an `ampero2` recipe),
Global EQ, an OpenRig backend (the research JSON is shared; the build/apply is Ampero).
