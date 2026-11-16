# 03 — Protocol: BLE, GATT login, MIoT, records

Two entirely separate channels exist. Most third-party software only uses the first.

| channel | requires | gives |
|---|---|---|
| **Advertisements** (passive) | 16-byte bind key | weight, heart rate, one impedance band per packet — no connection |
| **GATT connection** | 12-byte login token | live stream, full panel, stored records, profile management, work modes |

The bind key and the login token are **different values**. Both come from the Xiaomi cloud (the
community tool *Xiaomi-cloud-tokens-extractor* prints `BLE KEY` = 16 bytes, `Token` = 12 bytes).

---

## 1. Advertisements

24-byte payloads in the service data for UUID `0000fe95-0000-1000-8000-00805f9b34fb`, encrypted with
AES-CCM using the 16-byte bind key:

```
nonce      = mac_reversed(6) || data[2:5] || data[len-7:len-4]
AAD        = 0x11
tag        = 4 bytes at data[len-7:len-4]
ciphertext = data[5 : len-7]
```

Decrypted payload, two 32-bit words:

| bits | field | scale |
|---|---|---|
| 0–10 | weight | 0.1 kg (max 204.7) |
| 11–17 | heart rate | bpm + 50, valid 1–126 (i.e. 51–177) |
| 18–31 | impedance | 0.1 Ω (max 1638.3) |

Two packets are emitted per weighing:

- **Packet A**: `weight != 0` → carries weight, heart rate and the **50 kHz** impedance.
- **Packet B**: `weight == 0` → carries the **250 kHz** impedance only.

`z50 = max(impedance)`, `z250 = min(impedance)`: lower-frequency current cannot cross cell membranes,
so the 50 kHz path is longer and its resistance higher. Getting this round the wrong way is the most
common modelling error.

Advertisement-only integrations therefore see: weight, HR, z50, z250 — nothing else. All body
composition is computed on-device or by the phone.

---

## 2. GATT: services and characteristics

128-bit UUIDs are all `000000XX-0000-1000-8000-00805f9b34fb`:

| short | name here | direction | role |
|---|---|---|---|
| `0x0010` | UPNP | app → dev | control: `24000000` starts login, `21000000` arrives on success |
| `0x0019` | AVDTP | both | authentication exchange (randoms + HMACs) |
| `0x001A` | VEND1A | app → dev | encrypted MIoT payloads |
| `0x001B` | CMTP | dev → app | encrypted MIoT payloads |
| `0x0017` | AVCTP | — | secondary control, used by app builds |
| `0x001C` | VEND1C | — | auxiliary |

Subscribe to `0x0010`, `0x0019`, `0x001A`, `0x001B` at minimum. If a characteristic does not support
write-without-response (common on Windows/WinRT), use write-with-response — the scale accepts both.

---

## 3. Parcel framing

Every message, in both directions and on every channel, is a **parcel**:

```
header : 00 00 <mode> <type> <frame_count u16 LE>
         mode 0x00 = command, 0x01 = ack
ack    : 00 00 01 01     "ready"   (receiver → sender, before frames)
         00 00 01 00     "ok"      (receiver → sender, after frames)
frames : <index u16 LE, starting at 1> || up to 18 bytes of payload
```

Order is always: header → ready → frames → ok. Both sides act as receiver at some point, so both
must send acks.

Parcel `type` values seen:

| type | meaning | channel | direction |
|---|---|---|---|
| `0x0B` | app random (16 B) | 0019 | app → dev |
| `0x0D` | device random (16 B) | 0019 | dev → app |
| `0x0C` | device confirmation (HMAC) | 0019 | dev → app |
| `0x0A` | app confirmation (HMAC) | 0019 | app → dev |
| **`0x00`** | **encrypted MIoT payload** | 001A / 001B | both |

> **Pitfall.** For MIoT data use type `0x00`. With type `0x03` (a plausible-looking guess) the scale
> never sends the ready ack and the request silently dies.

---

## 4. Login handshake

```
app → 0010 : 24 00 00 00                      (start login)
app → 0019 : type 0x0B, app_rand (16 random bytes)
dev → 0019 : type 0x0D, dev_rand (16 bytes)
dev → 0019 : type 0x0C, remote_info (32 bytes = HMAC)
app → 0019 : type 0x0A, local_info (32 bytes = HMAC)
dev → 0010 : 21 00 00 00                      (login OK)
```

Key derivation:

```
HKDF-SHA256(ikm = token(12 B), salt = app_rand || dev_rand,
            info = "mible-login-info", length = 64)
  → dev_key 16 | app_key 16 | dev_iv 4 | app_iv 4

remote_info must equal HMAC-SHA256(dev_key, dev_rand || app_rand)
local_info  =         HMAC-SHA256(app_key, app_rand || dev_rand)
```

A mismatch means the token is wrong or has rotated (re-pairing in Mi Home rotates it). The HMAC check
is also a free way to distinguish "12-byte token" from "32-hex BLE key": only the 12-byte value as-is
passes.

Encrypted payloads on `001A`/`001B`:

```
<counter u16 LE> || AES-CCM(ciphertext || tag(4))
nonce = iv(4) || 00 00 00 00 || counter(2) || 00 00 , AAD = none
app→dev uses app_key/app_iv and its own counter; dev→app uses dev_key/dev_iv and the device's counter
```

---

## 5. MIoT message format

Inside the decrypted payload:

```
u16  header  = 0x2000 | total_length
u16  tid
u8   op
body...
```

| op | meaning | body |
|---|---|---|
| `0x02` | get properties | siid, (piid…) |
| `0x03` | set properties | siid, count, (piid, type/len, value…) |
| `0x04` | action result / property result | — |
| `0x05` | **action** | siid u8, aiid u16, argc u8, (piid u16, type/len u16, value…) |
| `0x06` | action reply | siid, aiid, code |
| `0x07` | **event** (device push) | siid, eiid, argc, (piid, type/len, value…) |

`type/len` word = `(type << 12) | length`; type `1` = uint8, `5` = uint32, `0xA` = string.

Worked example — the records request:

```
0e 20 | 01 00 | 05 | 09 | 01 00 | 01 | 04 00 | 01 10 | 00
 ↑len   ↑tid   ↑op   ↑siid ↑aiid  ↑argc ↑piid  ↑type1/len1 ↑0
```

---

## 6. The MIoT model (`urn:miot-spec-v2:device:scale:0000A07D:yunmai-ms104:1`)

| siid | service | notable members |
|---|---|---|
| 1 | device-information | manufacturer, model, firmware-revision, serial-no |
| 2 | scale | `unit` (1 kg / 2 lb), `heart-rate-detection`, `current-time` |
| 6 | user-management | `miid`, `user-age`, `user-sex` (1 man / 2 woman), `user-type` (1 primary, 2 virtual, 3 visitor), `user-height`, `user-weight`, `time`, `user-id`, `user-bfp`; actions `update-user`, `query-update-user`, `del-user`, `requset-user-list`, `update-base-weight` |
| 8 | online-data | `weight-data` (string), `body-composition` (string); events `eiid 1` (live load), `eiid 2` |
| 9 | **offline-data** | `report-offline-data` (string, eiid 1), `idx-string` (eiid 2), `offline-data-count`, `only-upload-count`; actions `request-offline-data` (aiid 1), `end-of-reception` (aiid 2) |
| 10 | work-mode | `mode` (0 normal, 1 baby, 2 balance, 3 visitor, 4 once), `status`, `balance-time`, `real-weight`; action `wakeup-device` |
| 13 | syncinfo | `pluginversion`, `unit`, `current-time`, `userinfolist`, `offline-msg-cnt`, `sn`, `mac`, `firmwareversion`, `battery` |
| 14 | share-cancel | `share-user-list`; action `del-share-users` |
| 12 | (undocumented) | `eiid 1001` uint8 = 1, seen twice; purpose unknown |

The app writes the profile (age/sex/height/weight) and its own **plugin version** into the scale;
the scale stores them per user and uses the plugin version to decide which report variant to send.
That is why two phones with different app versions get slightly different panels from the same scale.

---

## 7. Stored records

```
app → 001A : action siid 9 / aiid 1, arg piid 4 (uint8) = 0
dev →       : action reply op 0x06, code 0
dev →       : event siid 9 / eiid 2, piid 3 = number of stored records (0 when empty)
dev →       : event siid 9 / eiid 1, piid 1 = the records string
```

- Records are separated by `_`, each is **33 comma-separated integers**.
- **Do not send `end-of-reception` (siid 9 / aiid 2) unless you want them deleted.** Without it the
  records persist and the phone app can still sync them.
- The count is `0` whenever the phone app has already collected them. To capture records, keep the
  phone out of range and weigh.
- Field layout and meaning: `05_FIELDS.md`.

---

## 8. Unsolicited traffic

After login the scale **pushes messages on `001B` by itself** — 12 in one session, 78 in another.
You must receive and ack these before your own request will go through (the scale will not accept a
new parcel while it is waiting for acks).

| message | payload | interpretation |
|---|---|---|
| siid 8 / eiid 1 / piid 1 | string `"N,M"` e.g. `0,0`, `62,0`, `74,0` … `144,4` | live load stream; `N` looks like load/weight, `M` a state flag (4 seen at the end of a weighing) |
| siid 12 / eiid 1001 / piid 1 | uint8 `1` | unknown, seen twice |

The `siid 8 / eiid 1` stream is what the app uses for its settling animation and is a far better
source of sub-second weight than the advertisement path.

---

## 9. Work modes

| mode | behaviour | firmware evidence |
|---|---|---|
| normal (0) | ordinary measurement + full panel | — |
| baby (1) | two-stage: adult baseline held, held-baby reading differenced | `get baby mode weight, w, flag, stable`, `processing baby mode data, weight, flag, status`, `mi_spec_report_baby_mode_statue` |
| balance (2) | timed balance test, not a measurement | `balance mode start, start timing`, `get balance test data, status, time`, `report balance mode data to app, status, time`, `balance time: %d`, timeouts and over-weight exits |
| visitor (3) | measured without saving a profile | `cur visitor user info` kept separately |
| once (4) | single measurement, no profile binding | — |

Only normal mode feeds the composition chain.

---

## 10. Impedance smoothing — fully decoded

`FUN_0081CE6C` implements it. It is **not** an exponential moving average; it is a gated weighted
average of the profile's stored impedance (`user_bodyResZ50/Z250`, kept per user slot) and the
current measurement:

```
d = |user.weight - current.weight|          (same 0.1 kg units)
t = now - user.last_measure_time            (seconds)

if d > 60:            use current impedance unchanged        "no need to smooth impedance"
elif d >= 36:         50% stored + 50% current               "bfp in range 60"
else:  d < 36 →
      if t < 601:     use stored impedance only  (100/0)      "bfp in range 30, time in range 10"
      elif t <= 1800: 80% stored + 20% current               "bfp in range 30, time in range 30"
      else:           50% stored + 50% current               (two log variants by 4 h)
```

So the thresholds in 0.1 kg units are **3.6 kg and 6.0 kg** for the weight gate (0x24 = 36, 0x3C = 60)
and **601 s / 1800 s / 14401 s** (10 min, 30 min, 4 h) for the time windows. The blend is integer
arithmetic, rounded down after dividing by 100:

```
after = (stored * 80 + current * 20) / 100      or      (stored + current) * 50 / 100
```

Observable consequences:

- A first weigh-in on a fresh profile has nothing stored, so it is unsmoothed — the cleanest sample.
- Repeat weigh-ins inside 10 minutes return the **stored** value almost unchanged; this is by design,
  not a defect, and it is why back-to-back readings look "stuck".
- A weight change of more than 6 kg bypasses smoothing entirely.
- The record's `z50`/`z250` fields are the *post-smoothing* values, which is why they reproduce the
  panel exactly (see `04_ALGORITHM.md` §0).

---

## 11. Practical notes

- **Contention.** The phone app holds the GATT link while open. Close it before connecting; whoever
  connects first wins.
- **Records vanish after app sync.** Weigh with the app closed to accumulate records.
- **Wake the scale.** It advertises for a few seconds after a weigh-in and sleeps otherwise. `scan`
  only sees it in that window.
- **Windows.** Use `bleak` — it drives the WinRT stack with no dongle or driver. Write mode must be
  chosen from the characteristic properties; WinRT rejects write-without-response where it is not
  advertised.
- **MTU/frames.** 18-byte frames with ~15 ms gaps work reliably; larger frames are not required.
