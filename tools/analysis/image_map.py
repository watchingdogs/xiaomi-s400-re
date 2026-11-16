"""Map the image: find the vector table, code region, and the meaning of the
0x0080xxxx literals. All cheap, no Ghidra, no RAM.
"""
import pathlib
import struct
import collections

out = pathlib.Path("/opt/data/fw")
blob = next(p for p in out.iterdir() if p.name.endswith("_dec_yunmai.scales.ms104.bin")).read_bytes()


def words(o, n):
    return [struct.unpack("<I", blob[o + 4 * k:o + 4 * k + 4])[0] for k in range(n)]


print("=== words 0x00..0x160 ===")
for base in range(0, 0x160, 0x20):
    vals = words(base, 8)
    print("  0x%03x: %s" % (base, " ".join("%08x" % v for v in vals)))

print("\n=== candidate vector table: runs of odd words 0x60..0x400 ===")
for start in range(0x00, 0x200, 4):
    vals = words(start, 48)
    odd = [v for v in vals if v & 1]
    if len(odd) >= 20:
        lo, hi = min(odd), max(odd)
        print("  table@0x%03x odd=%d/48 range 0x%08x-0x%08x" % (start, len(odd), lo, hi))

print("\n=== function-prologue density (0xB5xx push) per 1KB ===")
prof = []
for i in range(0, len(blob) - 4, 1024):
    n = 0
    for j in range(i, min(i + 1024, len(blob) - 2), 2):
        if blob[j] == 0xB5 and blob[j + 1] in (0x10, 0x30, 0x50, 0x70, 0x90, 0xB0, 0xD0, 0xF0, 0x1F, 0x3F):
            n += 1
    prof.append(n)
print("  " + "".join("%X" % min(n, 15) for n in prof))
print("  peak KB: ", [i for i, n in enumerate(prof) if n >= 8][:25])

print("\n=== context of the 48x 0x0080E7A1 literal ===")
locs = [i for i in range(0, len(blob) - 4) if struct.unpack("<I", blob[i:i + 4])[0] == 0x0080E7A1]
print("  count=%d  first offsets=%s" % (len(locs), [hex(x) for x in locs[:10]]))
l = locs[0]
print("  bytes around first:", blob[l - 16:l + 20].hex())
print("  neighbours as words:", ["%08x" % v for v in words(l - 16, 9)])

print("\n=== string cluster boundaries ===")
import re
hits = [m.start() for m in re.finditer(rb"\[[IDWE]\] : ", blob)]
if hits:
    print("  %d log-format strings, first 0x%x last 0x%x" % (len(hits), hits[0], hits[-1]))
print("  ascii density per 1KB (0-9):")
dens = []
for i in range(0, len(blob) - 1024, 1024):
    n = sum(1 for b in blob[i:i + 1024] if 32 <= b < 127)
    dens.append(min(9, n // 40))
print("  " + "".join(str(d) for d in dens))
