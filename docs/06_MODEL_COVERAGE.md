# 06 — Model coverage: which firmwares behave the same way

The question that matters for contributing findings: does this apply only to
`yunmai.scales.ms104 2.1.1_0006`, or to the family?

## 1. Method

Two independent checks, both scripted (`tools/analysis/variant_compare.py`,
`tools/analysis/relocated_test.py`).

**Check A — content signature.** For each decompressed image, count occurrences of the strings and
constants that define the algorithm:

```
strings   : "bia_calc_t 1:", "bmr %d,bt %d,ma %d", "miid %llu,duid %d",
            "bmc %d,vfr %d,pp %d", "impedance_50KHZ", "impedance_smoothing",
            "mi_spec_report_body_composition", "send body composition to BLE peer"
constants : 21.6, 0.944, -0.3315, 0.6216, 22.554, -0.3332, 0.7509,
            -1.48615435 (adult body age), -1.0136192 (youth body age)
```

**Check B — byte identity of the code.** Take 192-byte slices from four separate code regions of
ms104 and search the other images for them. This distinguishes "same strings and constants" (could be
a coincidental reimplementation) from "the same compiled code, just relocated".

Regions probed (ms104 file offsets, image base `0x0080E000`):

| region | ms104 file offset | what it is |
|---|---|---|
| BIA routine | `0x2301C` | `FUN_0083101C` — the algorithm |
| body-age block | `0x2308E` | `FUN_0083108E` continuation |
| panel formatter | `0x117E2` | `FUN_0081F7E2` — builds the CSV |
| record writer | `0x11EEC` | `FUN_0081FEEC` |

## 2. Results

### Content signature — all four non-Pro variants are identical in content

| model | all 8 strings | all 9 constants |
|---|---|---|
| ms104 (S400 intl) | 1 each | 1 each (adult body-age coefficient appears twice) |
| ms103 (S400 CN) | 1 each | 1 each |
| ms107 | 1 each | 1 each |
| ms115 (S400 JP/KR) | 1 each | 1 each |

### Byte identity — the code is the same, merely moved

Each slice was found **exactly once**, byte for byte, at a consistent offset:

| region | ms103 | ms107 | ms115 |
|---|---|---|---|
| BIA routine | `0x22E54` (−0x1C8) | `0x22E6C` (−0x1B0) | `0x23424` (+0x408) |
| body-age block | `0x22EC6` (−0x1C8) | `0x22EDE` (−0x1B0) | `0x23496` (+0x408) |
| panel formatter | `0x11616` (−0x1CC) | `0x11632` (−0x1B0) | `0x11BEA` (+0x408) |
| record writer | `0x11D20` (−0x1CC) | `0x11D3C` (−0x1B0) | `0x122F4` (+0x408) |

Interpretation:

- **ms107** is a uniform −0x1B0 relocation of ms104's code.
- **ms115** is a uniform +0x408 relocation.
- **ms103** is −0x1C8 in the algorithm region but −0x1CC in the two builders — a 4-byte difference,
  i.e. a small insertion between those regions (almost certainly a changed string or table entry).
- Whole-image block similarity is low (13/177 identical 1 KiB blocks) purely because differing
  strings and version banners shift everything; that is not evidence of different logic.

**Therefore: ms103, ms104, ms107 and ms115 run the same body-composition algorithm and the same
record format.** Findings about ms104 apply to the family. What differs between them is regional
configuration (units, server, language strings, plugin-version gating), not the maths.

## 3. The S400 Pro (`xiaomi.scales.ms110`) — different, and not verifiable here

- Its OTA container is a different format: magic `55AAAA55`, 834,662 bytes, not LZMA/zstd/lz4, and
  it shares **no** 256-byte blocks with the S400 images. It is a different SoC generation.
- Its full SPI dump (8,388,608 bytes, P25Q64SH) contains the Pro's bootloader and resource blobs, but
  the application image inside it is itself compressed, so the constants are not visible in a raw
  scan. Absence of the strings in that dump is **not** evidence of a different algorithm.
- Independent evidence that the Pro computes the same thing: RX14 decompiled the Pro OTA and derived
  exactly the coefficients listed above, and `dckiller51` verified the resulting model against ten
  real S400 weighings. Our S400 findings are consistent with that work field for field.

**Status: same algorithm highly likely, not independently verified by us.** Testing it would need
either the Pro's OTA container cracked or a Pro owner running `tools/s400_records.py`.

## 4. Practical guidance for contributors

- Model string is the right key for feature detection, but the correct granularity is
  **"any of ms103/ms104/ms107/ms115"**, not one model.
- Do not gate on firmware version: 2.1.1_0003, _0006, _0009 and _0057 all contain the same code.
- If a future firmware changes the algorithm, the fastest check is Check A above — eight string
  greps and nine constant searches on the decompressed image, all offline, no hardware needed.
- The Pro (`ms110`) should be treated as a separate case until someone verifies it.

## 5. Related models that are *not* in this family

| model | what it is | why it differs |
|---|---|---|
| `xiaomi.scales.ms113` | Xiaomi Smart Scale S200 | different product, no dual-frequency BIA |
| `yunmai.scales.ms115` vs `xiaomi.scales.ms115` | namespace prefix reflects regional branding only | the JP/KR image examined here is `xiaomi.scales.ms115` |
| `xiaomi.scales.400pgj` | another Xiaomi scale SKU | not examined; assume different until checked |

When in doubt, run the two checks in §1 — they take under a minute and need no device.
