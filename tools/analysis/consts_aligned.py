"""Decode the S400 constant pool correctly: doubles are passed as (lo,hi) word
pairs, so a pair (DAT_a, DAT_a+4) is one double, and (0, DAT_a) means the low
word is a literal zero.
"""
import pathlib
import re
import struct

BASE = 0x0080E000
img = next(p for p in pathlib.Path("/opt/data/fw").iterdir()
           if p.name.endswith("_dec_yunmai.scales.ms104.bin")).read_bytes()


def word(addr):
    off = addr - BASE
    return struct.unpack("<I", img[off:off + 4])[0]


def dbl(addr):
    return struct.unpack("<d", img[addr - BASE:addr - BASE + 8])[0]


src = pathlib.Path("/tmp/decomp/FUN_0083101c.c").read_text()

# every "DAT_x,DAT_y" adjacent pair in the source
pairs = re.findall(r"DAT_([0-9a-f]{8}),DAT_([0-9a-f]{8})", src)
seen = {}
for lo_s, hi_s in pairs:
    lo, hi = int(lo_s, 16), int(hi_s, 16)
    if hi != lo + 4:
        continue
    seen[lo] = dbl(lo)

print("aligned constant pairs: %d" % len(seen))
print("\n%-12s %22s" % ("addr", "double"))
for a in sorted(seen):
    print("0x%08x  %22.10g" % (a, seen[a]))

# (0, DAT_x) form -> low word zero, high word from memory
zero_hi = re.findall(r",0,DAT_([0-9a-f]{8})\)", src)
vals = set()
for h in zero_hi:
    a = int(h, 16)
    vals.add(struct.unpack("<d", b"\x00\x00\x00\x00" + img[a - BASE:a - BASE + 4])[0])
print("\n(0,hi) constants: %s" % ", ".join("%.10g" % v for v in sorted(vals)))
