# tone-builder reference

Two tools, used only from the command line:

- `ampero2` — the pedal. `resolve` (catalog lookup), `reamp` (USB audio through the pedal), and the
  patch commands `build_patch.py` drives. Everything about the pedal itself is in the `ampero2` skill.
- `tone-analyzer` — the audio (github.com/jpfaria/tone-analyzer, Python ≥ 3.11). `analyze` /
  `compare` / `eq-match` on WAV files. Override the executable with `$TONE_ANALYZER`. Its interface
  lives in `scripts/analyzer.py` (see its docstring); when the CLI changes, fix that one file.

Setup: `tone-analyzer` is a dependency of `ampero2` (installed with it); the re-amp loop also needs
`pip install "ampero2[reamp]"`. Check `ampero2 resolve AMP "Fender Twin"` and `tone-analyzer --help`
before starting a tone; missing → install, do not improvise.

Scripts live in `${CLAUDE_PLUGIN_ROOT}/skills/tone-builder/scripts/` (stdlib only, Python ≥ 3.11).

## Research JSON

Written by the agent. It carries **gear names and sources**, never catalog model names, slot
numbers or knob indices.

```json
{
  "song": "Gravity", "artist": "John Mayer", "role": "rhythm",
  "id": "john_mayer_gravity_rhythm", "name": "John Mayer - Gravity (rhythm)",
  "tempo_bpm": 66,
  "amp":    { "name": "Dumble Overdrive Special overdrive section on", "brand": "dumble",
              "params": { "gain": 35 }, "provenance": "sourced", "sources": ["https://…"] },
  "drives": [ { "name": "Ibanez TS808", "brand": "ibanez", "params": { "drive": 20, "level": 60 },
                "provenance": "sourced", "sources": ["https://…"] } ],
  "cab":    null,
  "fx":     [ { "type": "gate", "name": "ISP Decimator noise gate", "params": { "threshold": 38 },
                "provenance": "unverified", "sources": [] },
              { "type": "delay", "name": "mono analog delay",
                "params": { "time_ms": 454, "feedback": 28, "mix": 30 },
                "provenance": "derived", "sources": ["https://…"] } ]
}
```

| Field | Rule |
|---|---|
| `amp.name` | Real amp + channel/variant words when the catalog has variants (`normal channel`, `high treble channel`, `jump`, `overdrive section on`, `vibrato channel`, `lead channel`). `resolve --strict` reports a tie as `unresolved` with the candidates: add the word the sources support. |
| `drives[]` | One entry per pedal, signal order. `[]` = clean. Boosts resolve in `DRV` then `DYN`. |
| `cab` | An object only when a source names the cab/speaker or the amp is a preamp. `null` for a combo: the build derives the amp's own combo cab (`provenance: derived`). No derivable cab → the build aborts `no_cab`; research the cab. |
| `fx[].type` | `gate`, `comp`, `wah`, `mod`, `delay`, `reverb`. `volume` and `limiter` are rejected. |
| `sources` | Real URLs you opened. Placeholders, "plausible" URLs, or citations from memory are forbidden — the gate cannot check them, you can. Empty `sources` is only allowed on the `gate`. |
| `provenance` | `sourced` (a source states the knob values), `derived` (computed: delay time from BPM, cab from the amp), `unverified` (cited unit, knobs unknown → catalog defaults or a stated default). Absent = `unverified`. |
| `params` | Keys are generic knob names (alias table below); values in the model's own range (usually 0–100; delay `time` in ms). Unknown keys are reported as `unmapped` and ignored. |

**Knob aliases** (`params` key → model knob it lands on, first match by prefix): `gain|drive` → Gain/Drive/Sustain/Fuzz;
`level|volume|output` → Level/Volume/Output; `tone`; `bass|low`; `mid|middle`; `treble|high`; `presence`;
`time|time_ms` → Time; `feedback|repeats`; `mix|blend`; `depth`; `rate|speed`; `threshold`; `attack`; `release`.
Any other key is `unmapped`. Run `ampero2 params CAT "Model"` to see a model's knobs.

## Catalog rules that differ from a modeler with captures

- **AMP / PRE AMP models have no speaker.** A CAB (or IR) slot is mandatory; the build enforces it.
- The EQ slot is always `EQ "Graphic EQ"` (31 Hz … 16 kHz, −12…+12 dB, `Level` left at 50). Gains come
  only from `tone-analyzer eq-match` (`--eq-gains`, capped ±6 dB); otherwise all 0.
- Slot order: gate → comp → wah → drive(s) → amp → cab → eq → mod → delay → reverb, slots 0…n.
  Scene 1 only, every slot on. Scenes, footswitches, EXP, quick access, patch volume, Global EQ:
  not this skill — the user configures them with the `ampero2` skill afterwards.

## Commands

```bash
TB=${CLAUDE_PLUGIN_ROOT}/skills/tone-builder/scripts
python3 $TB/build_patch.py --research R.json --plan PLAN.json                 # plan only, no pedal
python3 $TB/build_patch.py --research R.json --plan PLAN.json --apply A26-2 NAME [--overwrite] [--eq-gains g1,…,g10]
ampero2 reamp DI.wav WET.wav [--tail S] [--mono]                              # after `ampero2 input-source usb34`
tone-analyzer analyze REF.wav --out-dir EVAL/ref                              # fingerprint.json: self_floor_pct, top_octave_dead
tone-analyzer compare REF.wav WET.wav --out-dir EVAL/v1                       # diff.json: proximity_pct
tone-analyzer eq-match REF.wav WET.wav --gains g1,…,g8 --output EVAL/v1/eq_match.json   # 8 analyzer bands (80 Hz…10.24 kHz)
```

The analyzer works on 8 octave bands, the pedal's Graphic EQ on 10: `scripts/analyzer.py`
(`eq_match(ref, wet, current_10_gains)`) does the nearest-centre mapping both ways and caps ±6 dB —
use it (python one-liner or import) rather than mapping by hand.

`build_patch.py` exit codes: `2` build aborted (`unresolved`, `uncited`, `forbidden`, `too_many`, `no_cab`
— stderr says which and why), `4` verify mismatch after apply (`show` did not read back the plan),
`5` the target patch already has a name and `--overwrite` was not given. It prints the `unverified`
and `unmapped` lists on stderr: relay both to the user.

`--apply` runs: `load PATCH`, `model` per slot (+ `none` on the rest), `param` per non-default knob,
`powers 1 …`, `tempo`, `save PATCH NAME`, then reloads and `show`s to verify. Nothing else.

## Re-amp precondition (validation loop)

Audio goes computer → USB Output 3 → **chain A input** only when the current patch's input node
`SOURCE` is `USB OUT 3/4` (`INPUT CH = L`). Chain A's output comes back on USB Input 1/2.
`reamp` exits 3 with "no signal" when that is not set.

`ampero2 input-source usb34` sets it in the edit buffer (message captured from the editor on 2026-09-17,
verified live). Build and iterate in any empty patch with it set; before saving to the destination run
`ampero2 input-source input` so the saved patch plays the guitar input again.

DI: a real guitar DI WAV, reused across every tone, kept at `$HOME/.ampero2/di.wav`. Ask the user for
it once (any dry electric-guitar recording, mono, a few bars of open chords + single notes). The
`tone-analyzer` test fixtures are synthetic tones, not a guitar — never use them as the DI. No DI →
the validation loop is unavailable → reference-less path, say so.

## Evaluation directory

`EVAL = $HOME/.ampero2/evaluations/<artist-song-slug>/` (create it). Keep `research/<role>-v<N>.json`,
`plan-v<N>.json`, `wet-v<N>.wav`, the analyzer out-dirs, and `eval.md` (gear research with sources,
mapping, iteration log with the numbers, unverified params, methodology notes).
