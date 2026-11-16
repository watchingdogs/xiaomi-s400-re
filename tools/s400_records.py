#!/usr/bin/env python3
"""s400_records.py - pull the stored weigh-ins off a Xiaomi Body Composition Scale S400.

Standalone: Windows / macOS / Linux, no Home Assistant, no Xiaomi app running.
Speaks the Mi Home v2 BLE protocol (login -> encrypted MIoT action -> read service 9).

    pip install bleak cryptography

Quick start
-----------
  1) Find the scale:            python s400_records.py scan
  2) Get credentials:           Xiaomi-cloud-tokens-extractor (handles 2FA), save its JSON
  3) Read the records:          python s400_records.py fetch --mac AA:BB:CC:DD:EE:FF --cred credentials.json

Credentials JSON is the extractor's output, a list of objects like:
    [{"mac": "AA:BB:CC:DD:EE:FF", "bindkey": "<32 hex>", "token": "<24 hex>", "did": "blt...", "server": "de"}]

Notes
-----
* The scale holds up to ~160 weigh-ins until the official app acknowledges them with
  end-of-reception. This script never sends that acknowledgement, so the Xiaomi app keeps
  working normally.
* Read the records BEFORE opening the Xiaomi Home app if the two are competing for the link.
* Exit code 0 on success, 1 on failure.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import struct
import sys
import time
from dataclasses import dataclass, field

try:
    from bleak import BleakClient, BleakScanner
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESCCM
    from cryptography.hazmat.primitives.hmac import HMAC
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
except ImportError as exc:  # pragma: no cover
    sys.exit("missing dependency (%s) - run: pip install bleak cryptography" % exc)

# ---------------------------------------------------------------- constants
UPNP = "00000010-0000-1000-8000-00805f9b34fb"   # control: login command / result
AVDTP = "00000019-0000-1000-8000-00805f9b34fb"  # auth data parcels
VEND1A = "0000001a-0000-1000-8000-00805f9b34fb"  # app -> device, encrypted
CMTP = "0000001b-0000-1000-8000-00805f9b34fb"    # device -> app, encrypted
AVCTP = "00000017-0000-1000-8000-00805f9b34fb"
VEND1C = "0000001c-0000-1000-8000-00805f9b34fb"

CMD_LOGIN = bytes.fromhex("24000000")
CMD_SEND_KEY = bytes.fromhex("0000000b0100")
CMD_SEND_INFO = bytes.fromhex("0000000a0200")
CMD_SEND_DATA = bytes.fromhex("000000030400")
RCV_RDY = bytes.fromhex("00000101")
RCV_OK = bytes.fromhex("00000100")
CFM_LOGIN_OK = bytes.fromhex("21000000")

OP_ACTION = 0x05
OP_ACTION_REPLY = 0x06
OP_EVENT = 0x07
T_UINT8, T_UINT32, T_STRING = 0x1, 0x5, 0xA

SIID_OFFLINE, AIID_REQUEST, PIID_ONLY_UPLOAD = 9, 1, 4

FRAME_PAYLOAD = 18   # bytes per parcel frame
FRAME_GAP = 0.05     # seconds between frames

# record layout (33 comma-separated integers), from community RE + our own analysis
RECORD_FIELDS = {
    0: ("index", ""), 1: ("account", ""), 2: ("profile", "0 = unrecognised"),
    4: ("weight", "x0.1 kg"), 7: ("timestamp", "unix"),
    8: ("fat%", "x0.1"), 9: ("muscle_kg", "x0.1"), 10: ("water%", "x0.1"),
    11: ("bone_kg", "x0.1"), 12: ("visceral", "level 1-59"), 13: ("protein%", "x0.1"),
    15: ("bmi", "x0.1"), 16: ("ideal_weight", "x0.1 kg"), 21: ("bmr", "kcal"),
    22: ("body_type", "index -5..4"), 23: ("metabolic_age", "years"),
    24: ("body_score", ""), 25: ("muscle%", "x0.1"), 26: ("bone%", "x0.1"),
    27: ("fat_mass", "x0.1 kg"), 28: ("fat_free_mass", "x0.1 kg"),
    29: ("water_mass", "x0.1 kg"), 30: ("protein_mass", "x0.1 kg"),
    31: ("z50", "ohm x0.1"), 32: ("z250", "ohm x0.1"),
}
BODY_TYPES = {-5: "lean", -4: "underweight", -3: "invisibly-obese", -2: "slim-muscular",
              -1: "slim", 0: "fit", 1: "muscular", 2: "overweight", 3: "athletic", 4: "obese"}


# ---------------------------------------------------------------- crypto
def hmac_sha256(key: bytes, data: bytes) -> bytes:
    h = HMAC(key, hashes.SHA256())
    h.update(data)
    return h.finalize()


@dataclass(frozen=True)
class SessionKeys:
    dev_key: bytes
    app_key: bytes
    dev_iv: bytes
    app_iv: bytes


def derive_login_keys(token: bytes, app_rand: bytes, dev_rand: bytes) -> SessionKeys:
    d = HKDF(algorithm=hashes.SHA256(), length=64, salt=app_rand + dev_rand,
             info=b"mible-login-info").derive(token)
    return SessionKeys(d[0:16], d[16:32], d[32:36], d[36:40])


def decrypt_from_device(keys: SessionKeys, raw: bytes) -> bytes | None:
    """raw = <iter u16><ciphertext + 4B tag>; nonce = dev_iv||0^4||iter||0^2."""
    if len(raw) < 6:
        return None
    try:
        return AESCCM(keys.dev_key, tag_length=4).decrypt(
            keys.dev_iv + bytes(4) + raw[:2] + bytes(2), raw[2:], None)
    except Exception:
        return None


def encrypt_for_device(keys: SessionKeys, counter: int, plaintext: bytes) -> bytes:
    it = counter.to_bytes(2, "little")
    return it + AESCCM(keys.app_key, tag_length=4).encrypt(
        keys.app_iv + bytes(4) + it + bytes(2), plaintext, None)


# ---------------------------------------------------------------- MIoT
def miot_action(tid: int, siid: int, aiid: int, args: list[tuple[int, int, object]]) -> bytes:
    body = bytes([OP_ACTION, siid]) + struct.pack("<HB", aiid, len(args))
    for piid, typ, value in args:
        if typ == T_UINT8:
            val = bytes([value & 0xFF])
        elif typ == T_UINT32:
            val = struct.pack("<I", value)
        elif typ == T_STRING:
            val = value.encode()
        else:
            val = bytes(value)
        body += struct.pack("<H", piid) + struct.pack("<H", (typ << 12) | len(val)) + val
    return struct.pack("<HH", 0x2000 | (4 + len(body)), tid) + body


def miot_parse(data: bytes) -> dict | None:
    if len(data) < 5 or (data[1] >> 4) != 0x2:
        return None
    _, tid, op = struct.unpack_from("<HHB", data)
    out = {"tid": tid, "op": op, "values": {}}
    try:
        if op == OP_ACTION_REPLY:
            (out["code"],) = struct.unpack_from("<h", data, 5)
        elif op == OP_EVENT:
            siid, eiid, argc = struct.unpack_from("<BHB", data, 5)
            out.update(siid=siid, eiid=eiid)
            pos = 9
            for _ in range(argc):
                piid, tl = struct.unpack_from("<HH", data, pos)
                pos += 4
                ln = tl & 0x0FFF
                raw = data[pos:pos + ln]
                typ = tl >> 12
                out["values"][piid] = (raw.decode("ascii", "replace") if typ == T_STRING
                                       else int.from_bytes(raw, "little"))
                pos += ln
        else:
            return None
    except struct.error:
        return None
    return out


# ---------------------------------------------------------------- BLE plumbing
class Link:
    """Holds the connected client, per-characteristic queues and the parcel reassembler."""

    def __init__(self, client: BleakClient, verbose: bool):
        self.client = client
        self.verbose = verbose
        self.q = {}
        self._buf = {}
        self._need = {}

    def _log(self, *a):
        if self.verbose:
            print(*a)

    def queue(self, uuid):
        return self.q.setdefault(uuid, asyncio.Queue())

    def callback(self, uuid):
        q = self.queue(uuid)

        def cb(_h, data: bytearray):
            self._log("  <-", uuid[:8], bytes(data).hex(" "))
            q.put_nowait(bytes(data))

        return cb

    async def start(self):
        for uuid in (UPNP, AVDTP, CTM := CMTP, VEND1A, AVCTP, VEND1C):
            try:
                await self.client.start_notify(uuid, self.callback(uuid))
            except Exception:
                pass  # optional characteristics

    async def write(self, uuid, data):
        self._log("  ->", uuid[:8], data.hex(" "))
        await self.client.write_gatt_char(uuid, data, response=False)

    async def send_parcel(self, uuid, payload, header):
        await self.write(uuid, header)
        for i in range(0, len(payload), FRAME_PAYLOAD):
            n = i // FRAME_PAYLOAD + 1
            await self.write(uuid, struct.pack("<H", n) + payload[i:i + FRAME_PAYLOAD])
            await asyncio.sleep(FRAME_GAP)

    async def recv_parcel(self, uuid, timeout=5.0):
        """Reassemble one multi-frame parcel; acks both stages as required."""
        q = self.queue(uuid)
        first = await asyncio.wait_for(q.get(), timeout)
        if len(first) < 6 or first[:3] != b"\x00\x00\x00":
            raise RuntimeError("unexpected first frame: %s" % first.hex())
        count = first[4] | (first[5] << 8)
        await self.write(uuid, RCV_RDY)
        buf = b""
        for _ in range(count):
            frame = await asyncio.wait_for(q.get(), timeout)
            buf += frame[2:]
        await self.write(uuid, RCV_OK)
        return buf

    async def login(self, token: bytes):
        if len(token) != 12:
            raise RuntimeError("token must be 12 bytes (24 hex chars), got %d" % len(token))
        app_rand = secrets.token_bytes(16)
        await self.write(UPNP, CMD_LOGIN)
        await self.write(AVDTP, CMD_SEND_KEY)
        if await asyncio.wait_for(self.queue(AVDTP).get(), 5.0) != RCV_RDY:
            raise RuntimeError("device refused the key parcel")
        await self.send_parcel(AVDTP, app_rand, CMD_SEND_KEY)
        if await asyncio.wait_for(self.queue(AVDTP).get(), 5.0) != RCV_OK:
            raise RuntimeError("device did not ack the key parcel")

        dev_rand = await self.recv_parcel(AVDTP)
        remote_info = await self.recv_parcel(AVDTP)
        if len(dev_rand) != 16:
            raise RuntimeError("bad dev_rand length %d" % len(dev_rand))

        keys = derive_login_keys(token, app_rand, dev_rand)
        if remote_info != hmac_sha256(keys.dev_key, dev_rand + app_rand):
            raise RuntimeError(
                "HMAC mismatch - the 12-byte token is wrong or has rotated "
                "(re-run Xiaomi-cloud-tokens-extractor)")
        await self.write(AVDTP, CMD_SEND_INFO)
        if await asyncio.wait_for(self.queue(AVDTP).get(), 5.0) != RCV_RDY:
            raise RuntimeError("device refused the auth parcel")
        await self.send_parcel(AVDTP, hmac_sha256(keys.app_key, app_rand + dev_rand),
                               CMD_SEND_INFO)
        if await asyncio.wait_for(self.queue(AVDTP).get(), 5.0) != RCV_OK:
            raise RuntimeError("device did not ack the auth parcel")

        result = await asyncio.wait_for(self.queue(UPNP).get(), 5.0)
        if result != CFM_LOGIN_OK:
            raise RuntimeError("login failed, device said %s" % result.hex())
        return keys

    async def send_command(self, keys, plaintext, counter=1):
        await self.send_parcel(VEND1A, encrypt_for_device(keys, counter, plaintext),
                               CMD_SEND_DATA)

    async def recv_message(self, keys, timeout=5.0):
        """One decrypted MIoT message from the device, or None."""
        raw = await self.recv_parcel(CMTP, timeout)
        return decrypt_from_device(keys, raw)


# ---------------------------------------------------------------- commands
async def _discover(timeout):
    """[(device, advertisement_or_None)] - tolerant of bleak version differences."""
    try:
        found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    except TypeError:                    # bleak < 0.19
        found = await BleakScanner.discover(timeout=timeout)
        return [(d, None) for d in found]
    if isinstance(found, dict):          # address -> (device, adv)
        pairs = []
        for v in found.values():
            if isinstance(v, (tuple, list)) and len(v) >= 1:
                pairs.append((v[0], v[1] if len(v) > 1 else None))
            else:
                pairs.append((v, None))
        return pairs
    return [(d, None) for d in found]     # list of devices


async def cmd_scan(args):
    t = float(getattr(args, "timeout", 8.0) or 8.0)
    print("scanning for %d s ..." % t)
    pairs = await _discover(t)
    rows = []
    for dev, adv in pairs:
        name = getattr(adv, "local_name", None) or getattr(dev, "name", None) or ""
        uuids = [u.lower() for u in (getattr(adv, "service_uuids", None) or [])]
        rssi = getattr(adv, "rssi", None)
        if rssi is None:
            rssi = getattr(dev, "rssi", None)
        hit = ("fe95" in " ".join(uuids)
               or any(k in name.lower() for k in ("s400", "mijia", "xiaomi", "scale")))
        if hit or getattr(args, "all", False):
            rows.append((getattr(dev, "address", "?"), name or "?", rssi))
    print("saw %d device(s), %d with a Xiaomi signature" % (len(pairs), len(rows)))
    if not rows:
        print("")
        print("Nothing matching. The scale only advertises for a few seconds after a")
        print("weigh-in - step on it, then run the scan immediately. If it still does")
        print("not appear, try:  py s400_records.py scan --all")
        return 1
    print("%-20s %-30s %s" % ("MAC", "name", "rssi"))
    for a, n, r in sorted(rows, key=lambda x: (x[2] is None, -(x[2] or -999))):
        print("%-20s %-30s %s" % (a, n, "?" if r is None else r))
    return 0


async def cmd_fetch(args):
    mac, token = args.mac.upper(), None
    if args.cred:
        raw = json.loads(open(args.cred, encoding="utf-8").read())
        if isinstance(raw, dict):
            raw = [raw]
        for entry in raw:
            if entry.get("mac", "").upper() == mac:
                token = bytes.fromhex(entry["token"])
                break
        if token is None:
            sys.exit("MAC %s not in %s" % (mac, args.cred))
    if args.token:
        token = bytes.fromhex(args.token)
    if token is None or len(token) != 12:
        sys.exit("need a 12-byte token: --token <24 hex> or --cred <extractor.json>")

    print("connecting to %s ..." % mac)
    async with BleakClient(mac, timeout=20.0) as client:
        if not client.is_connected:
            sys.exit("could not connect")
        print("connected; logging in ...")
        link = Link(client, args.debug)
        await link.start()
        keys = await link.login(token)
        print("logged in.")

        msg = miot_action(1, SIID_OFFLINE, AIID_REQUEST,
                          [(PIID_ONLY_UPLOAD, T_UINT8, 0)])
        print("requesting stored records ...")
        await link.send_command(keys, msg)

        records_text = None
        count = None
        deadline = time.time() + args.timeout
        while time.time() < deadline and records_text is None:
            try:
                plain = await link.recv_message(keys, timeout=min(5.0, args.timeout))
            except asyncio.TimeoutError:
                continue
            if plain is None:
                continue
            parsed = miot_parse(plain)
            if not parsed:
                continue
            if args.debug:
                print("   miot:", parsed)
            if parsed["op"] == OP_ACTION_REPLY:
                print("   request acked (code %d)" % parsed.get("code", 0))
            elif parsed.get("siid") == SIID_OFFLINE and parsed.get("eiid") == 2:
                count = parsed["values"].get(3)
                print("   device reports %s record(s)" % count)
            elif parsed.get("siid") == SIID_OFFLINE and parsed.get("eiid") == 1:
                records_text = parsed["values"].get(1, "")
                break

        if not records_text:
            print("no records received (empty history, or the app already synced them)")
            return 1
        return emit_records(records_text, args)


def parse_records(text: str):
    out = []
    for chunk in text.split("_"):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            f = [int(x) for x in chunk.split(",")]
        except ValueError:
            continue
        if len(f) >= 33:
            out.append(f)
    return out


def emit_records(text: str, args):
    recs = parse_records(text)
    print("\n%d record(s):\n" % len(recs))
    for i, f in enumerate(recs):
        w = f[4] / 10.0
        print("#%d  %s  profile %d  %.1f kg  z50 %.1f  z250 %.1f  fat %.1f%%  bmr %d  age %d  type %s" % (
            i, time.strftime("%Y-%m-%d %H:%M", time.localtime(f[7])) if f[7] else "?",
            f[2], w, f[31] / 10.0, f[32] / 10.0, f[8] / 10.0, f[21], f[23],
            BODY_TYPES.get(f[22], f[22])))
        if args.height and args.age and args.sex:
            pred, score = predict_body_age(
                args.height, w, args.age, args.sex.lower().startswith("m"),
                f[8] / 10.0, f[28] / 10.0, f[9] / 10.0, f[21])
            delta = f[23] - pred
            print("      body age: device %d, model %d (score %.2f) -> %s" % (
                f[23], pred, score,
                "MATCH" if delta == 0 else "off by %+d year(s)" % delta))
        if args.verbose:
            for idx in sorted(RECORD_FIELDS):
                name, note = RECORD_FIELDS[idx]
                print("      [%2d] %-14s %8d  %s" % (idx, name, f[idx], note))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump({"raw": text, "records": recs}, fh, indent=1)
        print("\nwritten to %s" % args.out)
    if args.csv:
        import csv
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["idx"] + [RECORD_FIELDS.get(i, ("f%d" % i, ""))[0] for i in range(33)])
            for f in recs:
                w.writerow(list(range(0, 1)) + f)
        print("written to %s" % args.csv)
    return 0


def _r01(x: float) -> float:
    import math
    return math.floor(x * 10 + 0.5) / 10 if x >= 0 else math.ceil(x * 10 - 0.5) / 10


_BMI_MID = {
    True: (15.0, 15.2, 15.45, 15.8, 16.25, 16.75, 17.35, 18.0, 18.75, 19.5, 20.2, 20.75, 22.0),
    False: (14.95, 15.15, 15.4, 15.85, 16.35, 17.0, 17.75, 18.5, 19.25, 19.9, 20.3, 20.65, 21.0),
}
_BFP_MID_F = (16.0, 16.0, 17.0, 18.0, 19.0, 20.0, 21.0, 22.0, 23.0)
_AGE_COEF = {True: (-1.48615435, 0.129089458, 0.591458258, -0.000405611446),
             False: (-1.0136192, 0.107155831, 0.277336024, -0.0349702346)}


def predict_body_age(height_cm, weight_kg, age, male, fat_pct, lbm_kg, muscle_kg, bmr):
    """The model from S400_ALGORITHM_REFERENCE.md 4.1 - used to test the device's value."""
    age_i = int(age)
    band = min(max(age_i, 6), 18) - 6
    bmi_mid = _BMI_MID[male][band]
    if male:
        bfp_mid = 15.0
    elif age_i >= 14:
        bfp_mid = 23.0
    else:
        bfp_mid = _BFP_MID_F[min(max(age_i, 6), 13) - 6]

    std_w = _r01(bmi_mid * height_cm * height_cm / 10000.0)
    ref_lbm = _r01((100 - bfp_mid) * std_w / 100.0)
    ref_bmr = int(21.6 * ref_lbm + 370.5)
    ref_muscle_pct = _r01((100 - bfp_mid) * 0.944)

    c = _AGE_COEF[age_i >= 18]
    muscle_pct = _r01(muscle_kg / weight_kg * 100.0)
    score = ((weight_kg - std_w) * c[0]
             + (bmr - ref_bmr) * c[1]
             + (fat_pct - bfp_mid) * c[2]
             + (muscle_pct - ref_muscle_pct) * c[3]) / 2.5

    if age_i < 18:
        shift = -1 if score < -2 else (1 if score >= 2 else 0)
        return int(max(6, min(17, age_i + shift))), round(score, 3)
    if score < -10:
        shift = -10
    elif score >= 2:
        shift = 2
    elif score >= 0:
        shift = int(score) + 1
    else:
        shift = int(score)
    return int(max(18, min(100, age_i - shift - 4))), round(score, 3)


def cmd_selftest(_args):
    ok = True

    # 1. MIoT action must reproduce the exact bytes captured from a working session
    got = miot_action(1, 9, 1, [(4, T_UINT8, 0)]).hex()
    want = "0e20010005090100010400011000"
    print("miot action   %s  %s" % (got, "OK" if got == want else "MISMATCH (want %s)" % want))
    ok &= got == want

    # 2. HKDF is deterministic and 64 bytes
    a = derive_login_keys(bytes(12), bytes(16), bytes(16))
    print("hkdf          %d/%d/%d/%d bytes  %s" % (
        len(a.dev_key), len(a.app_key), len(a.dev_iv), len(a.app_iv),
        "OK" if (len(a.dev_key), len(a.app_iv)) == (16, 4) else "BAD"))
    ok &= len(a.dev_key) == 16 and len(a.app_iv) == 4

    # 3. AES-CCM round-trip through the device-side decryptor
    k = derive_login_keys(b"123456789012", b"A" * 16, b"B" * 16)
    body = miot_action(7, 9, 1, [(4, T_UINT8, 0)])
    blob = body
    it = (5).to_bytes(2, "little")
    ct = AESCCM(k.app_key, tag_length=4).encrypt(k.app_iv + bytes(4) + it + bytes(2), blob, None)
    back = decrypt_from_device(SessionKeys(k.app_key, k.app_key, k.app_iv, k.app_iv), it + ct)
    print("aes-ccm       %s  %s" % (back == blob, "OK" if back == blob else "FAIL"))
    ok &= back == blob

    # 4. record parser on a known-good line
    line = ",".join(str(x) for x in [42, 1234567, 1, 1, 750, 0, 1, 1790000000, 200, 565, 580,
                                     32, 7, 170, 310, 231, 700, 0, 0, 0, 0, 1666, 4, 38, 82, 753,
                                     43, 150, 600, 435, 128, 5200, 4750, 0])
    r = parse_records(line)
    print("record parse  %d record, %.1f kg  %s" % (
        len(r), r[0][4] / 10.0 if r else -1, "OK" if r and r[0][4] == 750 else "FAIL"))
    ok &= bool(r) and r[0][4] == 750

    pred, score = predict_body_age(180, 75, 38, True, 19.5, 60.4, 57.1, 1675)
    print("body-age calc %d (score %.3f)  %s" % (
        pred, score, "OK" if pred == 35 else "MISMATCH (want 35)"))
    ok &= pred == 35

    print("\n%s" % ("all self-tests passed" if ok else "SELF-TEST FAILED"))
    return 0 if ok else 1


def main():
    p = argparse.ArgumentParser(description="Read stored weigh-ins from a Xiaomi S400 over BLE.")
    p.add_argument("--debug", action="store_true", help="log every BLE frame")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="list nearby Xiaomi BLE devices")
    s.set_defaults(func=lambda a: asyncio.run(cmd_scan(a)))

    f = sub.add_parser("fetch", help="log in and read the stored records")
    f.add_argument("--mac", required=True)
    f.add_argument("--cred", help="JSON from Xiaomi-cloud-tokens-extractor")
    f.add_argument("--token", help="12-byte token as 24 hex chars (alternative to --cred)")
    f.add_argument("--out", help="write raw + parsed records to this JSON file")
    f.add_argument("--csv", help="write records to this CSV file")
    f.add_argument("--timeout", type=float, default=20.0, help="seconds to wait for records")
    f.add_argument("--verbose", action="store_true", help="print every field of every record")
    f.add_argument("--height", type=int, help="your height in cm (enables the body-age check)")
    f.add_argument("--age", type=int, help="your age in years")
    f.add_argument("--sex", choices=["m", "f"], help="your sex")
    f.set_defaults(func=lambda a: asyncio.run(cmd_fetch(a)))

    t = sub.add_parser("selftest", help="run offline self-tests (no hardware)")
    t.set_defaults(func=cmd_selftest)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
