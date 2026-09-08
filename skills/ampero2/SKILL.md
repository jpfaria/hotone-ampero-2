---
name: ampero2
description: Use when the user wants to read or change anything on a Hotone Ampero II Stage over USB without the editor UI — patches, scenes, knobs, models, footswitches, templates, quick access, EXP, Global Settings/EQ, NAM/IR/CLONE captures — e.g. "muda o Master do amp do A30-3", "lista os patches da Ampero", "sobe esse NAM pra pedaleira", "liga o No Cab Mode", "que modelos de amp existem", or when a USB command times out / the pedal stopped answering.
---

# ampero2 — Ampero II Stage over USB

CLI + Python package (`ampero2`) speaking the pedal's SysEx protocol (`docs/protocol.md`).
`ampero2` with no arguments prints every command with its syntax. Not installed?
`pipx install git+https://github.com/jpfaria/hotone-ampero-2` (or `pip install -e "${CLAUDE_PLUGIN_ROOT}"`).
Needs macOS, the pedal on USB (port `Ampero II Stage MIDI`); the editor may stay open but
will NOT show USB changes — `ampero2 show` is the source of truth.

## Recipe: change a knob and persist it

```bash
ampero2 show A30-3                    # slot numbers, model per slot, knob names in order
ampero2 load A30-3 && ampero2 scene 1
ampero2 param 4 1 60                  # slot 4, knob index 1 (order printed by show / `params AMP "<model>"`)
ampero2 save A30-3 DET-LUGA           # name is mandatory: save also renames the edit buffer
ampero2 load A26-1 && ampero2 load A30-3 && ampero2 show A30-3   # reload from flash, then verify
```

- Slots: line 1 = 0..5, line 2 = 6..11, **empty slots count** (DET-LUGA's delay is slot 6).
- A knob set on scene 1 lands on all 5 scenes; on scene 2+ only that scene.
- `load` of the patch that is already current does nothing — load another patch first to
  drop an edit buffer or to re-read the flash.
- Everything below marked *buffer* touches only the edit buffer until `save`.

## All commands (verified live)

| Area | Commands |
|---|---|
| inspect | `patches` (300 slots), `show A30-3`, `dump A30-3 [out.bin]` (decompressed image), `inventory` (firmware, CLONE, NAM, IR), `templates` |
| patch selection | `load A30-3`, `scene` (print active), `scene 2` (select) |
| edit *buffer* | `param SLOT IDX VALUE`, `model SLOT CAT "Model"` / `model SLOT none`, `powers SCENE b0..b11` (12 on/off bits), `scene-name N NAME` (≤7), `tempo BPM`, `volume 0-100`, `footswitches 1b ff ff ff ff ff ff` (7 hex codes, `protocol.FOOTSWITCH_FUNCTIONS`), `quick-access PARA SLOT KNOB` / `quick-access PARA off`, `exp EXP TARGET SLOT KNOB` / `exp EXP TARGET off` |
| persist / copy | `save A30-3 NAME`; copy = `load SRC && save DST NAME`; `template-save 1 NAME` (≤11), `template-load 1` |
| catalog (offline) | `models AMP` (index, code, based on), `params AMP "Marshell 45"` (knob order, defaults, ranges) |
| captures | `nam-upload 3 f.nam [name]`, `nam-rename 3 NAME`, `nam-delete 3`, `clone-upload 6 f.clo [name]`, `clone-delete 6`, `ir-upload 2 cab.wav [name]` — uploads need the "Ampero II" editor installed (its dylib converts the files) |
| globals | `global N` (raw page 0-10), `global-set ID VALUE [PAGE]` (only ids in `protocol.GLOBAL_PARAMS`, e.g. `0x10 1` = No Cab L cab only, `0x04 1 8` = Bank Select wait), `ctrl 1 exp|single|dual`, `ctrl 1 fs 29` (single-FS code, hex), `eq`, `eq-set "band 1" gain 3` |
| live | `listen [seconds]` prints the patch the pedal broadcasts when a footswitch changes it |

NAM/CLONE/IR/template positions and para/EXP/target numbers are 1-based, exactly as the
editor labels them (NAM Slot 3, User IR 2, Para 1). **Slots and knob indices are 0-based**:
the first knob of a block is index 0 (`show` and `params` print them in order).

## Global Settings — hard rules (firmware hangs otherwise)

Send only (page, id, value) triples listed in `protocol.GLOBAL_PARAMS`; never guess an id or
send a value outside the documented options; **one set at a time**, then read the page
(`global N`) and compare. Never fire a burst: eleven sets in 35 s hung the pedal.

## When the pedal stops answering

A timeout on `scene`, `show` or `global` after a write means the SysEx handler hung. Stop
sending. Only a power cycle (not a USB replug) recovers it; then re-read what you changed
(writes made right before a hang were not persisted). Say this to the user plainly.
