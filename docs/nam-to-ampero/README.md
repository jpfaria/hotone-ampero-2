# NAM → Ampero CLONE (.clo)

**Idea (2026-09-28, João):** turn a NAM capture into the Ampero's own, lighter capture
format (CLONE, `.clo`), not upload the NAM itself (that already works: `nam-upload`).

## What a .clo is (read from two files, 2026-09-28)
Fixed 8840 bytes, little-endian. Samples: `tests/fixtures/ts9.clo`,
`~/Library/Application Support/com.hotone.mp380/Presets/Archetype Mayer X - /MAYERX DUMB CL.clo`.

| offset | content |
|---|---|
| 0x00 | `HTSI`, u32 file size (8840), u32 (checksum?, differs per file), zeros |
| 0x18 | biquad 1: 5 doubles (TS9: identity `1,0,0,0,0`; Mayer: real filter) |
| 0x40 | biquad 2: 5 doubles (same) |
| 0x68 | 4 floats (gains/levels?) |
| 0x7C | u32 × 3: `128, 128, N` (TS9 N=512, Mayer N=2048) |
| 0x88 | 128 floats (not monotonic: not a plain waveshaper table) + N floats, rest zero-padded |

Reading: a block model (EQ → small nonlinear part of 128 params → N-tap FIR → EQ),
orders of magnitude smaller than a NAM WaveNet. Semantics of the 128 params and the
4 floats are **not established**.

## How a conversion would work
Not a weight copy (different architecture). Use the NAM as a black box: run it offline
over a test signal, then fit the .clo parameters to that output. Needs first:
1. the .clo inference (what the 128 params and the FIR do) — from the pedal by black-box
   probing (upload altered .clo, re-amp, measure) or from firmware;
2. then the fitter `ampero2 nam-to-clo IN.nam OUT.clo`.

## Decision (2026-09-28): shelved
João only wants it if the result is identical to the NAM. A .clo has far fewer parameters
and a simpler structure than a WaveNet, so a fit is an approximation by construction: it
cannot be identical. Not pursued.
