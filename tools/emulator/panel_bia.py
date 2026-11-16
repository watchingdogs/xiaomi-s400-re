"""Run the S400 BIA routine and decode the full output panel.

Verified identities on h=180.0cm w=75.0kg male 38y z50=520.0 z250=475.0:
  +0x00 fat% 19.50   +0x90 fat mass 14.60 (=19.5%*75)   +0x98 FFM 60.40
  +0x38 BMI 23.10    +0x40 ideal weight 70.00 ((h-80)*0.7)
"""
import struct
import sys

sys.path.insert(0, "/opt/data")
from probe_struct import run

LABELS = {
    0x00: "body fat %",
    0x08: "? (moves with h,w,sex)",
    0x10: "?",
    0x18: "?",
    0x20: "?",
    0x28: "?",
    0x30: "?",
    0x38: "BMI",
    0x40: "ideal weight (kg)",
    0x48: "?",
    0x50: "?",
    0x58: "?",
    0x60: "?",
    0x68: "?",
    0x70: "?",
    0x80: "?",
    0x88: "?",
    0x90: "fat mass (kg)",
    0x98: "fat-free mass (kg)",
    0xa0: "?",
    0xa8: "?",
    0xb0: "?",
}


def panel(h01, w01, sex, age, imp0, imp1):
    buf = bytearray(16)
    struct.pack_into("<H", buf, 0, h01)
    struct.pack_into("<H", buf, 2, w01)
    buf[4] = sex
    buf[5] = age
    buf[6] = 4
    struct.pack_into("<H", buf, 8, imp0)
    struct.pack_into("<H", buf, 10, imp1)
    blob, err = run(buf)
    if blob is None:
        raise SystemExit(err)
    return blob


def show(name, blob):
    print("\n=== %s ===" % name)
    print("  doubles:")
    for off in range(0, 0xC0 - 8, 8):
        v = struct.unpack("<d", blob[off:off + 8])[0]
        if v == v and (abs(v) > 1e-6 or True):
            lab = LABELS.get(off, "")
            print("    +0x%02x  %14.4f   %s" % (off, v, lab))
    print("  shorts:")
    for off in range(0, 0xC0 - 2, 2):
        s = struct.unpack("<h", blob[off:off + 2])[0]
        if s:
            print("    +0x%02x  %d" % (off, s))


if __name__ == "__main__":
    b = panel(1800, 750, 1, 38, 5200, 4750)
    show("male 180.0cm 75.0kg 38y 520/475 ohm", b)
    ffm = struct.unpack("<d", b[0x98:0xa0])[0]
    fat = struct.unpack("<d", b[0x90:0x98])[0]
    print("\n  check: 21.6*FFM + 370 = %.1f" % (21.6 * ffm + 370))
    print("  check: fat mass == fat%%*w/100 -> %.2f" % (struct.unpack("<d", b[0:8])[0] * 75.0 / 100))

    b2 = panel(1650, 600, 2, 30, 6000, 5400)
    show("female 165.0cm 60.0kg 30y 600/540 ohm", b2)
