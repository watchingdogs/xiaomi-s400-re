#!/usr/bin/env python3
"""Offline decryption sweep for the Xiaomi S400 (ms104) app payload.

The image is a nested container:
  0x00000  48B outer header  magic 41960005, 0x2792, 0x9BF4, 16B const 6d67def1..f40cde01
  0x00030  stage-1 plaintext DFU (40,960 - 48 bytes)
  0x0A000  48B inner header  magic 21810005, 0x2793, 0x1B60C, same 16B const
  0x0A030  ~111 KB payload, entropy 8.0

Sweep tries AES in ECB/CBC/CFB/OFB/CTR, key=bindkey and simple derivations,
several IV choices, several payload offsets, and scores each output.
"""
import collections
import hashlib
import math
import pathlib
import sys

from Crypto.Cipher import AES
from Crypto.Util import Counter

if len(sys.argv) < 2:
    sys.exit("usage: aced_key_sweep.py <bind key, 32 hex chars>")
KEY_HEX = sys.argv[1]
FW = next(p for p in pathlib.Path("/opt/data/fw").iterdir() if "_upd_yunmai.scales.ms104" in p.name)
DATA = FW.read_bytes()
CONST = bytes.fromhex("6d67def16e33e811b1024d2df40cde01")  # placeholder, fixed below
CONST = DATA[12:28]  # actual 16-byte constant from the outer header

WORDISH = {b"\x00\x00", b"\xff\xff"}

def entropy(b):
    if not b:
        return 0.0
    c = collections.Counter(b)
    n = len(b)
    return -sum((v / n) * math.log2(v / n) for v in c.values())

def score(buf):
    """Higher is more plausibly decrypted firmware."""
    head = buf[:65536]
    e = entropy(head)
    runs = len([m for m in __import__("re").finditer(rb"[ -~]{6,}", head)])
    # Thumb BL: 32-bit halfword pairs 11110xxxxxxxxxxx 11xxxxxxxxxxxxxx
    words = [int.from_bytes(head[i:i+4], "big") for i in range(0, len(head) - 4, 2)]
    bl = sum(1 for w in words if (w >> 27) == 0b11110 and ((w >> 14) & 0xF) in (0b11, 0b01, 0b10, 0b00) and (w & 0x3000) == 0x3000)
    blratio = bl / max(1, len(words))
    return dict(entropy=round(e, 2), strings=runs, blratio=round(blratio, 3),
                score=round((8.0 - e) * 10 + min(runs, 200) * 0.3 + blratio * 40, 2)), head

def make_keys(k):
    k = bytes.fromhex(k) if isinstance(k, str) else k
    out = {"raw16": k, "raw16_swapped": k[::-1]}
    if len(k) == 16:
        out["md5"] = hashlib.md5(k).digest()
        out["sha256_16"] = hashlib.sha256(k).digest()[:16]
        out["xor_const"] = bytes(a ^ b for a, b in zip(k, CONST))
        out["const_xor"] = out["xor_const"]
    return out

def try_decrypt(data, key, mode, iv):
    try:
        if mode == "ECB":
            return AES.new(key, AES.MODE_ECB).decrypt(data)
        if mode == "CBC":
            return AES.new(key, AES.MODE_CBC, iv).decrypt(data)
        if mode == "CFB":
            return AES.new(key, AES.MODE_CFB, iv, segment_size=128).decrypt(data)
        if mode == "OFB":
            return AES.new(key, AES.MODE_OFB, iv).decrypt(data)
        if mode == "CTR":
            return AES.new(key, AES.MODE_CTR, counter=Counter.new(128, initial_value=int.from_bytes(iv, "big"))).decrypt(data)
    except Exception:
        return None
    return None

def main():
    print(f"key={KEY_HEX}  file={FW.name}  size={len(DATA):,}")
    keys = make_keys(KEY_HEX)
    ivs = {
        "zero": b"\x00" * 16,
        "hdr_const": CONST,
        "hdr_const_rev": CONST[::-1],
        "last16_of_header": DATA[0xA000:0xA010],
        "bindkey_as_iv": bytes.fromhex(KEY_HEX),
    }
    starts = [0xA000, 0xA010, 0xA020, 0xA030, 0xA040, 0xA050, 0xA060]
    results = []
    for kn, kv in keys.items():
        for ivn, iv in ivs.items():
            for mode in ("ECB", "CBC", "CFB", "OFB", "CTR"):
                if mode == "ECB" and ivn != "zero":
                    continue
                for st in starts:
                    payload = DATA[st:]
                    payload = payload[: len(payload) - (len(payload) % 16)]
                    out = try_decrypt(payload, kv, mode, iv)
                    if out is None:
                        continue
                    s, head = score(out)
                    results.append((s["score"], kn, mode, ivn, st, s, out))
    results.sort(key=lambda r: -r[0])
    print(f"\n{len(results)} combinations tried. Top 10:\n")
    print(f"{'score':>7} {'key':10s} {'mode':4s} {'iv':16s} {'start':>7} {'ent':>5} {'str':>4} {'bl':>5}")
    for sc, kn, mode, ivn, st, s, _ in results[:10]:
        print(f"{sc:7.2f} {kn:10s} {mode:4s} {ivn:16s} 0x{st:05x} {s['entropy']:5.2f} {s['strings']:4d} {s['blratio']:5.3f}")
    # dump the best if it looks like code at all
    best = results[0]
    p = pathlib.Path("/opt/data/fw/decrypt_best.bin")
    p.write_bytes(best[6])
    print(f"\nbest output -> {p}\npreview: {best[6][:64].hex()}")
    txt = __import__("re").findall(rb"[ -~]{6,}", best[6][:65536])[:10]
    print("strings:", [t.decode() for t in txt])
    return results

if __name__ == "__main__":
    main()
