# 04 — The body-composition algorithm

*(This is the standalone reference document, updated with the live-hardware validation.)*

# Xiaomi Body Composition Scale S400 — device algorithm reference

Status: working document. Everything in §4 was verified by executing the firmware's own
code and comparing against an independent implementation of the published model. Everything
in §5 is partially verified and marked as such.

## 0. Live validation (real device)

A real 33-field record from a male adult profile was run through the emulator built from firmware
2.1.1_0006. **Nineteen record fields reproduce exactly**, including every derived mass and
percentage: fat %, muscle, water %, bone, visceral, protein %, SMM, BMI, ideal weight, BMR, fat
mass, FFM, water mass, protein mass, muscle % and bone %. The record itself is personal data and is
not published; run `tools/emulator/compare_real.py` on a record from your own scale to repeat the
check.

Plus three previously unidentified fields, which are reference deltas (see §3.2). Illustrated with
the model's output for a **synthetic** profile (male, 35 y, 178 cm, 80.0 kg, z50 450, z250 400;
ideal 68.6, FFM 62.2, fat mass 17.8):

```
17 = 0.85·ideal_weight − LBM            (58.3 − 62.2 = −3.9)
18 = ideal_weight − weight              (68.6 − 80.0 = −11.4)
19 = 0.15·ideal_weight − fat_mass       (10.3 − 17.8 = −7.5)
```

The four fields that do not come out of `bia_calc_t` are: 4 (weight — an *input*, not an output),
20 (unknown), 23 (body age) and 24 (body score) — the last three are computed downstream of it.

This confirms the whole chain end to end on hardware: the two impedances the scale reports are
the ones it used, the rounding order is right, and the model in §3 is not an approximation.
Fields `20`, `22`, `23`, `24` are **not** produced by `bia_calc_t` (see §4).

Firmware analysed: `yunmai.scales.ms104` (MJTZC01YM), **2.1.1_0006**, BLE image
`ac2deeb70c29d94578aecaec3a7e53a0_upd_yunmai.scales.ms104.bin`, md5
`ac2deeb70c29d94578aecaec3a7e53a0`, 153,196 bytes container → 182,388 bytes decompressed.
MCU: M91, `0006`.

---

## 1. Platform

| | |
|---|---|
| SoC | Realtek **RTL8762C** (Cortex-M4F, single-precision FPU only) |
| BLE stack | Xiaomi `mible` over RTK_BLE / RTK_NVM / RTK_GATT |
| SDK | 1.2.1.248, build `Fri Mar 20 17:12:50 2020` |
| Measurement MCU | **M91** ("Yunmai"), UART1. Command set is version + DFU only: `MIBLE_MCU_GET_VERSION / READ_DFUINFO / WRITE_DFUINFO / WRITE_FIRMWARE / VERIFY_FIRMWARE / UPGRADE_FIRMWARE / TRANSFER` |
| Container | nested headers (magic `41960005` / `21810005`), stage-1 plaintext Thumb-2 DFU (40,912 B, identical across ms103/104/107/115), payload = 12 × LZMA1 streams, 16 KiB each |
| Code base | `0x0080E000` (image loads here; literals are absolute at this base) |
| Arithmetic | doubles, **software-emulated** (M4F is SP only) — hence the `__aeabi_d*` cascade in disassembly |

The M91 measures; the SoC computes. There is no BIA message in the MCU command set, so body
composition is not delegated.

---

## 2. Transport

### 2.1 Advertisement (passive)

MiBeacon, product id `0x3BD5`, service data UUID `0xFE95`.

```
frame ctrl 0x5910 (empty) / 0x5948 (object present, encrypted)
nonce  = MAC_reversed(6) || product_id(2) || counter(1) || ext_counter(3)
cipher = AES-CCM, key = bindkey (16 B), AAD 0x11, 4-byte MIC
object 0x6E16 (9 B): u8 user, u32 packed, u32
packed: weight bits 0–10 (0.1 kg), heart rate bits 11–17 (+50 bpm),
        impedance bits 18–31 (0.1 Ω)
weight frame : weight ≠ 0, impedance = 50 kHz
final frame  : weight = 0, HR = 0, impedance = 250 kHz
```

The advertisement carries **no** composition data — only weight, HR and one band per frame.

### 2.2 GATT (what Mi Home uses)

Service `0xFE95`: `0x0010` control, `0x0019` auth parcels, `0x001A` app→device, `0x001B`
device→app, `0x0017`/`0x001C` also notify. Login: `24 00 00 00` → app_rand → dev_rand +
remote_info → `HKDF-SHA256(token, salt=app_rand||dev_rand, info="mible-login-info", 64)` →
`dev_key/app_key/dev_iv/app_iv`; HMAC-SHA256(app_key, app_rand||dev_rand); `21 00 00 00` = OK.
Encrypted parcels: `<counter u16><AES-CCM ct + 4B tag>`, nonce `iv(4)||0(4)||counter(2)||0(2)`.

MIoT spec `urn:miot-spec-v2:device:scale:0000A07D:yunmai-ms104:1`:

| siid | service | notes |
|---|---|---|
| 2 | scale | unit, heart-rate-detection, current-time |
| 6 | user-management | miid, age, sex (1 M / 2 F), user-type, height, weight, time, user-id, **user-bfp**, … |
| 8 | online-data | `weight-data`, `body-composition` (strings) |
| 9 | offline-data | stored weigh-ins, ≤160, until `end-of-reception` |
| 10 | work-mode | normal / baby / balance / visitor / once, balance-time, real-weight |
| 13 | syncinfo | pluginversion, unit, time, userlist, offline count, sn, mac, firmware, battery |
| 14 | share-cancel | share-user-list |

`body-composition` and the offline records are **ASCII CSV**, built from a struct that is also
logged in three 10-field groups (see §5.1).

---

## 3. `bia_calc_t` — the device's computation

Entry point: `0x0083101C`. Logged as:

```
bia_calc_t 1: height=%u, weight=%u, sex=%u, age=%u, electrodes_number=%u, imp0=%u, imp1=%u
bia_calc_t 2: …same…
```

Two calls per weighing (two electrode configurations / refinement passes).

### 3.1 Input struct

```
+0x00 u16 height    ×0.1 cm
+0x02 u16 weight    ×0.1 kg
+0x04 u8  sex       0 = female, 1 = male   (MIoT spec uses 1/2; the firmware remaps)
+0x05 u8  age       years
+0x06 u8  electrodes_number   (not used by the maths)
+0x08 u16 imp0      ×0.1 Ω  (50 kHz)
+0x0a u16 imp1      ×0.1 Ω  (250 kHz)
```

### 3.2 Output panel (offset → quantity), all verified

| off | quantity | off | quantity |
|---|---|---|---|
| +0x00 | body fat % | +0x30 | skeletal muscle mass kg |
| +0x08 | muscle mass kg | +0x38 | BMI |
| +0x10 | water % | +0x40 | ideal (standard) weight kg |
| +0x18 | bone mass kg | +0x78 | BMR kcal (int16) |
| +0x20 | visceral fat level | +0x90 | fat mass kg |
| +0x28 | protein % | +0x98 | fat-free mass kg |
| | | +0xa0 | water mass kg |
| | | +0xa8 | protein mass kg |

### 3.3 Formulas

Nine-term regressions (water, bone, solids, skeletal muscle, visceral), coefficients ×1e6:

```
reg(k) = (k0·h + k1·w + k2·z50 + k3·z250 + k4·√h + k5·√w + k6·√z50 + k7·√z250 + k8) / 1e6
```

```
_WATER           2935892  149065  -468183   589094  -63286091  -778045  23941529 -29784715  424044966
_BONE             118543   26106   -45544    48749   -2271994  -155662   2151182  -2248649   12272558
_SOLIDS           160696   28769   -60093    65412   -3163648  -169504   2860478  -3043837   18045896
_SKELETAL_MUSCLE 2475795  118673  -457174   556218  -53616294  -574893  23989719 -28648257  352065003
_VISCERAL_FAT   -1849883  424124   366784  -455322   39648934  -359012 -20035428  24213934 -265509571
```

Body fat and everything derived from it:

```
body_fat% = clamp(100·(c0·h + c1·w + c2·age + c3·z50 + c4)/w, 3, 55)
  male   c = (-0.3315, 0.6216, 0.0183, 0.0085, 22.554)
  female c = (-0.3332, 0.7509, 0.0196, 0.0072, 22.7193)

fat_mass = round01(round01(body_fat%)·w/100)      ← the % is rounded to 0.1 first
lbm      = w − fat_mass
bone     = reg(_BONE); 0 if round01(x) < 0.3; clamp 0..5
solids   = round01(reg(_SOLIDS))
water    = round01(round01(reg(_WATER)) + 0.03·w)
water%   = round01(clamp(round01(water/w·100), 20, 85))
water_m  = round01(water%·w/100)
protein% = (lbm − solids − water_m)/w·100          clamp 5..32
protein_m= round01(clamp(round01(protein%), 5, 32)·w/100)
muscle   = clamp(lbm − round01(bone), 7, 141.5)
smm      = clamp(reg(_SMM), 0.45·round01(muscle), 0.70·round01(muscle))
visceral = clamp(int(reg(_VISC) + 0.5), 1, 59)
bmr      = int(21.6·round01(lbm) + 370 + 0.5)       clamp 400..3500
bmi      = w/(h/100)²
ideal    = (h−80)·0.7 [male] | (h−70)·0.6 [female]
```

`round01(x)` = round half away from zero to 0.1.

**Order matters.** Each mass is rounded to 0.1 kg before the next step consumes it, and the
water chain re-masses the *clamped percentage* (`water% · w/100`) instead of keeping the
regressed mass — so protein is computed against a slightly different water figure than the
regression produced. A float implementation that keeps full precision drifts by a few tenths.

### 3.4 Validation

Emulated firmware vs independent implementation of the formulas above:

```
                      formula   firmware
180cm 75kg M 38y   fat %   19.49   19.50    muscle 57.10  57.10
 z=520/475 Ω       water % 57.73   57.70    bone    3.26   3.30
                   prot %  17.60   17.60    SMM    31.44  31.40
                   BMR    1674.6    1675    fat mass 14.60 14.60
                   FFM     60.40   60.40    water m 43.30  43.30
                   protein 13.20   13.20    visceral 7.00  7.00

165cm 60kg F 30y   fat %   29.51   29.50    ideal  57.00  57.00
 z=600/540 Ω       BMR    1283.7    1284    BMI    22.04  22.00
```

After correcting one detail — the firmware rounds the fat *percentage* to 0.1 before turning
it into a mass — a straightforward implementation of §3.3 reproduces all 14 fields exactly
across 7 profiles spanning both sexes, ages 19–55, weights 45–100 kg and impedances 360–700 Ω.
Maximum deviation: 7e-15 (float noise). `s400_model.py` in this bundle is that implementation.

**Consequence:** the firmware implements the published "Xiaomi Home" model exactly; the
coefficients are compiled in as per-site immediates, not stored as a table.

---

## 4. Reference-based metrics (partial)

### 4.1 Body age / metabolic age — formula known, ONE weak data point

First real sample (a young adult male, the record in §0): model 18, device 18 — MATCH,
but 18 is the adult floor, so this only proves the score sits above −3. It does not test the
formula. A profile that produces a value **above** 18 is needed (older and/or higher body fat).

Everything below remains the formula as derived from the constants, not from executed code.

Status after a dedicated reconstruction pass: **attempted, not validated.** Details, so nobody
repeats the work:

- All ten coefficients are present (adult −1.48615435, 0.129089458, 0.591458258,
  −0.000405611446; youth −1.0136192, 0.107155831, 0.277336024, −0.0349702346; plus 0.944, 2.5,
  −10, 21.6, 370) and are read by code around `0x0083108E`.
- `0x0083108E` is **not a function entry**: it is a jump-table continuation entered with r4–r7
  pre-loaded, sharing a stack frame with unrelated metrics. Ghidra never created a function at
  its call site (`0x008319A0`) either — "no function contains this address".
- The block at `0x8318A0–0x8319A4` reads input fields at struct +0x08 and +0x0A, multiplies by
  −0.8122387355 and 1.647969043, divides by 10.0, adds stack-held doubles and 23.3769314591,
  then calls `0x83108E`. Those coefficients belong to the same family as the other panel metrics,
  which suggests this block computes a *derived ratio* (candidate: `whr` / `sbc` / `slp`), not body
  age.
- `bia_calc_t` has a `param_3 == 1` branch that was executed under emulation (§8): it produces an
  almost entirely zeroed panel, so it is not the reference-metric path either.
- The published reference tables (13-entry `BMI_MID` per sex, the girls' `BFP_MID` table) are
  **absent from the image in every encoding tested** — float64, and integers ×1/×10/×100/×1000 in
  16- and 32-bit. Either the device derives those references differently, or its body age is not
  the published algorithm at all.

What the chain does look like, from the constants and the published implementation:

```
band        = clamp(age,6,18) − 6
bmi_mid     = BMI_MID[sex][band]     (absent from image — unconfirmed)
bfp_mid     = 15.0 male | 23.0 adult female | by-age table for girls
std_weight  = round01(bmi_mid·h²/10000)
ref_lbm     = round01((100−bfp_mid)·std_weight/100)
ref_bmr     = int(21.6·ref_lbm + 370.5)
ref_muscle% = round01((100−bfp_mid)·0.944)
score       = ((w−std_weight)·c_w + (bmr−ref_bmr)·c_bmr
              + (fat%−bfp_mid)·c_fat + (muscle%−ref_muscle%)·c_muscle) / 2.5
adults:  shift = −10 | +2 | int(score)+1 | int(score); result = clamp(age − shift − 4, 18, 100)
children: shift ∈ {−1,0,+1}; result clamped 6..17
```

**Decisive cheap test instead of more decompilation:** one real weigh-in. The stored record
carries `ma` at index 23; compare it against this formula for the same profile and impedances.
The device's fat%, FFM and BMR are already bit-exact (§3.4), so a single sample isolates the
body-age step.

Supporting findings from this pass:

- `report_body_composition` = `FUN_0081F930` → formats the panel and sends it as MIoT **siid 8,
  piid 2** — confirming `body-composition` is exactly that property.
- The panel struct is filled before that call, by the caller at `0x81CE5E` (inside
  `FUN_0081CE6C`).
- `bia_calc_t` call sites: `0x817034`, `0x81D024`, `0x81D084`.

### 4.2 Body type — classification grid, two incompatible encodings

Body type is not a formula: it is a cell in a 2-D lookup, fat-% thresholds by age band and
sex (7 bands, e.g. 18–40 men 11/17/22/27) against muscle-% thresholds by height and sex
(3 height tiers, e.g. men ≥170 cm 49.4/59.5), giving nine cells.

Encodings in circulation:

- Xiaomi Home plugin (`yunmai.scales.ms104` v31, `_getBodyTypeTitle`): **−5…+4**, ten values,
  `2` = overweight used twice;
- miscale heritage: **0…8**, `obese, overweight, thick-set, lack-exercise, balanced,
  balanced-muscular, skinny, balanced-skinny, skinny-muscular`.

Any implementation must map the signed device index explicitly. The grid itself is
unverified for this device.

### 4.3 Body score — unknown

Record index 24. No `score` string in the image, routine not located. Presumably a 0–100
composite against the same reference bands; the weights are unknown. One real weigh-in with
the app's displayed score would be enough to fit it.

---

## 5. Records and work modes

### 5.1 Stored record (service 9)

Records separated by `_`; each is 33 comma-separated integers. The formatter
(`0x0081F7E2`) builds the CSV from a struct and logs the same fields in three groups of ten,
which fixes the column order:

```
group 1 (miid …)      miid(64-bit), duid, usrtype, weight, heart, status, time, bfp, slm, bwp
group 2 (bmr …)       bmr, bt, ma, sbc, slp, bmp, bfm, ffm, bwm, pm
group 3 (bmc …)       bmc, vfr, pp, smm, bmi, sbw, mc, wc, fc, whr
```

**Empirical field table, verified against a real record + emulator (§0):**

| idx | meaning | idx | meaning |
|---|---|---|---|
| 0–1 | miid (64-bit, hi word is 0) | 17 | 0.85·ideal − LBM |
| 2 | profile slot / duid | 18 | ideal − weight |
| 3 | user type (1 = primary) | 19 | 0.15·ideal − fat mass |
| 4 | weight ×10 | 20 | unknown |
| 5 | heart rate | 21 | BMR |
| 6 | status | 22 | body type index |
| 7 | unix time | 23 | metabolic age |
| 8 | fat % ×10 | 24 | score ("sbc") |
| 9 | muscle mass ×10 | 25 | muscle % ×10 ("slp") |
| 10 | water % ×10 ("bwp") | 26 | bone % ×10 ("bmp") |
| 11 | bone mass ×10 ("bmc") | 27 | fat mass ×10 |
| 12 | visceral level | 28 | fat-free mass ×10 |
| 13 | protein % ×10 ("pp") | 29 | water mass ×10 ("bwm") |
| 14 | skeletal muscle mass ×10 | 30 | protein mass ×10 ("pm") |
| 15 | BMI ×10 | 31 | z50 ×10 |
| 16 | ideal weight ×10 ("sbw") | 32 | z250 ×10 |

The three `mc`/`wc`/`fc` names in group 3 correspond to 17–19 by position, but the CSV and the
log projections don't align one-to-one (33 fields vs 30 names), so treat the *abbreviations* as
plausible and the *numbers* as verified.

Community-confirmed indices (HA thread post #51):
`0` index, `1` account, `2` profile, `4` weight ×10, `7` timestamp, `8` fat% ×10,
`9` muscle ×10, `10` water% ×10, `11` bone ×10, `12` visceral, `13` protein% ×10,
`15` BMI ×10, `16` ideal ×10, `21` BMR, `22` body type, `23` metabolic age, `24` body score,
`25` muscle% ×10, `26` bone% ×10, `27` fat mass ×10, `28` FFM ×10, `29` water mass ×10,
`30` protein mass ×10, `31`/`32` z50/z250 ×10. Unidentified: 3, 5, 6, 14, 17, 19, 20.

Identity checks that hold on real records (and reproduce from §3.3):

```
fat% × weight = fat mass      weight − fat mass = FFM      BMR = 370 + 21.6·FFM
water + protein + bone = FFM  BMI = w/(h/100)²             z250 < z50
```

### 5.2 Work modes (state machines, not maths)

- **normal** — the path that feeds §3.
- **baby** — `get baby mode weight, w, flag, stable` → `processing baby mode data, weight,
  flag, status`; two-stage weighing (adult baseline, then held baby), status reported to the app.
- **balance** — timed test: `balance mode start, start timing` → `get balance test data,
  status, time` → `report balance mode data to app`; exits on timeout / over-weight;
  `balance time: %d`.
- **visitor** — profile not persisted (`cur visitor user info`).
- **once** — single measurement, no profile binding.

---

## 6. Verified vs inferred

| Item | Status |
|---|---|
| Container format (nested headers + LZMA chunks) | verified |
| 14-field panel formulas, rounding order, clamps | verified: bit-exact reimplementation over 7 profiles |
| Sex encoding 0/1 in `bia_calc_t` | verified |
| Advert bit layout, AES-CCM framing | verified (community + firmware strings) |
| Record column order (32/33 CSV, three groups) | derived from formatter + community |
| Body-age *constants* | present in image; applied by code at 0x8317xx/0x8318xx |
| Body age *formula* | derived (published model); one real sample matches at the 18 floor only — not yet discriminating |
| Body score | unknown; one real sample only, no formula recovered |
| Fields 17/18/19 (reference deltas) | verified against real record (§0) |
| Body type grid | community/published; index encoding differs between sources |
| Body score | unknown |
| Impedance smoothing rule | known to exist (`impedance_smoothing`, `before/after`), magnitude unknown |

---

## 7. Implementation notes (for openScale or similar)

1. **Rounding order is part of the model.** Round to 0.1 at each step as listed; do not carry
   full precision through the chain.
2. **Sex is 0/1** in the calculation; MIoT's 1/2 must be remapped. Any other value falls to
   the 3.0 % fat clamp.
3. **Band naming is inverted** relative to BIA convention: the larger impedance is ~50 kHz and
   carries the fat-relevant information; the smaller is ~250 kHz.
4. **The device smooths impedance** against the profile's previous measurement for the values
   it shows. A passive reader sees raw values, so back-to-back weigh-ins legitimately differ
   slightly from the app.
5. **Prefer the stored records over adverts** where reliability matters: one record carries
   both bands, heart rate, timestamp and profile, and up to 160 can be read back.

---

## 8. Reproduction

```
tools: ghidra 11.1.2 (base 0x0080E000), unicorn, capstone
scripts: s400_extract.py         container -> LZMA -> image
         emu_bia.py              execute bia_calc_t with synthetic inputs
         probe_struct.py         struct calibration by byte perturbation
         panel_bia.py            print the full panel
         label_panel.py          match panel fields to formulas
         ghidra_scripts/*.py     xrefs, decompilation, constant mining
```

`python3 emu_bia.py` prints the panel for a few sample profiles; `label_panel.py` diffs it
against the formulas above.
