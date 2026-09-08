# Ampero II Stage USB (SysEx) protocol

The "Ampero II" editor talks to the pedal over CoreMIDI (port `Ampero II Stage MIDI`)
using SysEx only. Everything below was measured on 2026-09-07 by spying on the editor
with MIDI Monitor (full captures in `docs/captures/`) and reproduced by the `ampero2`
package. Firmware V1.7.0, editor app `com.hotone.mp380` with `HTUSBTools.dylib`.
The pedal does not answer the universal MIDI Identity Request.

## Frame

```
F0 21 25 4D 50 00 00 CK CMD LEN_lo LEN_hi OFF_lo OFF_hi  n1 n2 n3 n4 ...  F7
```

| Field | Meaning |
|---|---|
| `21 25 4D 50` | fixed signature ("MP") |
| `CK` | sum of every byte from `LEN_hi` up to (not including) `F7`, mod 128. The pedal itself sends 01/03 here and does not verify it |
| `CMD` | `0x11` query (host → pedal), `0x12` data (both directions) |
| `LEN` | decoded payload length, 14-bit little-endian (7 bits per byte) |
| `OFF` | decoded offset of this chunk (long replies arrive in 185-byte chunks, uploads are sent in 183-byte chunks) |
| nibbles | every payload byte `b` is sent as two bytes `b >> 4`, `b & 0x0F` |

Decoded payload: `[type 2B][op][target][len32 LE]` followed by an **LZO1X** stream.
For short messages that stream is just a literal run (`len+17`, the bytes, then the
`11 00 00` end marker); patch dumps and uploads are real compressed streams. Floats are
IEEE-754 little-endian.

## Messages (body in brackets)

| Action | CMD | type/op/target | body |
|---|---|---|---|
| select scene | 12 | `01 00 00 03` | `[scene 0-4]` |
| set parameter | 12 | `03 00 04 01` | `[slot 00 index 00][float]` (edit buffer only) |
| query current scene | 11 | `01 00 00 03` + `00 00 00 00` (no trailer) | reply: payload byte 9 = scene |
| block on/off | 12 | `04 00 09 01` | `[scene][12 bytes 0/1, one per slot]` (whole scene bitmap) |
| load patch | 12 | `00 00 09 00` | `[index u32]` — no ack when it is already the current patch (and the edit buffer is kept) |
| read patch | 11 | `00 00 00 01` | `[index u32]` → chunked 0x12 dump (see below). For the current patch this returns the edit buffer, not the flash |
| save edit buffer | 12 | `00 00 00 05` | `[index u32][name 16 chars + NUL]` — also renames the edit buffer |
| set model in slot | 12 | `02 00 04 01` | `[slot][category index][model code u32][01]`; empty = `[slot][FF×5][01]`. A wrong category byte hangs the pedal |
| rename scene | 12 | `07 00 09 01` | `[scene u32][name 7 chars + NUL]` |
| patch tempo | 12 | `02 00 09 01` | `[00 00][bpm u16]` |
| patch volume | 12 | `01 00 09 01` | `[00 00][volume u16]` (the "100" next to the speaker icon) |
| patch footswitches | 11/12 | `00 00 03 01` + `00 00 00 00` reads (12×FF + `10 0F 12 00` when unassigned); `01 00 03 01` writes 7 bytes, one per footswitch | function codes: Scene 1..5 = 1B..1F, Bank- 10, Patch+ 26, Tap Tempo 0D, Tuner 12, Looper 11, EXP 1/2 29, block A2 0C, OFF FF (other slots, Bank+, Patch- not captured) |
| quick access | 12 | `01 00 02 01` | `[para][slot][category][code u32][param]`; empty = `[para][FF×7]` |
| EXP target | 12 | `02 00 06 01` | `[target][exp][slot][category][code u32][param]`; empty = `[target][exp][FF×7]` (range/curve not captured) |
| user templates | 11/12 | `04 00 00 02` lists; `02 00 00 02` `[position+4 u32][name 11 + NUL]` saves the edit buffer; `03 00 00 02` `[position+4 u32]` loads (reply `00 00 00 02` = template image) |
| `0A` query the editor sends when a block is clicked | 11 | `03 00 0A 01` | `[slot 00 00 00]` → a float that is not the knob value (660/567 seen); meaning unknown |

Slots: line 1 = 0..5, line 2 = 6..11; empty slots count. Parameter index = knob order in
the editor panel (Digital Delay HQ: Mix 0, Time 1, Feedback 2, Sync 3). Patch index =
`(bank-1)*5 + (position-1)` (`A28-4` → 138, `A30-3` → 147); 300 patches (A1-1..A60-5).

Model codes come from the editor's own table (`ampero2/catalog.json`, built by
`catalog_build.py` from `App.framework/.../assets/data/v1.0.9_alg_data.json`): 609
models in 18 categories with parameters (name, index, default, range, type). The code is
**not** `category << 24 | index` (Marshell 45 is index 43, code `0x0700002A`).

### Notifications

When the patch is changed from the footswitches the pedal broadcasts the full dump of the
new patch (`00 00 00 01`, same format as *read patch*) plus `03 00 08 00 [01|00]`. The
editor additionally polls: page 9 (`00 00 09 00`) for the current patch index and
`01 00 00 03` for the scene.

## Patch dump

Dump payload = `00 00 00 01` + `len32` + LZO1X stream. Decompressed it is a 7705-byte image:

| Offset | Content |
|---|---|
| 0 | patch index u32 |
| 34 | name, NUL-terminated (17-byte field) |
| 153 | 7 footswitch function codes |
| `200 + 4·slot` | model code u32 per slot, `FF FF FF FF` = empty |
| `256 + 1200·scene + 100·slot + 4·param` | parameter float (5 scenes × 12 slots × 25 floats) — verified at several points |
| `6256 + 12·scene + slot` | block on/off per scene |
| `6326 + 2·scene` | tempo u16 per scene |
| `6655 + 8·scene` | scene names ("Scene 1".."Scene 5") |

Verified by diffing images after single edits: `set parameter` + `save` into an empty
slot changed only the index, the name, the expected float and one flag near 6505. A
parameter set on scene 1 shows up in all 5 scenes; set on scene 2 only in scene 2.

## Global Settings pages (`00 00 PG 00` + `00 00 00 00`)

| Page | Content |
|---|---|
| 0 | 2640-byte master blob: firmware string, [16] current patch, [637] USB source, [819] display mode, … |
| 1 | Input/Output: [0] input L (0 electric, 1 acoustic, 2 line), [1] input R, [3] unbalanced out, [4] balanced out, [6] bypass (0 true, 1 dsp), [8] unbalanced source (0 normal, 1 usb only), [9] fx send source, [10] balanced source, [11] power-on (0 normal, 1 mute), [15] no cab L (0 off, 1 cab, 2 ir), [16] no cab R |
| 2 | USB Audio: [5] unbalanced output source (1 = USB out 1/2, 2 = 3/4, 3 = 5/6), [6..7] the other two |
| 3 | Global EQ, 148 bytes: `[on f32]` + 30 floats (low cut en/f/Q, low shelf en/f/Q/gain, band 1..4 en/f/Q/gain, high shelf en/f/Q/gain, high cut en/f/Q), then `[level][0×3][1.0]` |
| 6 | MIDI: [0] in source (3 = mixed), [1..3] channel TRS/BT/USB (0-15, 16 = omni), [5] clock out TRS, [7] clock source |
| 7 | Controls: [0]/[1] EXP/CTRL 1/2 function (0 exp, 1 single fs, 2 dual fs), [2]/[3] single-FS code, [4..7] dual-FS codes, [8] volatile, [14] set by id 5, [15] global tempo on, [16] global tempo bpm |
| 8 | [0] auto cab match, [1] patch display mode (0 mode 1, 1 mode 2), [3] bank select mode (0 initial, 1 wait) |
| 9 | current patch index u32 |
| 10 | `00 1e 78 00 00 00 01 81` (unknown; 0x78 = 120) |

Setting a global field: `12` with `ID 00 PG 00` and body `[value]` (option index). Known
ids — page 1: 01 input L, 02 input R, 03/04 outputs, 07 unbalanced source, 08 fx send
source, 09 bypass, 0B balanced source, 0C power-on, 10/11 no cab L/R; page 2: 06 USB
source; page 7: 01 `[ctrl 00 function 00]`, 02 `[ctrl 00 fs-code 00]`, 06 global tempo
on/off; page 8: 01 auto cab, 02 display mode, 04 bank select. Global EQ: `02 00 03 00`
`[field index u32][float]` where the index is the position in the 30-field list above
(band 1 gain = 10). PATCH FS FUNC, the MIDI page fields, USB levels and display
colour/brightness have **no known id**.

## NAM upload (`00 00 00 08`)

The editor converts the `.nam` JSON to `.namb` (binary, ~8 KB) with
`convertNamToNamb(char* path)` from `HTUSBTools.dylib` (callable through ctypes; writes
`<file>.namb` next to the input) and sends one LZO image in 183-byte chunks:
`[sum16 of the rest, u32][slot u32 (0-based)][name 20 B][01 00 00 00][namb]`.
Reply `00 00 00 06` with `08 01 00 00 00 <slot>`. Verified live: the image is byte-identical
to the editor's. Rename = `02 00 00 08` `[slot u32][name 16 B]`; delete = `01 00 00 08` `[slot u32]`.

## IR upload (`00 00 00 04`)

The editor normalizes the wav with `getNormalWav(char* path)` (returns the path of
`~/Library/Caches/HTUSBTools/HTCache/Temporary.wav`: mono, 44.1 kHz, 24-bit, r8brain
resampler) and sends `[slot u32][name 32 B][2048 × int32 24-bit samples][sum16 LE]`;
"User IR n" = slot 30 + n - 1. Reply `00 00 00 06` with `04 01 00 00 00 <slot>`. Verified
live. IR list (`03 00 00 04`): 50 fields of 32 bytes; empty slots still carry "User IR n" leftovers.

## CLONE upload (`00 00 00 07`)

Same envelope as NAM with the raw `.clo` file (header `HTSI`):
`[sum16 u32][slot u32][name 20 B][01 00 00 00][clo]`; ack `00 00 00 06` `07 01 00 00 00 <slot>`.
Delete = `01 00 00 07` `[slot u32]`. Rename presumably `02 00 00 07` (not captured).

## Inventories (`11`, no trailer)

| Kind | Query | Reply |
|---|---|---|
| patch names | `00 00 08 01` | 29700-byte image: 300 × u16 order table, then 300 names of 17 bytes at offset 600 |
| user IRs | `03 00 00 04` | 50 × 32-byte names |
| CLONE captures | `03 00 00 07` | 30 × 17-byte names |
| NAM models | `03 00 00 08` | 30 × 17-byte names |
| firmware | `05 00 00 03` | `"V1.7.0"` |

## Connection (what the editor sends when it finds the port)

1. `11` with payload `17 00 00 05 00 00 00 00` (device info; no reply seen).
2. Five times, 200 ms apart: `F0 21 25 7F 4D 50 01 2C 11 00 00 38 00 0E 04 F7` — a different
   frame family (`7F` instead of `4D 50 00 00 CK`, no nibbles); probably "hello / editor version".
3. Page 9 (current patch), current scene, *read patch*, then all inventories.

None of this is required to drive the pedal; the tool works without it.

## Pitfalls

- **SysEx hang.** The pedal goes silent for all SysEx (even the editor's handshake) and only
  a power cycle recovers it — a USB replug does not. Seen three times: (1) *set model* with a
  wrong category byte, (2) eleven Global Settings sets in 35 s **sent by the editor itself**,
  (3) `01 00 06 00 [0F]` — a page-6 id with an out-of-range value. Rules: send only
  (page, id, value) triples observed from the editor, one at a time, read the page after
  each (timeout = stop and tell the user), never burst, never probe ids blindly. Writes
  made right before a hang are not persisted.
- `save` writes the **edit buffer** to the given index and renames the buffer; *read patch*
  of the current patch returns the buffer, not the flash. Load another patch and come back
  to re-read the flash.
- The editor follows patch changes made by the pedal but never re-reads knobs: USB changes
  do not show in its panel.
- MIDI Monitor's Copy truncates long SysEx; save the document (`.mmon`, a plist whose
  `messageData` is an NSKeyedArchiver archive) to keep the full bytes — `ampero2.mmon_export`
  decodes it.
- Not captured: chain topology (series/parallel), Patch MIDI, EXP range/curve, deleting IRs
  or templates.
