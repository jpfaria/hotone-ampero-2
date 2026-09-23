---
tags: [hotone-ampero-2, learnings]
created: 2026-09-18
updated: 2026-09-20
source: claude-code-sessions
---

## 2026-09-20 — Input source `usb34` is borrowed state, restored in code not in docs

- **Incident:** after a re-amp flow (tone-builder), the current patch was left with input
  source `usb34` (re-amp over USB). In that mode the guitar input is ignored, so the pedal
  went silent; the user lost an hour debugging before finding `ampero2 input-source usb34`
  was the cause. Fix at the time: `ampero2 input-source input`.
- **Gotcha / invariant:** `usb34` must never be left set by any automated path. The guarantee
  lives in `ampero2/state.py::borrowed_input_source`, a context manager that snapshots the
  previous source, switches to the target, and restores it in `finally` **and** on
  SIGINT/SIGTERM — covering success, exceptions, and a killed process. `ampero2 reamp`
  (`ampero2/cli.py`) is the only caller that sets `usb34`, and it always goes through this
  context manager — it no longer requires (or accepts as a substitute) a prior manual
  `ampero2 input-source usb34`. `ampero2 doctor` reads the current patch back and reports
  (exit 1) if it's stuck on a source that leaves the pedal silent, with the fix command.
- **Why it matters:** this was previously a documentation-only rule (run `input-source usb34`
  before `reamp`, remember to set it back after) — exactly the kind of step a session under
  pressure skips. It is now enforced by code and covered by tests
  (`tests/test_input_state.py`, `tests/test_cli_reamp_doctor.py`), so a future change can only
  break it by touching `state.py` and having the regression tests fail.
- **Applies to:** `ampero2/state.py`, `ampero2/cli.py` (`reamp`, `doctor`), any future code
  path that needs `usb34` — it must go through `borrowed_input_source`, never call
  `msg_set_input_source("usb34")` directly.

# hotone-ampero-2 — Learnings

## 2026-09-22 — The NAM block's output does not follow the input level (measured on A57-1)

- **Gotcha / invariant:** re-amping the same DI through A57-1 scene 3 (NAM slot 1 `bogner_ecstasy_b` → Boger 4x12 B) and scene 2 (Boger XT Blue M gain 30 → same cab): the NAM comes out **8 dB quieter** (rms −28.9 vs −21.1 dBFS) with mids 800–2 kHz 4 dB lower and >5 kHz 3 dB higher than the amp model. Its output is nearly **independent of the input level**: NAM `Input` knob −20 → +20 dB moves the output only −2.6 → 0 dB; a DI boosted +16 dB (peak −0.9 dBFS) changes nothing (−28.5); a single note 24 dB softer comes out 0.4 dB softer (the amp model: 3.8 dB). `Output` works normally (−10 → −10 dB). Files: 15 s of `gravity-john-mayer/di/jpfaria-rhythm.wav`, `ampero2 reamp --mono`.
- **Why it matters:** an A/B by ear against a factory amp is unfair by default (8 dB down) and the NAM block plays with no dynamics: softer picking does not clean up. Whether this is the Ampero's NAM converter normalising or the capture saturating at every level is not established; the `Input` knob is not the fix either way. Level-match with `Output` (+8) before judging the tone.
- **Applies to:** any NAM block on the pedal (`ampero2 param SLOT 0` is `Input`, `1` is `Output`), the tone-builder skill when it puts a NAM next to a factory amp.

## 2026-09-18 — One direct-reference URL per package across sibling repos

- **Gotcha / invariant:** `tone-analyzer` is a `git+https://…` direct reference. When two packages installed into the same environment (here `ampero2` and `tone-builder`) point at the same package with different URLs (e.g. one pinned `@v0.1.0`, one unpinned), pip refuses to resolve. Keep the exact same URL string in every sibling repo (`b602201`).
- **Why it matters:** the install of the whole toolchain breaks, not just this package.
- **Applies to:** `pyproject.toml` `dependencies`; any other repo that also depends on `tone-analyzer`.

## 2026-09-18 — The tone-builder skill here is reference-less only

- **Gotcha / invariant:** `skills/tone-builder/` researches, builds and applies a patch, then reads it back (`show`). It does **not** measure. Matching a recording (re-amp → compare → EQ match) lives in the separate `tone-builder` project with `--device ampero2`. The old adapter (`scripts/analyzer.py`) and the `tone-analyzer compare`/`eq-match` instructions were removed (`4b2bea4`, `eba8080`).
- **Why it matters:** the skill once said those commands were obsolete while `reference.md` still taught them. Don't reintroduce a measured loop or "measure" wording here. `--eq-gains` stays only for one-band-at-a-time adjustments driven by listening feedback.
- **Applies to:** `skills/tone-builder/SKILL.md`, `reference.md`, `scripts/build_patch.py`, README.
