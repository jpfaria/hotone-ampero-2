---
name: ampero2
description: Use when the user wants to read or change anything on a Hotone Ampero II Stage over USB without the editor UI — patches, scenes, knobs, models, footswitches, templates, Global Settings/EQ, NAM/IR/CLONE captures — e.g. "muda o Master do amp do A30-3", "lista os patches da Ampero", "sobe esse NAM pra pedaleira", "liga o No Cab Mode", "que modelos de amp existem", or when a USB command times out / the pedal stopped answering.
---

# ampero2 — Ampero II Stage over USB

CLI + Python package (`ampero2`) speaking the pedal's SysEx protocol (`docs/protocol.md`).
Run `ampero2` with no arguments for the command list. If it is not installed:
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
- `param`/`model`/`scene-name`/`tempo` touch only the edit buffer until `save`.

## Other commands (all verified live)

| Need | Command |
|---|---|
| list / inspect | `patches`, `show A30-3`, `inventory`, `dump A30-3 out.bin` |
| build a patch | `model 4 AMP "Marshell 45"` (`models AMP`, `params AMP "Marshell 45"`), `model 4 none`, `powers 2 0 1 0 0 1 1 1 0 0 0 0 0` |
| patch extras | `scene-name 1 NAME` (≤7), `tempo 120`, `footswitches 1b ff ff ff ff ff ff` (hex codes in `protocol.FOOTSWITCH_FUNCTIONS`) |
| copy / move a patch | `load SRC && save DST NAME` |
| captures | `nam-upload 3 f.nam`, `ir-upload 2 cab.wav`, `clone-upload 6 f.clo`, `nam-delete 3`, `clone-delete 6` (uploads need the "Ampero II" editor installed: its dylib converts the files) |
| globals | `global 1` (raw page), `global-set 0x10 1` (No Cab L = cab only), `global-set 0x04 1 8` (Bank Select = Wait), `eq`, `eq-set "band 1" gain 3` |

## Global Settings — hard rules (firmware hangs otherwise)

Send only (page, id, value) triples listed in `protocol.GLOBAL_PARAMS`; never guess an id or
send a value outside the documented options; **one set at a time**, then read the page
(`global N`) and compare. Never fire a burst: eleven sets in 35 s hung the pedal.

## When the pedal stops answering

A timeout on `scene`, `show` or `global` after a write means the SysEx handler hung. Stop
sending. Only a power cycle (not a USB replug) recovers it; then re-read what you changed
(writes made right before a hang were not persisted). Say this to the user plainly.
