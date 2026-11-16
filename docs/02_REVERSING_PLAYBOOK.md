# 02 — Reversing playbook: how this was done, reproducibly

Every step below was actually executed. Commands are given as run (Linux, but all Python is
portable). Where a step failed first, the failure and the fix are recorded — those are the parts
that cost the most time and are the most valuable to anyone repeating this.

---

## Step 0 — Set up a workspace

```
python -m venv .venvs/miio
.venvs/miio/bin/pip install pycryptodome capstone unicorn bleak cryptography micloud python-miio
```

Ghidra 11.1.2 with a JDK 17+ (`/opt/data/tools/ghidra_11.1.2_PUBLIC`, JDK at `/opt/data/jdk`).

**Pitfall (cost: 2 wasted runs).** If you unpack the Ghidra zip with Python's `zipfile`, the Unix
permission bits are **not** restored. Ghidra's native decompiler binary loses `+x`, and every
decompile then fails with an *empty* error message that looks like an analysis problem:

```
decompile failed
```

Fix once:

```
chmod +x Ghidra/Features/Decompiler/os/linux_x86_64/decompile
chmod +x support/*.sh support/analyzeHeadless
```

---

## Step 1 — Fetch the firmware

`tools/xiaomi_fw_fetch.py --model yunmai.scales.ms104 --region de`. The endpoint is model-keyed and
returns `url` + `md5`; verify the MD5 after download. See `01_PROVENANCE.md` for region quirks.

---

## Step 2 — Unpack the container

`tools/s400_extract.py <ota.bin>`:

1. Read the 48-byte outer header (magic `41960005`), skip the 40,912-byte plaintext stage-1.
2. At `0xA000` read the inner header (magic `21810005`) — its `+12..+28` constant is identical to the
   outer one; that shared constant is a domain separator, not a per-image hash.
3. From `0xA068`, walk LZMA-alone streams: at each offset try `lzma.decompress` on the
   `5D 00 10 00 <size:8>` header with `FORMAT_ALONE`; on success, advance by the compressed length.
4. Concatenate the 16,384-byte outputs → flat image (182,388 bytes for ms104).

**Dead ends recorded so you can skip them:** the payload is not AES (882 combos of mode/padding/key
derivation with the BLE bind key), not zlib/gzip, not zstd/lz4/bz2, and the stage-1 bootloader
contains no cipher implementation (no AES S-box, no TEA delta, no SHA constants) — consistent with
there being no decryption step at all.

---

## Step 3 — Identify the platform

Strings in the decompressed image give it away in seconds:

```
RTK_BLE, RTK_NVM, RTK_GATT, mible_*, "In SoC Mode", "1.2.1.248", "Fri Mar 20 17:12:50 2020"
"@Xiaomi Scale S400", "YUNMAI"
"[I] : impedance_50KHZ: %d, impedance_250KHZ: %d, weight: %d"
"[I] : bmr %d,bt %d,ma %d,sbc %d,slp %d,bmp %d,bfm %d,ffm %d,bwm %d,pm %d"
```

Realtek RTL8762C, Xiaomi `mible` over the Realtek SDK.

---

## Step 4 — Load it into Ghidra at the right base  ← the critical step

```
support/analyzeHeadless <project_dir> <name> \
  -import <image> \
  -processor "ARM:LE:32:Cortex" \
  -loader BinaryLoader -loader-baseAddr 0x80E000 \
  -scriptPath <scripts> -postScript FindReport.py \
  -max-cpu 1 -analysisTimeoutPerFile 900
```

**Pitfall (cost: an entire session).** Importing at the default base `0x0` yields **zero string
references** — every literal points outside the program, Ghidra silently discards the references, and
it looks like the firmware uses some exotic addressing scheme. It does not. The image loads at
`0x0080E000`, so a string at file offset `0x29A4E` has address `0x0080E000 + 0x29A4E = 0x00837A4E`.
At the correct base, `ldr rx,[pc,#imm]` literal loads resolve normally and xrefs appear.

**How the base was found, if you ever need to redo it:** the literal pool next to the VTOR store
(`0xE000ED08`) contains pointers `0x0080E7A1` (48 occurrences) and `0x0083A128`; the image is
182,388 bytes, so a base of `0x0080E000` puts both just inside it and makes the header words
`0x0080E400`/`0x0080E000` meaningful. Sanity check: `base + string_offset` must land on a string.

**RAM discipline.** Ghidra on a 15 GB box: `MAXMEM=1536M`, `-max-cpu 1`. Analysis of this 182 KB
image takes ~15 s and never exceeded 2 GB. Do not parallelise headless runs on the same project.

---

## Step 5 — Find the interesting functions

Approach: grep the decompressed image for the log format strings, then let Ghidra list their
references and the containing functions.

| string | address (file) | function | what it is |
|---|---|---|---|
| `[I] : bia_calc_t 1: height=%u…` | 0x29A48 | — | the request struct log |
| `[I] : bia_calc_t 2: …` | 0x29AAC | `FUN_0081CF9A` | caller that logs and calls the calculator |
| `[I] : bmr %d,bt %d,…` | 0x29B66 | `FUN_0081F7E2` | panel → CSV formatter |
| `[report][body composition]len=%d` | 0x11A1E | `FUN_0081F930` | `report_body_composition()` → MIoT siid 8/piid 2 |
| `bia_calc_t` consumer | — | **`FUN_0083101C`** | **the algorithm** |
| body-age constants | 0x8318xx | `FUN_0083108E` / block at `0x8318A0` | reference metrics (see below) |

**Pitfall.** `FUN_0083108E` is not a real function entry — it is a jump-table continuation entered
with `r4`–`r7` pre-loaded, which is why Ghidra renders it with 59 `param_N` arguments and `unaff_r4`.
Ghidra also reports "no function contains" its call site `0x008319A0`. Do not try to call it in
isolation; it needs the dispatcher's frame.

---

## Step 6 — Deal with software floating point

Cortex-M4F has only **single**-precision hardware FP. All the algorithm's arithmetic is **double**,
emulated in software, so the decompiled C is an unreadable chain of calls like
`FUN_00834908(a, b, 0, DAT_008318d0)` — where `(lo, hi)` word pairs carry the doubles.

Trick that made this tractable: **identify the helpers by executing them.** Load the image into
Unicorn and call each candidate with `a = 2.0`, `b = 3.0`, reading the result from `r0:r1`:

| address | f(2,3) | meaning |
|---|---|---|
| `0x00834820` | 0 (r0=0) | `i2d` (int → double) |
| `0x0083400C` | 5.0 | `dadd` |
| `0x00834CF8` | −1.0 | `dsub` |
| `0x00834908` | 6.0 | `dmul` |
| `0x0083428C` | 0.667 | `ddiv` |
| `0x00834890` | 2.0 | `dmin`/compare |
| `0x00834C46` | 2.0 | `dmin` variant |
| `0x0083467C` | 2 | `d2i` (double → int) |

`tools/emulator/label_helpers.py` does exactly this.

Constant pool notes: constants appear in two encodings — full 8-byte doubles referenced as
`(DAT_x, DAT_x+4)`, and "zero-low-word" doubles referenced as `(0, DAT_x)` where `x` holds the
**high** word. Reading a shifted 8 bytes at a constant gives values like `3.000000478` — that is the
tell-tale of a zero-low-word constant, not a real coefficient.

---

## Step 7 — Drive the algorithm directly

`tools/emulator/probe_struct.py` maps the image, patches stubs, sets up registers per AAPCS and runs
`FUN_0083101C`:

- Map ROM `0x0` (1 MB), image at `0x0080E000`, RAM `0x20000000`, peripherals `0x40000000`,
  ROM alias `0xC0000000` (zeros are fine).
- Patch four functions with `movs r0,#0; bx lr` (`00 20 70 47`): the input validator `0x00832240`,
  the log formatter `0x00813AFC`, and two ROM helpers `0x0005A060`, `0x0005A070`. Patching memory is
  far more reliable than code hooks — a hook that rewrites PC mid-instruction corrupts the pipeline
  ("invalid instruction at 0x0083103E").
- Call convention for `FUN_0083101C(out, in, flag)`: `r0` = 0xC0-byte output buffer,
  `r1` = input struct, `r2` = 0 (mode).
- Set `lr` to a mapped sentinel inside the stack region and stop when PC reaches it.

**Input struct (16 bytes), calibrated by perturbing one byte at a time:**

```
+0x00 u16  height, 0.1 cm      +0x05 u8   age
+0x02 u16  weight, 0.1 kg      +0x06 u8   electrode count (unused by the maths)
+0x04 u8   sex: 0 = female, 1 = male     +0x08 u16 z50, 0.1 Ω
                                +0x0a u16 z250, 0.1 Ω
```

Perturbation results (this is how the layout was proven): bytes 0–5 and 8–11 each change output
values; bytes 6, 7 and 12–15 change nothing. Sex = 2..255 drops fat % to the 3.0 clamp floor —
the tell-tale of an unhandled branch, and how `0 = female` was discovered.

**Output struct:** doubles at `+0x00 … +0xB0`, integers at `+0x78` (BMR) and `+0xB8`. See
`05_FIELDS.md` for the complete offset table.

---

## Step 8 — Validate, do not assume

Two independent checks, both automated in `tools/emulator/`:

1. **Against the published model** — implement the known formulas in Python and compare across
   profiles of both sexes, ages 19–55, 45–100 kg, 360–700 Ω. Result: **exact to 7e-15**.
2. **Against real hardware** — feed a real record's own inputs into the emulator and compare all
   33 fields. Result: 16 fields exact, three previously-unlabelled fields identified
   (`05_FIELDS.md` §3).

The rounding-order detail that validation caught: the firmware rounds **fat %** to 0.1 **before**
converting it to a mass. Using the unrounded percentage shifts fat mass by 0.1 kg and BMR by 3 kcal
on some profiles — small, but it is the difference between "close" and "identical".

**Searches that failed, and why (do not repeat them):**

| attempt | result | lesson |
|---|---|---|
| byte-search for the coefficient values as float32/float64/int at 10 scales | 0 hits | coefficients are **instruction immediates**, not a table |
| ordered-chain search (7 vectors × 10 scales × 2/3/4-byte widths, ≥3 in 256 B) | nothing | same |
| literal xrefs at base 0x0 | 0 refs | wrong base |
| `movw`/`movt` scan for address construction | 0 pairs | compiler uses literal pools, not movw/movt |
| unpacked Ghidra zip | decompiler not executable | restore permissions |

---

## Step 9 — Confirm which other firmwares behave the same

`tools/analysis/variant_compare.py` and `relocated_test.py`:

- Every variant contains the same strings (`bia_calc_t`, the three panel logs, `impedance_50KHZ`,
  `impedance_smoothing`) exactly once.
- Every variant contains every algorithm constant exactly once (21.6, 0.944, all five body-fat
  coefficients, both body-age coefficient sets).
- 192-byte slices taken from four separate code regions of ms104 (the BIA routine, the body-age
  block, the panel formatter, the record writer) are found **byte-identical** in ms103, ms107 and
  ms115, at consistent offsets (ms103 −0x1C8/−0x1CC, ms107 −0x1B0, ms115 +0x408).

Conclusion: the algorithm and the record format are shared across the S400 family. Details and the
Pro caveat are in `06_MODEL_COVERAGE.md`.

---

## Step 10 — Reproduce the transport findings

The BLE side does not need Ghidra. The protocol was confirmed against hardware with
`tools/s400_records.py --debug`, which logs every frame. The framing, login handshake and MIoT
message layout are documented in `03_PROTOCOL.md`, including the two details that are easy to get
wrong (the parcel `type` byte for MIoT data, and buffering the device's unsolicited messages before
sending your own request).
