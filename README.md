# hotone-ampero-2

Control a **Hotone Ampero II Stage** over USB without the editor: the reverse-engineered
SysEx protocol (September 2026, firmware V1.7.0) plus a Python library and CLI.

```bash
pipx install git+https://github.com/jpfaria/hotone-ampero-2   # or: pip install -e .
ampero2 patches                     # the 300 slots with their names
ampero2 show A30-3                  # slots/models, knob values, scenes, on/off, tempo, footswitches
ampero2 load A30-3 && ampero2 scene 2 && ampero2 param 6 0 25 && ampero2 save A30-3 DET-LUGA
ampero2 model 4 AMP "Marshell 45"   # put a model in a slot (editor catalog: ampero2 models AMP)
ampero2 nam-upload 3 capture.nam    # NAM -> slot 3 (uses the editor's converter through ctypes)
ampero2 ir-upload 2 cab.wav         # IR -> User IR 2
ampero2 eq                          # Global EQ
ampero2                             # every command
```

`python3 -m ampero2` works without the console script.

## Covered

Patches (load, read, save, list, copy = load + save), scenes, knobs, block on/off, model per
slot, scene names, tempo, volume, footswitch functions, quick access, EXP targets, user
templates, Global Settings (Input/Output, Bank Select, Auto Cab, display mode, USB source,
EXP/CTRL, Global Tempo, Global EQ), inventories (patches, NAM, CLONE, IR, firmware), NAM
upload/rename/delete, CLONE upload/delete, IR upload. The pedal broadcasts the new patch by
itself when you change patches with your feet. Byte-level details: [docs/protocol.md](docs/protocol.md).

## Rules that keep the firmware alive

- Global Settings writes: **one at a time**, only (page, id, value) triples that are
  documented, then read the page back. A wrong id or value silences the pedal's SysEx until
  a power cycle (it happened three times while reverse-engineering).
- `save` stores the *edit buffer* into the given slot and renames the buffer; reload the patch
  afterwards.
- NAM/IR uploads need the "Ampero II" editor installed: `HTUSBTools.dylib` is called through
  ctypes to convert `.nam` → `.namb` and to normalize the wav.

## Requirements

macOS (CoreMIDI through `python-rtmidi`), Python ≥ 3.10, the pedal on USB (port
`Ampero II Stage MIDI`). The editor can stay open; it just won't show USB changes.

## Claude Code plugin

This repo is also a plugin marketplace. The bundled `ampero2` skill teaches the agent the
CLI and the rules above.

```bash
claude plugin marketplace add jpfaria/hotone-ampero-2
claude plugin install ampero2@hotone-ampero-2
```

Or per project, in `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "hotone-ampero-2": { "source": { "source": "github", "repo": "jpfaria/hotone-ampero-2" } }
  },
  "enabledPlugins": { "ampero2@hotone-ampero-2": true }
}
```

## Development

```bash
pip install -e ".[dev]" && pytest -q      # golden vectors captured from the editor (docs/captures)
python3 -m ampero2.catalog_build          # rebuild ampero2/catalog.json from the installed editor
python3 -m ampero2.mmon_export doc.mmon   # decode a MIDI Monitor capture
```

MIT.
