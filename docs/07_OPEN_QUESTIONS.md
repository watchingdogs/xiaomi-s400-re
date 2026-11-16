# 07 — Open questions, and exactly how to close each one

Each item states what is known, what is missing, the cheapest decisive test, and the effort.

---

## Q1. Body age above the floor — **highest value**

**Known.** The coefficients are in the image; the formula is the published one; one real record
matches (model 18, device 18). But 18 is the adult floor: for a young adult any score above −3
clips to 18, so that sample only proves the sign of the score.

**Missing.** A sample where the device reports **> 18**.

**Test.** One weigh-in on a profile with age ≥ 45 and/or higher body fat, read via
`tools/s400_records.py fetch --height … --age … --sex …`, which prints device vs model side by side.
Records above the floor either match exactly (formula confirmed) or show a systematic offset (formula
wrong, and the offset tells you how).

**Effort.** One weigh-in. No code changes.

**Alternative if no second person is available:** create a temp profile in the app (visitor mode or a
second user slot) with a different age/height, weigh once. Visitor mode does not persist a profile,
so use a normal second user slot.

---

## Q2. Body score (record field 24)

**Known.** One real sample only (a male profile). Log name
`sbc`. Computed outside `bia_calc_t` (it is not among the panel outputs).

**Missing.** Formula. Not in any string; the routine has not been located.

**Test, cheap:** a second record with a different score. Two points constrain any linear form in the
three deltas (`field17/18/19`); three points would identify it outright.

**Test, rigorous:** the score is computed in the same code block as body age (the jump-table
continuation around `0x8318A0`). Reconstructing that block's caller frame would expose both. That is
the piece that has resisted so far — see `02_REVERSING_PLAYBOOK.md` step 5 for why.

**Effort.** Cheap test: one more record. Rigorous: several hours of frame reconstruction.

---

## Q3. Record fields 20 and 22

**Known.** Only one sample has been seen. Neither field is produced by `bia_calc_t`.
Field 22 is most likely the body-type index (matches the `bt` log slot); field 20 is unknown.

**Missing.** A second sample with a different profile/body composition to see them move.

**Test.** Same as Q1 — one more record from a different profile body type. If field 22 changes to a
non-zero value, it can be matched against the nine/ten-entry body-type table.

**Effort.** One weigh-in.

---

## Q4. Female reference deltas (fields 17–19)

**Known.** For a male, `0.85·ideal − LBM`, `ideal − weight`, `0.15·ideal − fat mass` reproduce the
three fields exactly. The 0.85/0.15 split corresponds to the 15 % male mid-fat reference.

**Missing.** Whether a female profile uses the same split or its own (the published model uses a
different mid-fat, 23 % for adults, which would imply 0.77/0.23).

**Test.** One female record.

**Effort.** One weigh-in.

---

## Q5. Impedance smoothing — **ANSWERED** (see `03_PROTOCOL.md` §10)

**Known.** `FUN_0081CE6C`. Not an EMA: a gated weighted average of the profile's stored impedance and
the current measurement. Weight gate at 3.6 kg / 6.0 kg; time windows at 601 s / 1800 s / 14401 s
giving 100/0, 80/20 or 50/50 blends.

**Missing.** Only whether the *advertisement* also carries smoothed values (the record demonstrably
carries post-smoothing values).

**Test.** Three to five weigh-ins one to two minutes apart on the same profile, app closed, then
`tools/s400_analyze.py` on the records — it computes the lag-1 relationship between consecutive
impedances and reports the implied alpha. The first weigh-in of the series is unsmoothed; that is the
ground truth.

**Effort.** Five weigh-ins, one command.

---

## Q6. S400 Pro (`ms110`)

**Known.** Different container format, different SoC generation, shares no code blocks with the S400
images at the block level. RX14's independent decompilation of the Pro produced the same coefficients.

**Missing.** Our own verification.

**Test either:** (a) crack the `55AAAA55` container (could be a custom LZ, an obfuscated stream, or a
signed/encrypted section — no standard compressor matches); or (b) run
`tools/s400_records.py` against a Pro and compare a record's fields against `tools/s400_model.py`.
(b) is minutes if a Pro owner is available.

**Effort.** (b) minutes, (a) hours to days.

---

## Q7. Mode-dependent behaviour

**Known.** Five work modes exist (normal, baby, balance, visitor, once) and only normal feeds the
composition chain. Baby mode differences two weighings; balance mode is a timed test reporting
seconds.

**Missing.** The exact baby-mode arithmetic (is the stored baseline a recent adult weight, or a
per-session one?) and what `balance-time`/`real-weight` mean precisely.

**Test.** Switch the scale into baby mode via the app, weigh, read the record; the record's
weight/status fields would show whether a subtraction was applied on-device or in the app.

**Effort.** One session. Needs the MIoT action for `work-mode` set, which is not yet implemented in
`tools/s400_records.py`.

---

## Q8. Fields `+0x60`, `+0x68`, `+0x70` in the panel

**Known.** Written every run (`+0x60` was 1.00 on every sample so far), absent from the stored
record.

**Missing.** Meaning. They are probably intermediate values in the score/body-age step.

**Test.** Emulate with varied inputs and see how they respond; a few profiles will reveal whether they
are simple sums like `fat% + muscle% + bone%`. On the one real sample that sum was off by about 1.6,
so it is not that simple.

**Effort.** Minutes with the emulator already built.

---

## Q9. `siid 12 / eiid 1001`

**Known.** A uint8 `1` pushed twice in one session. Not in the published MIoT spec.

**Missing.** Meaning. Probably a state notification (e.g. "measurement finished" or "user changed").

**Test.** Correlate with actions — log it against weigh-ins and app interactions.

**Effort.** Low, once someone is capturing sessions anyway.

---

## Q10. Android app-side behaviour

**Known.** The app writes the profile and its **plugin version** into the scale, and the scale chooses
a report variant from that version.

**Missing.** Which plugin versions trigger which variant, and whether newer app versions change the
panel (e.g. dropping fields for older firmware).

**Test.** Two phones with different app versions connected to the same scale; compare the reports.

**Effort.** Low, opportunistic.
