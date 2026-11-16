"""Dump the constant pool raw and decode at every 4-byte offset, both ways."""
import pathlib
import struct

BASE = 0x0080E000
img = next(p for p in pathlib.Path("/opt/data/fw").iterdir()
           if p.name.endswith("_dec_yunmai.scales.ms104.bin")).read_bytes()

REGIONS = [(0x831470, 0x8314c0), (0x8318b0, 0x831900), (0x831d50, 0x831dd0),
           (0x8321b0, 0x8321f0)]

for start, end in REGIONS:
    print("\n=== 0x%08x .. 0x%08x ===" % (start, end))
    off = start - BASE
    for i in range(0, end - start, 4):
        a = start + i
        w = struct.unpack("<I", img[off + i:off + i + 4])[0]
        # high-word-only constant: low word zero, high = w
        as_hi = struct.unpack("<d", b"\x00\x00\x00\x00" + struct.pack("<I", w))[0]
        # full double starting here
        full = struct.unpack("<d", img[off + i:off + i + 8])[0]
        flag = ""
        if abs(as_hi - round(as_hi, 4)) < 1e-3 and 0.4 < abs(as_hi) < 20000:
            flag = "  <-- hi-word const %.4g" % as_hi
        print("  0x%08x  hw=0x%08x  full=%20.12g%s" % (a, w, full, flag))
