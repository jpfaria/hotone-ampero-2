# tone-builder reference

One tool, used only from the command line: `ampero2` — the pedal. `resolve` (catalog lookup) and the
patch commands `build_patch.py` drives. Everything about the pedal itself is in the `ampero2` skill.

This skill builds **reference-less** tones only. Measuring against a record (full mix + separated
guitar track) is the `tone-builder` plugin (`jpfaria/tone-builder`, `tone-builder build --device
ampero2`). `tone-analyzer compare` / `eq-match` / `proximity_pct` are obsolete — never use them.

Setup: check `ampero2 resolve AMP "Fender Twin"` before starting a tone; missing → install, do not
improvise.

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
- The EQ slot is always `EQ "Graphic EQ"` (31 Hz … 16 kHz, −12…+12 dB, `Level` left at 50). All gains 0;
  `--eq-gains` (capped ±6 dB) exists only for the user's explicit ear feedback, one band per move.
- Slot order: gate → comp → wah → drive(s) → amp → cab → eq → mod → delay → reverb, slots 0…n.
  Scene 1 only, every slot on. Scenes, footswitches, EXP, quick access, patch volume, Global EQ:
  not this skill — the user configures them with the `ampero2` skill afterwards.

## Commands

```bash
TB=${CLAUDE_PLUGIN_ROOT}/skills/tone-builder/scripts
python3 $TB/build_patch.py --research R.json --plan PLAN.json                 # plan only, no pedal
python3 $TB/build_patch.py --research R.json --plan PLAN.json --apply A26-2 NAME [--overwrite] [--eq-gains g1,…,g10]
```

`build_patch.py` exit codes: `2` build aborted (`unresolved`, `uncited`, `forbidden`, `too_many`, `no_cab`
— stderr says which and why), `4` verify mismatch after apply (`show` did not read back the plan),
`5` the target patch already has a name and `--overwrite` was not given. It prints the `unverified`
and `unmapped` lists on stderr: relay both to the user.

`--apply` runs: `load PATCH`, `model` per slot (+ `none` on the rest), `param` per non-default knob,
`powers 1 …`, `tempo`, `save PATCH NAME`, then reloads and `show`s to verify. Nothing else.

## Evaluation directory

`EVAL = $HOME/.ampero2/evaluations/<artist-song-slug>/` (create it). Keep `research/<role>-v<N>.json`,
`plan-v<N>.json` and `eval.md` (gear research with sources, mapping, unverified params, ear-feedback log).
