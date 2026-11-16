# 08 — Upstream notes: what to contribute, where, in what shape

Written for whoever takes this to the projects. Ranked by value per unit of effort.

---

## 1. openScale (`oliexdev/openScale`) — the biggest win

Current state: `MiScaleS400Handler` + `S400Decryptor` + `S400Aggregator` read **advertisements only**.
Impedances arrive one band per packet, dedup/aggregation is heuristic, packet loss under BlueZ is
substantial, and there is no history. Their `S400BodyComposition` is deliberately a scientific
(NHANES-refit) model, not the vendor one.

### 1a. GATT offline-record import — highest value

What it buys: no packet loss, both impedances in one record, timestamps, up to 160 weigh-ins per sync,
and multi-user identification. It turns "did the measurement arrive?" into "here is the history".

Implementation surface: the login handshake and framing in `03_PROTOCOL.md` §3–5, the action in §7,
the field map in `05_FIELDS.md` §1. There is a working reference client in `tools/s400_records.py`
(~500 lines, no HA, `bleak` + `cryptography`).

Things to get right:

- parcel `type = 0x00` for MIoT on `001A`;
- buffer and ack the scale's unsolicited `001B` traffic before sending the request;
- do **not** send `end-of-reception` unless deleting from the device is intended;
- write mode from characteristic properties (WinRT rejects write-without-response where unadvertised).

### 1b. Xiaomi calculation mode (optional, clearly labelled)

Their design choice not to fit to the app is right, but users cross-check against Xiaomi Home and file
the difference as a bug. A second backend — "Xiaomi (device firmware)" — is ~120 lines mirroring
`bodycomp/models/xiaomi_home.py`, and we now have a **reference implementation and test vectors**:
`tools/s400_model.py` reproduces 16 record fields bit-exactly.

Credit: algorithm reverse-engineered by RX14 (Apache-2.0), validated on hardware here.

### 1c. Documentation corrections

- The larger impedance is the **50 kHz** one (`z50 = max(imp)`); it carries the fat-relevant signal.
  The 250 kHz band is the smaller value.
- The scale **smooths impedances per profile** across nearby weigh-ins. Passive readers see raw
  values, so repeat weigh-ins legitimately differ from the app. Worth a line in the docs to
  pre-empt "inaccurate" reports.
- Sex encoding inside the device is `0 = female, 1 = male` (MIoT's `user-sex` uses `1 = man,
  2 = woman` — a different convention; do not pass MIoT values straight through).

---

## 2. `dckiller51/bodymiscale`

- The `xiaomi_home.py` model is **confirmed correct for the plain S400**, not just the Pro. That is
  worth stating in the docs and in issue #474's thread: the S400 and S400 Pro run the same algorithm
  (verified here by decompiling the S400 and comparing 16 fields against a live record).
- The three reference deltas (record fields 17–19) are now known and could be exposed — they are the
  "distance from ideal" numbers the app renders as arrows.
- The body-age formula's **structure** (shift bands: −10 … +2, `result = age − shift − 4`, clamps
  18–100 adults / 6–17 youth) is worth documenting even though it is marketing-shaped rather than
  physiological.

---

## 3. `Bluetooth-Devices/xiaomi-ble`

No protocol change needed — advertisements are already handled. Two additions worth having:

- a note that `max(imp)` is the 50 kHz band (a recurring source of confusion);
- the observation that the scale smooths impedances, so `z50`/`z250` from adverts are not directly
  comparable between back-to-back weigh-ins.

---

## 4. HA integrations (`snelstim/ha-xiaomi-s400`, `nokistin/xiaomi-s400-live`, `kbpk/…`)

- The record field map in `05_FIELDS.md` fills in their open TODOs: field 14 is SMM, 17–19 are
  reference deltas, 25/26 are muscle %/bone %, 31/32 are the impedances.
- `tools/s400_records.py` can serve as a reference implementation for the service-9 request and for
  the "buffer unsolicited traffic before requesting" behaviour.
- The live stream (`siid 8 / eiid 1`, `"N,M"`) is a better source for sub-second weight than adverts;
  worth wiring to a sensor.

---

## 5. What *not* to contribute

- **Do not** propose replacing a scientific model with the vendor one. They are different products:
  one aims at physiological plausibility, the other at reproducing an app. Both can coexist.
- **Do not** claim the S400 Pro is verified. It is likely identical (RX14's work + our
  cross-checks) but we did not decompile it. Say "likely, unverified".
- **Do not** distribute firmware binaries. Link the fetch method instead — Xiaomi's OTA endpoint,
  model key, md5. It is the same data, obtained by the user, without redistribution.

---

## 6. Suggested framing for a discussion / issue

> The plain S400 (`ms103`/`ms104`/`ms107`/`ms115`) runs the same body-composition algorithm as the
> S400 Pro. Verified by decompiling firmware 2.1.1_0006 (`bia_calc_t` → `FUN_0083101C`), reproducing
> the panel to floating-point precision, and matching **16 of 33 fields of a real stored record**
> exactly — including three fields that were previously unidentified. The same compiled code is
> present byte-identically (relocated) in the other three variants, so the finding is family-wide.
>
> Separately, the device supports a GATT path that returns both impedances plus a full history in a
> single 33-integer record per weighing, which would remove the packet-loss and packet-pairing
> problems of the advertisement-only path.
>
> Both are documented with reproduction steps and working tooling; feedback on scope and shape
> welcome.
