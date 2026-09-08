---
name: tone-builder
description: Use when the user wants the tone of a specific song, artist or genre built as a patch on a Hotone Ampero II Stage — "timbre da Gravity", "preset do Slipknot na Ampero", "tom da [música]", "recreate the [song] sound", "monta um som de blues" — with or without a reference WAV. Not for editing an existing patch's knobs, scenes or footswitches: that is the ampero2 skill.
---

# tone-builder — a song's tone as an Ampero patch

**You make the judgment calls in natural language (which real gear, cited). Deterministic tools
turn them into a patch and measure it.** You never pick a catalog model, a slot or a knob index
yourself; `build_patch.py` resolves the researched names through `ampero2 resolve`, refuses what it
cannot back, applies through the `ampero2` CLI and reads the patch back. `reference.md` (next to
this file) has the research JSON schema, the knob aliases, the command lines and the exit codes.

**Violating the letter of these rules is violating their spirit.** "Faz rápido" changes nothing
below: a fast wrong tone is thrown away and rebuilt slowly anyway.

## The FORM — every tone, the same

0. **Ask once, up front:** destination patch (must be empty; a named patch needs the user's
   explicit "overwrite"), the working `REAMP` patch (see reference.md) when a reference exists,
   and whether there is a reference WAV of the **isolated guitar**. Then work autonomously.
1. **Fingerprint the reference** (if any): `tone-analyzer analyze`. A full mix or a
   wrong-instrument stem is refused and explained. `degraded` → flat path (step 5 skipped).
2. **Research the rig for THIS song, cited.** `tonedb.co` first, then groundguitar.com,
   killerrig.com, musicstrive.com, guitarchalk.com, Premier Guitar / Guitar World rig rundowns.
   Every element: comp, gate, drive(s), amp + channel, cab/speaker, mod, delay, reverb. Open the
   pages; a URL you did not open is not a source. What you remember about the artist is a
   hypothesis to verify, never a citation.
3. **Write `EVAL/research/<role>-v<N>.json`** (schema in reference.md). Re-walk it in both
   directions: every unit a source names is in it; every block in it points at a source that names
   it. The noise gate is the only uncited block allowed.
4. **Build:** `build_patch.py --research … --plan … --apply REAMP|DEST NAME`. Exit 2 = fix the
   research (`unresolved` → add the channel/variant word a source supports, or research a different
   unit; `no_cab` → research the cab; `uncited` → drop the block or find its source). Relay the
   `unverified` and `unmapped` lists verbatim.
5. **Validate** (reference present, not degraded): `ampero2 reamp DI.wav wet-vN.wav`,
   `tone-analyzer compare`, `within = proximity_pct ≥ self_floor_pct − 3`. Not within → regulate in
   this order, one move per iteration, re-apply, re-amp, re-compare: (a) the researched amp's or
   drive's **gain** knob, (b) `tone-analyzer eq-match` → `--eq-gains`. The amp model never changes.
   Plateau below the floor → report both numbers and stop.
6. **Persist:** if built in `REAMP`, `ampero2 load REAMP && ampero2 save DEST NAME && ampero2 show
   DEST`. Say plainly what is unverified, what was derived, and (fallback) that `SOURCE` must be
   flipped back on the screen.
7. **Ear feedback:** one explicit complaint from the user → ONE bounded move (≈ ±2–3 dB on one EQ
   band, one gain-knob step, or a researched cab swap) → stop and let them judge again.

**No reference, or degraded reference:** steps 1 and 5 do not apply. Ship the researched gear with
all EQ gains at 0 and say: *"no reference to match — this is an un-tunable starting point built from
cited gear; give me an isolated-guitar WAV and I'll tune it, or tell me what's off by ear."*

## Hard rules

- **A block ships only when a source names the unit.** Not "the genre has one", not "it would sound
  empty", not "the record has air" — a reverb added for "the room / the air of the recording" is the
  documented failure. Missing knob values never justify dropping a cited block (ship it
  `unverified`); a missing citation never justifies adding one.
- **No fabricated sources.** `sources` holds URLs you opened. A placeholder to get past the gate is
  worse than an empty list: the gate cannot tell, the user cannot either.
- **No stand-ins by taste.** The catalog lacks the researched unit → `resolve` says `unresolved` →
  you research (cited) what the artist used *instead* or what the unit is a clone of, and name that.
  "EVM12L is the classic Dumble speaker so UK Custom 4x12" is your taste, not a source.
- **Cab not in the catalog (`no_cab`, or the sourced cab has no match):** name it by the **cited
  speaker** first (EV/EVM12L, Greenback, V30, Alnico Blue…), then the cited size; `provenance:
  derived`, and tell the user which cited fact chose it. No cited speaker or size → the closest
  cab of the **same amp family**, said out loud as a stand-in. Never by what "sounds right".
- **Knobs from a different unit** (a Two-Rock's settings on the Dumble model, a live rig's on a
  studio take) are `unverified`, never `sourced` — the number is documented, its meaning here is not.
- **Knobs come from sources, derivation, or catalog defaults.** You have no ears. A number you
  "feel" is right is `unverified` at best — say so — and never an EQ band: EQ gains come only from
  `eq-match`.
- **The tone is scene 1, slots, knobs, tempo.** Scenes 2–5, scene names, footswitches, EXP, quick
  access, patch volume, Global EQ: not touched. The user configures them afterwards with the
  `ampero2` skill.
- **One tone per run. Never overwrite a named patch without the user's word. `show` is the source
  of truth.**

## Red flags — stop

- Typing a model name (`Faun Drive`, `Marshell 45`) or a slot number into anything but a test.
- Writing `sources` before opening the page. Writing "plausible" URLs.
- "Sem fonte, mas Mayer com certeza usa…" / "reverb pra dar o ar da gravação".
- Choosing a cab, delay or drive "because it is the closest" without a source for the closeness.
- Reaching for `powers 2 …`, `scene-name`, `footswitches`, `volume`, `eq-set`.
- Skipping research because the user said "rápido", "simples", "qualquer coisa serve".

| Rationalization | Reality |
|---|---|
| "I know this rig, research is a formality" | Memory produced a Klon, a Keeley and a spring reverb with no source in the baseline. Verify or drop. |
| "The gate needs a source, so I'll put a plausible URL" | You just lied to the tool that exists to stop you. Empty list + drop the block. |
| "No Dumble cab in the catalog, I'll pick the classic speaker" | Unsourced stand-in. Find what the recording's cab/speaker was, or what the amp was, and resolve that. |
| "All knobs are guesses but the user wants something" | Ship defaults marked `unverified` and say so; do not dress guesses as settings. |
| "A quick spring reverb makes it sound finished" | Uncited block. Sounding finished is not a source. |
| "I'll add scenes and footswitches while I'm here" | Not the tone. The user does that with the `ampero2` skill. |
