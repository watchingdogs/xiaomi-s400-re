# Xiaomi Body Composition Scale S400 - reverse-engineering knowledge base


This is a complete, reproducible record of how the S400 scale's firmware was obtained, unpacked, decompiled and validated, and everything that can be learned about it's BLE protocol and body comp algorythm. Everything in this repository, apart from this note has been AI generated, all of the decompilations etc are produced by an LLM. However, every result can be reproduced independently. The goal of this repository is to unlock the features of the scale, to use it independently of the Xiaomi apps.

Device: Xiaomi Body Composition Scale S400 (MJTZC01YM) · Model string: `yunmai.scales.ms104` · Firmware: 2.1.1_0006

## Read in this order

| file | what it covers |
|---|---|
| `docs/01_PROVENANCE.md` | where the firmware came from, hashes, which models exist, legal note |
| `docs/02_REVERSING_PLAYBOOK.md` | **how it was done** — every step, every dead end, reproducible |
| `docs/03_PROTOCOL.md` | BLE advertisement, GATT login, MIoT framing, records, work modes |
| `docs/04_ALGORITHM.md` | the body-composition computation, field by field |
| `docs/05_FIELDS.md` | record layout, panel offsets, abbreviations, derived-delta formulas |
| `docs/06_MODEL_COVERAGE.md` | which firmwares/models share this code (verified by byte comparison) |
| `docs/07_OPEN_QUESTIONS.md` | what is still unknown and exactly how to close each gap |
| `docs/08_UPSTREAM_NOTES.md` | what is worth contributing back, to which project, in what shape |

## Tools

| file | purpose | deps |
|---|---|---|
| `tools/s400_records.py` | read stored weigh-ins over BLE (Windows/macOS/Linux) | bleak, cryptography |
| `tools/s400_model.py` | the 16-field body-composition model, pure Python, no deps | none |
| `tools/s400_analyze.py` | offline analysis of a raw record string | none |
| `tools/s400_extract.py` | unpack an S400 OTA container to a flat image | none |
| `tools/xiaomi_fw_fetch.py` | fetch OTA firmware from Xiaomi's cloud by model | micloud |
| `tools/emulator/` | run the firmware's own BIA code under Unicorn | unicorn, capstone |
| `tools/analysis/` | the probes used to derive every claim here | capstone, unicorn |
| `ghidra_scripts/` | Ghidra post-scripts (xrefs, decompilation, passes) | Ghidra 11.x |
| `decompiled/` | not included; regenerate the decompiled C locally with `ghidra_scripts/` | — |
| `data/constants.json` | every algorithm constant, machine-readable | — |
| `data/checksums.txt` | sha256 of every file here + md5 of each firmware | — |

## The 60-second version

1. Xiaomi's OTA endpoint (`/app/home/latest_version`) serves firmware by **model string**, with no device ownership required — only a logged-in account.
2. The OTA file is **not encrypted**: a 48-byte header, a 40 KB plaintext DFU stage, then an inner header and **12 concatenated LZMA streams** (4 KiB dictionary). Four lines of Python unpack it.
3. The application SoC is a **Realtek RTL8762C** (Cortex-M4F), image load address **0x0080E000**. Loading it anywhere else makes every string reference dangle — that single mistake cost a full afternoon of "Ghidra finds no xrefs".
4. `bia_calc_t` is a struct passed to `FUN_0083101C`. It receives height, weight, sex, age, an electrode count and the two impedances, and produces a panel of doubles.
5. Because Cortex-M4F has only single-precision hardware float, all the maths is **software-emulated double**. Rather than read that by eye, the helper routines were identified by **executing** them, then the whole function was run under Unicorn with synthetic inputs.
6. The algorithm turns out to be **exactly the published Xiaomi model** (the one RX14 derived from the S400 Pro). The coefficients are **inlined as instruction immediates**, not stored as a table — which is why byte-searching for them fails, and why the earlier conclusion "the S400 uses a different model" was wrong.
7. Verified against a **real record from real hardware**: 19 fields reproduce exactly, including three fields nobody had previously identified (the reference deltas in `docs/05_FIELDS.md`).
8. The same code is present, **byte-identical but relocated**, in ms103, ms107 and ms115 — so the findings apply to the whole S400 family, not just one build (see `docs/06_MODEL_COVERAGE.md`).

## What is verified vs inferred

- **Verified by execution:** the 16-field panel, rounding order, clamps, sex encoding, struct layout.
- **Verified by byte comparison:** code identity across ms103/ms104/ms107/ms115.
- **Verified on hardware:** one full 33-field record reproduced from its own inputs; transport framing and the login handshake (captured live).
- **Inferred:** body-age formula (constants present, one floor-limited sample matches), body-type grid.
- **Unknown:** body score formula, record fields 20 and 22.
- **Solved late:** the impedance "smoothing" is a time- and weight-gated weighted average, not an EMA — 100/0, 80/20 or 50/50 depending on elapsed time, bypassed above a 6 kg weight change.

## Legal / ethical note

The firmware is Xiaomi's proprietary code. **No firmware binaries or decompiled firmware code are included here** — only hashes, descriptions, and the scripts needed to fetch, unpack and decompile them yourself. The constants in `data/constants.json` are provided for interoperability and research, in the same spirit as the existing open-source scale projects (openScale, bodymiscale, xiaomi-ble) that this work is intended to feed.

## License

The documentation, data and scripts in this repository are licensed under the [Apache License 2.0](LICENSE). The licence does not cover Xiaomi's firmware. See [NOTICE](NOTICE) for attribution, including RX14's Apache-2.0 body-composition model.
