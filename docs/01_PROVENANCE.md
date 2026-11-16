# 01 — Provenance: where the firmware came from

## 1. Models in the S400 family

| model string | marketing name | regions | notes |
|---|---|---|---|
| `yunmai.scales.ms103` | 米家体脂秤 S400 | CN | retail project id 3399 on the mindsolo mirror |
| `yunmai.scales.ms104` | Xiaomi Body Composition Scale S400 (MJTZC01YM / BHR7793GL) | sg, de, us, ru | **the device dissected here** |
| `yunmai.scales.ms107` | Xiaomi Body Composition Scale S400 | — | listed alongside ms103/ms104 by community integrations |
| `xiaomi.scales.ms115` | Xiaomi Body Composition Scale S400 | JP, KR | first registered 2024-11-04 |
| `xiaomi.scales.ms110` | Xiaomi Body Composition Scale **S400 Pro** (MJTZC03YM) | — | different SoC generation, sealed container |

Distinguish `ms110` (Pro) from the rest: the Pro's OTA container starts with magic `55AAAA55`,
is 834,662 bytes, and is not LZMA/zstd/lz4. The four non-Pro variants share the same container
format and, as shown in `06_MODEL_COVERAGE.md`, the same application code.

## 2. Firmware versions examined

| model | version | OTA file | size | md5 |
|---|---|---|---|---|
| ms104 | 2.1.1_0006 | `ac2deeb70c29d94578aecaec3a7e53a0_upd_yunmai.scales.ms104.bin` | 153,196 | `ac2deeb70c29d94578aecaec3a7e53a0` |
| ms103 | 2.1.1_0057 | `ec9e164a1f2cfabb8d94d10742db4596_upd_yunmai.scales.ms103.bin` | 152,940 | `ec9e164a1f2cfabb8d94d10742db4596` |
| ms107 | 2.1.1_0003 | `ebbfba21a04a09759eca97db44c7ce76_upd_yunmai.scales.ms107.bin` | 152,972 | `ebbfba21a04a09759eca97db44c7ce76` |
| ms115 | 2.1.1_0009 | `e3cc8ad3b7d8f73e802fd52db24aa558_upd_xiaomi.scales.ms115.bin` | 154,000 | `e3cc8ad3b7d8f73e802fd52db24aa558` |
| ms110 | 2.1.1_0063 | `6d4d7351eb487017ad0fdfb57cd241ed_upd_xiaomi.scales.ms110.bin` | 834,662 | `6d4d7351eb487017ad0fdfb57cd241ed` |

Each model also ships a separate **MCU image** (12,309 bytes for the non-Pro variants), unrelated to
the application firmware and not needed for anything in this knowledge base.

Provenance: all files were downloaded from Xiaomi's own OTA CDN and MD5-verified against the value
the API returned for that model. The full SPI flash dump of an S400 **Pro** used as a cross-check
(`dump_P25Q64SH_S400Pro.bin`, 8,388,608 bytes, sha256 `1f5980e3…d75c84`) comes from the public
repository `waw555/XIAOMI-MIJIA-BODY-FAT-SCALE-S400-PRO`.

## 3. How the firmware was obtained

Xiaomi serves OTA images through a model-keyed endpoint that does **not** require the device to be
bound to the account:

```
POST https://<region>.api.io.mi.com/app/home/latest_version
body: {"model": "yunmai.scales.ms104"}
→ {"version": "2.1.1_0006", "url": "<signed CDN url>", "md5": "...", "upload_time": ...}
```

Details that matter:

- Requests must be signed (`micloud` does this: `_signature`, `ssecurity` nonce). An unauthenticated
  POST returns `401 auth error`.
- **Region matters.** The China host (`api.io.mi.com`) serves ms103 and ms110 but returns nothing for
  ms104/ms115. ms104 is served by `de.`, `sg.`, `us.api.io.mi.com`; ms115 appears on `sg.` with a
  `country` parameter.
- The signed URL is time-limited (weeks), so re-query if it 403s.
- The account does not need any bound devices — a throwaway account with zero devices returns the
  full record set.

`tools/xiaomi_fw_fetch.py` implements this. Note the account creation itself is reCAPTCHA-gated
(Google reCAPTCHA Enterprise on the signup page); login is not, so an existing account works headless.

An older mirror (`vacuum.mindsolo.net`) lists the same files with versions and changelogs but gates
downloads behind a Google/Yandex login and returns `"url": null` to anonymous clients. Useful for
version history, not for acquisition.

## 4. Container format (non-Pro variants)

```
offset      size      content
0x00000     48        outer header
                      05 00 96 41 | 27 92 | 9B F4 | 16-byte constant 6d67def1 3e33e811 b1024d2d f40cde01
0x00030     40912     stage-1: plaintext Thumb-2 DFU code (byte-identical in ms103/104/107/115)
0x0A000     48        inner header
                      05 00 81 21 | 27 93 | 0C B6 01 | same 16-byte constant
0x0A068     ~100 KB   application payload: 12 concatenated LZMA streams
```

Each LZMA stream begins `5D 00 10 00 00` (LZMA-alone, `lc=3 lp=0 pb=2`, **4 KiB dictionary**,
16,384-byte output each; the last stream is short). `tools/s400_extract.py` walks them by parsing
the 8-byte uncompressed size, and produces a flat image of **182,388 bytes** for ms104.

The payload is **compressed, not encrypted**. An earlier claim in the community (that 2.1.1_0006 has
an encrypted main firmware with only the bootloader readable) is wrong — 882 combinations of
AES modes/paddings with the BLE bind key produce nothing because there is no cipher involved.
The bind key is only the AES-CCM key for advertisements.

## 5. Load address and SoC

- SoC: **Realtek RTL8762C**, Cortex-M4F, BLE 5.0, with Xiaomi's `mible` stack over Realtek
  `RTK_BLE` / `RTK_NVM` / `RTK_GATT`; SDK string `1.2.1.248`, build date `Fri Mar 20 17:12:50 2020`.
- Image load address: **0x0080E000**. Evidence: header fields `0x0080E400` / `0x0080E000`; the
  literal pool next to the VTOR write (`0xE000ED08`) holds `0x0080E7A1` (48 references) and
  `0x0083A128`, both inside `[0x0080E000, 0x0080E000+182388)`; importing at that base makes string
  references resolve.
- The second processor is an **M91** MCU on UART1, used for measurement and for its own firmware
  update. Its command vocabulary is version/DFU only (`MIBLE_MCU_GET_VERSION`, `READ_DFUINFO`,
  `WRITE_DFUINFO`, `WRITE_FIRMWARE`, `VERIFY_FIRMWARE`, `UPGRADE_FIRMWARE`, `TRANSFER`) — **no BIA
  command**, so the body-composition maths runs on the RTL8762C, not the MCU.

## 6. File inventory used in this work

| local file | what it is |
|---|---|
| `*_upd_*.bin` | OTA containers exactly as downloaded (md5-verified) |
| `*_dec_*.bin` | flat decompressed images produced by `s400_extract.py` |
| `*_mcu_*.bin` | M91 MCU images from the same OTA records |
| `dump_P25Q64SH_S400Pro.bin` | full SPI NOR dump of an S400 Pro (cross-check only) |

None of these binaries are distributed with this knowledge base; `data/checksums.txt` records their
hashes so any copy can be verified, and the fetch/extract tooling reproduces them.
