# 05 — Fields: what every number is

Three different "field maps" matter, and they are not the same projection of the data:

1. the **stored record** (33 integers, what the scale sends over GATT),
2. the **`bia_calc_t` output panel** (doubles + a few ints, internal),
3. the **log groups** (30 names in three lines of ten, written by the panel formatter).

The record is authoritative for interoperating; the panel is authoritative for the maths.

---

## 1. Stored record — 33 fields

Records are `_`-separated; each is 33 comma-separated integers. Everything decimal is stored ×10.

| idx | meaning | evidence |
|---|---|---|
| 0–1 | `miid` (64-bit account id; the high word is usually 0) | log format `miid %llu` |
| 2 | profile slot / `duid` | matches the slot the app wrote |
| 3 | user type (1 = primary, 2 = virtual, 3 = visitor) | MIoT `user-type` |
| 4 | weight ×10 (kg) | matches advert weight |
| 5 | heart rate (bpm) | matches the HR shown in the app; 0 when not measured |
| 6 | status | 0 in all samples |
| 7 | unix timestamp | decodes to the weighing time |
| 8 | body fat % ×10 | `fat% × weight = field 27` |
| 9 | muscle mass ×10 (kg) | panel `+0x08` |
| 10 | body water % ×10 | panel `+0x10` |
| 11 | bone mass ×10 (kg) | panel `+0x18` |
| 12 | visceral fat level (1–59) | panel `+0x20` |
| 13 | protein % ×10 | panel `+0x28` |
| 14 | **skeletal muscle mass ×10 (kg)** | panel `+0x30` — newly identified |
| 15 | BMI ×10 | `weight / height²` |
| 16 | ideal ("standard") weight ×10 (kg) | panel `+0x40`; equals `(h−80)·0.7` male |
| 17 | **reference delta: `0.85·ideal − LBM` ×10** | verified against panel `+0x48` |
| 18 | **reference delta: `ideal − weight` ×10** | verified against panel `+0x50` |
| 19 | **reference delta: `0.15·ideal − fat mass` ×10** | verified against panel `+0x58` |
| 20 | unknown | not produced by `bia_calc_t` |
| 21 | BMR (kcal) | `370 + 21.6 × FFM` exactly |
| 22 | body type index | matches MIoT `bt` |
| 23 | metabolic / body age (years) | matches MIoT `ma` |
| 24 | body score | log name `sbc`; formula unknown |
| 25 | muscle % ×10 | `muscle / weight` |
| 26 | bone % ×10 | `bone / weight` |
| 27 | fat mass ×10 (kg) | `fat% × weight` |
| 28 | fat-free mass ×10 (kg) | `weight − fat mass` |
| 29 | water mass ×10 (kg) | panel `+0xa0` |
| 30 | protein mass ×10 (kg) | panel `+0xa8` |
| 31 | **z50 ×10 (Ω)** — the 50 kHz impedance | panel input |
| 32 | **z250 ×10 (Ω)** — the 250 kHz impedance | panel input |

Cross-checks that hold on real data (use these to sanity-check any parser):

```
field 8  × field 4  / 1000 == field 27
field 4  − field 27          == field 28
370 + 21.6 × field 28/10     == field 21
field 4  / (height/100)²     == field 15  (±0.1)
field 9  / field 4  × 1000   == field 25
```

---

## 2. `bia_calc_t` output panel (0xC0 bytes)

Set by `FUN_0083101C`. Doubles are at 8-byte offsets, `+0x78` is an int16.

| offset | quantity | | offset | quantity |
|---|---|---|---|---|
| `+0x00` | body fat % | | `+0x78` | **BMR (int16)** |
| `+0x08` | muscle mass (kg) | | `+0x80` | muscle % |
| `+0x10` | body water % | | `+0x88` | bone % |
| `+0x18` | bone mass (kg) | | `+0x90` | fat mass (kg) |
| `+0x20` | visceral level | | `+0x98` | fat-free mass (kg) |
| `+0x28` | protein % | | `+0xa0` | water mass (kg) |
| `+0x30` | skeletal muscle mass (kg) | | `+0xa8` | protein mass (kg) |
| `+0x38` | BMI | | `+0xb0` | (unused / solids-adjacent) |
| `+0x40` | ideal weight (kg) | | `+0xb8` | 0 (not written by this path) |
| `+0x48` | `0.85·ideal − LBM` | | | |
| `+0x50` | `ideal − weight` | | | |
| `+0x58` | `0.15·ideal − fat mass` | | | |
| `+0x60` | 1.00 (constant on all samples so far) | | | |
| `+0x68` | intermediate, not in the record | | | |
| `+0x70` | intermediate, not in the record | | | |

`+0x60`, `+0x68`, `+0x70` are written on every run but do not appear in the stored record; they are
probably inputs to the score/body-age step.

---

## 3. The three reference deltas

These are the "how far from ideal" numbers the app renders as arrows. Verified to 0.1 against a real
record from a male profile (not published). Worked example for a **synthetic** profile (male, 35 y,
178 cm, 80.0 kg, z50 450, z250 400):

```
ideal      = (h − 80)·0.7    [male]      or   (h − 70)·0.6    [female]
field 17   = 0.85·ideal − LBM            = 58.3 − 62.2 = −3.9
field 18   = ideal − weight              = 68.6 − 80.0 = −11.4
field 19   = 0.15·ideal − fat mass       = 10.3 − 17.8 = −7.5
```

The 0.85 / 0.15 split is the male reference (15 % body fat at ideal weight). For a female profile the
complementary split should apply; that is **not yet verified** — see `07_OPEN_QUESTIONS.md`.

---

## 4. Log group names → record indices (partially aligned)

The formatter logs the panel in three lines of ten names:

```
group 1   miid, duid, usrtype, weight, heart, status, time, bfp, slm, bwp
group 2   bmr, bt, ma, sbc, slp, bmp, bfi, ffm, bwm, pm
group 3   bmc, vfr, pp, smm, bmi, sbw, mc, wc, fc, whr
```

Group 2 maps cleanly and in order onto indices 21–30:

```
21 bmr   22 bt   23 ma   24 sbc   25 slp   26 bmp   27 bfi   28 ffm   29 bwm   30 pm
```

With the numeric evidence, the abbreviations resolve as:

| abbrev | meaning | record idx |
|---|---|---|
| `bmr` | basal metabolic rate | 21 |
| `bt` | body type index | 22 |
| `ma` | metabolic age | 23 |
| `sbc` | body score (unknown formula) | 24 |
| `slp` | skeletal lean percentage (muscle %) | 25 |
| `bmp` | bone mass percentage | 26 |
| `bfi`/`bfm` | body fat mass | 27 |
| `ffm` | fat-free mass | 28 |
| `bwm` | body water mass | 29 |
| `pm` | protein mass | 30 |
| `bmc` | bone mineral content (mass) | 11 |
| `vfr` | visceral fat rating | 12 |
| `pp` | protein percentage | 13 |
| `smm` | skeletal muscle mass | 14 |
| `bmi` | body mass index | 15 |
| `sbw` | standard body weight | 16 |
| `bfp` | body fat percentage | 8 |
| `slm` | skeletal lean mass | 9 |
| `bwp` | body water percentage | 10 |

Group 1 and group 3 do **not** align one-to-one with the CSV (33 fields vs 30 names), so treat the
group-1/group-3 *names* as indicative and the *numbers* as verified. The `mc`/`wc`/`fc` names most
likely correspond to indices 17–19 (the reference deltas), but that is an inference from position,
not a proof.
