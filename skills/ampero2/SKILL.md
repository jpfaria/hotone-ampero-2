---
name: ampero2
description: Use when the user wants to read or change anything on a Hotone Ampero II Stage over USB without the editor UI — patches, scenes, knobs, models, footswitches, templates, quick access, EXP, Global Settings/EQ, NAM/IR/CLONE captures — e.g. "muda o Master do amp do A30-3", "lista os patches da Ampero", "sobe esse NAM pra pedaleira", "liga o No Cab Mode", "que modelos de amp existem", or when a USB command times out / the pedal stopped answering.
---

# ampero2 — Ampero II Stage over USB

CLI + Python package speaking the pedal's SysEx protocol. `reference.md` (next to this
file) has every command with its syntax, the footswitch codes, the Global Settings ids,
the Global EQ fields and the catalog categories — read it before composing commands.
`ampero2` with no arguments prints the same command list.

Setup: macOS, pedal on USB (port `Ampero II Stage MIDI`). Not installed?
`pipx install git+https://github.com/jpfaria/hotone-ampero-2` (or `pip install -e "${CLAUDE_PLUGIN_ROOT}"`).
The editor may stay open but does NOT show USB changes — `ampero2 show` is the source of truth.

## Numbering (most common mistake)

- **Slots and knob indices are 0-based.** Line 1 = slots 0-5, line 2 = 6-11, empty slots
  count. The first knob of a block is index 0; `show` and `params CAT "Model"` print the order.
- Everything else is 1-based like the editor's labels: patch `A30-3`, scene 1-5, NAM Slot,
  Sound Clone, User IR, template 1-5, para 1-3, EXP 1-3, target 1-4.

## Recipes

**Change a knob and persist it**
```bash
ampero2 show A30-3                              # find the slot and the knob index
ampero2 load A30-3 && ampero2 scene 1           # scene 1 propagates the value to all scenes
ampero2 param 4 1 60
ampero2 save A30-3 DET-LUGA                     # name is mandatory; save also renames the edit buffer
ampero2 load A26-1 && ampero2 load A30-3 && ampero2 show A30-3   # re-read from flash and verify
```

**Build a patch from scratch in an empty slot**
```bash
ampero2 load A26-2
ampero2 model 1 DRV "Green 9" && ampero2 model 4 AMP "Marshell 45" && ampero2 model 5 CAB "UK Vintage 4x12"
ampero2 model 6 DLY "Digital Delay HQ"
ampero2 params AMP "Marshell 45"                # knob order → indices for param
ampero2 param 4 0 40 && ampero2 param 6 0 25
ampero2 powers 1 0 1 0 0 1 1 1 0 0 0 0 0        # scene 1: DRV, AMP, CAB, DLY on
ampero2 powers 2 0 0 0 0 1 1 1 0 0 0 0 0        # scene 2: DRV off
ampero2 scene-name 1 RHYTHM && ampero2 scene-name 2 CLEAN && ampero2 tempo 120
ampero2 footswitches 1b 1c ff ff ff ff ff       # FS1 = scene 1, FS2 = scene 2
ampero2 save A26-2 MY-PATCH && ampero2 show A26-2
```
Chain topology (series/parallel) cannot be set over USB; new patches inherit it.

**Copy or move a patch**: `ampero2 load SRC && ampero2 save DST NAME` (move = then overwrite SRC).

**Put a NAM capture on the pedal and use it**
```bash
ampero2 inventory                               # free NAM slot?
ampero2 nam-upload 3 amp.nam "my amp"           # needs the Ampero II editor installed (dylib converts)
ampero2 load A26-2 && ampero2 model 4 NAM "my amp" && ampero2 save A26-2 MY-PATCH
```
IR: `ir-upload N cab.wav` then `model SLOT IR "<name>"`. CLONE: `clone-upload N f.clo`.

**Expression pedal / quick access**: `ampero2 exp 1 1 6 0` (EXP1, target 1 → slot 6 knob 0),
`ampero2 quick-access 1 4 0`; both live in the edit buffer, `save` afterwards.

**Global Settings** (see the id table in `reference.md`):
```bash
ampero2 global 1                                # read the page first
ampero2 global-set 0x10 1                       # ONE write: No Cab Mode L = cab only
ampero2 global 1                                # confirm byte 15 == 1
ampero2 eq && ampero2 eq-set "band 1" gain 3
```

**Follow the footswitches**: `ampero2 listen 120` prints each patch the pedal broadcasts.

## Hard rules

- Global Settings: only (page, id, value) triples listed in `reference.md`; **one write at a
  time**, read the page after each. Never burst, never guess an id or a value — a wrong one
  hangs the pedal's SysEx (it happened three times during reverse-engineering).
- `load` of the patch that is already current does nothing: to drop an edit buffer or
  re-read the flash, load another patch first.
- A knob `param` on scene 2-5 changes only that scene.
- Uploads need the "Ampero II" editor installed (its `HTUSBTools.dylib` converts .nam and .wav).

## When the pedal stops answering

A timeout on `scene`, `show` or `global` after a write means the SysEx handler hung. Stop
sending. Only a power cycle (not a USB replug) recovers it; then re-read what you changed —
writes made right before a hang were not persisted. Say this to the user plainly.

## Not possible over USB (use the editor)

Chain topology (series/parallel), Patch MIDI messages, EXP range/curve, PATCH FS FUNC, MIDI
channel/clock settings, USB audio levels, display colour/brightness, deleting IRs or templates.
