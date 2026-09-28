# NAM → Ampero (lite) by distillation

**Idea (2026-09-28, João):** take any NAM (A1 standard/xstd, A2 full, LSTM) and bring it to the
format the Ampero runs natively: the A2 lite WaveNet (1 layer array, 3 channels, kernel 6,
23 dilations, LeakyReLU, ~1.9k weights, `.namb` ~8 KB).

## Why it is not a file conversion
Weights of a 16- or 8-channel network cannot be squeezed into 3 channels. The editor's
`convertNamToNamb` only re-packs whatever architecture it receives (A1 standard → 55 KB
`.namb`); for an A2 container it keeps the lite submodel (see `docs/learnings.md`, 2026-09-28).

## How: distillation (teacher → student)
1. Teacher = the heavy `.nam`. Run it offline over the NAM training signal (`input.wav` v3,
   48 kHz) → `output.wav`. No amp or pedal involved.
2. Student = train an A2-lite WaveNet (same config as sub 0 of an A2 file) on
   `input.wav` → `output.wav` with the `neural-amp-modeler` trainer (torch, MPS on the Mac).
3. Check ESR student vs teacher on held-out audio (and on a DI, e.g. the gravity DI).
4. `convertNamToNamb` → `ampero2 nam-upload SLOT file.nam`.

## Open
- torch / `neural-amp-modeler` not installed on the Mac yet (venv inside the repo).
- Does the pedal run A1 standard / A2 full `.namb` as is? If yes, distillation is only a CPU
  saving, not a requirement. Not tested on the device.
- Where the output lives: `ampero2 nam-distill IN.nam OUT.nam` in this repo.
