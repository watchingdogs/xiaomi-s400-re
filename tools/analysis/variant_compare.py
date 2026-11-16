"""Compare the S400 firmware family: do they share the bia_calc code and constants?

Also checks the S400 Pro SPI dump (uncompressed flash) for the same code.
"""
import hashlib
import pathlib
import re
import struct

FW = pathlib.Path("/opt/data/fw")

IMAGES = {
    "ms104 (S400 intl)": FW / "ac2deeb70c29d94578aecaec3a7e53a0_dec_yunmai.scales.ms104.bin",
    "ms103 (S400 CN)": FW / "ec9e164a1f2cfabb8d94d10742db4596_dec_yunmai.scales.ms103.bin",
    "ms107 (?)": FW / "ebbfba21a04a09759eca97db44c7ce76_dec_yunmai.scales.ms107.bin",
    "ms115 (S400 JP/KR)": FW / "e3cc8ad3b7d8f73e802fd52db24aa558_dec_xiaomi.scales.ms115.bin",
}

STRINGS = [
    b"bia_calc_t 1:",
    b"bmr %d,bt %d,ma %d",
    b"miid %llu,duid %d",
    b"bmc %d,vfr %d,pp %d",
    b"impedance_50KHZ",
    b"impedance_smoothing",
    b"mi_spec_report_body_composition",
    b"send body composition to BLE peer",
]

# doubles that define the algorithm
CONSTS = {
    "21.6 (bmr slope)": 21.6,
    "370.0 (bmr intercept)": 370.0,
    "0.944 (ref muscle)": 0.944,
    "-0.3315 (bf male)": -0.3315,
    "0.6216 (bf male)": 0.6216,
    "22.554 (bf male)": 22.554,
    "-0.3332 (bf fem)": -0.3332,
    "0.7509 (bf fem)": 0.7509,
    "-1.48615435 (age adult)": -1.48615435,
    "-1.0136192 (age youth)": -1.0136192,
}


def find_double(blob, v):
    hits = []
    for fmt in ("<d", ">d"):
        pat = struct.pack(fmt, v)
        i = blob.find(pat)
        while i != -1 and len(hits) < 3:
            hits.append(i)
            i = blob.find(pat, i + 1)
    return hits


def code_hash(blob, start=0x2301C, length=0x4000):
    if len(blob) < start + length:
        return "short"
    return hashlib.sha256(blob[start:start + length]).hexdigest()[:16]


print("=" * 78)
print("compressed images")
rows = []
base = None
for name, p in IMAGES.items():
    blob = p.read_bytes()
    found = {s.decode(): blob.count(s) for s in STRINGS}
    consts = {k: len(find_double(blob, v)) for k, v in CONSTS.items()}
    h = code_hash(blob)
    if base is None:
        base = blob
    same = sum(1 for a, b in zip(base[0x2301C:0x2701C], blob[0x2301C:0x2701C]) if a == b)
    rows.append((name, len(blob), h, same, found, consts))

for name, size, h, same, found, consts in rows:
    print("\n%-22s size=%d  bia_calc-region sha=%s  bytes-equal-to-ms104=%d/16384"
          % (name, size, h, same))
    print("   strings : " + ", ".join("%s=%d" % (k[:26], v) for k, v in found.items()))
    print("   consts  : " + ", ".join("%s=%d" % (k[:22], v) for k, v in consts.items()))

print()
print("=" * 78)
print("S400 Pro SPI dump (uncompressed flash, 8 MB)")
pro = (FW / "dump_P25Q64SH_S400Pro.bin").read_bytes()
print("   strings : " + ", ".join("%s=%d" % (s.decode()[:26], pro.count(s)) for s in STRINGS))
print("   consts  : " + ", ".join("%s=%d" % (k[:22], len(find_double(pro, v))) for k, v in CONSTS.items()))
for pat in (b"\x0e\x20\x01\x00\x05\x09", b"offline flash", b"report-offline"):
    print("   %-22s %d" % (pat.decode(errors="replace")[:22], pro.count(pat)))
