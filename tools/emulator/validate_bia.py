"""Validate the emulated S400 BIA against the published Xiaomi (RX14) model."""
import math
import struct
import sys

sys.path.insert(0, "/opt/data")
from probe_struct import run


def emu(h_cm, w_kg, sex, age, z50, z250):
    buf = bytearray(16)
    struct.pack_into("<H", buf, 0, int(round(h_cm * 10)))
    struct.pack_into("<H", buf, 2, int(round(w_kg * 10)))
    buf[4] = sex
    buf[5] = age
    buf[6] = 4
    struct.pack_into("<H", buf, 8, int(round(z50 * 10)))
    struct.pack_into("<H", buf, 10, int(round(z250 * 10)))
    blob, err = run(buf)
    if blob is None:
        raise SystemExit(err)
    d = {o: struct.unpack("<d", blob[o:o + 8])[0] for o in range(0, 0xB8, 8)}
    return d


def model_fat(h, w, age, z50, male):
    c = (-0.3315, 0.6216, 0.0183, 0.0085, 22.554) if male else (-0.3332, 0.7509, 0.0196, 0.0072, 22.7193)
    v = 100.0 * (c[0] * h + c[1] * w + c[2] * age + c[3] * z50 + c[4]) / w
    return max(3.0, min(55.0, v))


CASES = [
    (180, 75, 1, 38, 520.0, 475.0),
    (180, 75, 1, 38, 480.0, 430.0),
    (165, 60, 2, 30, 600.0, 540.0),
    (172, 88, 1, 55, 430.0, 390.0),
    (158, 52, 2, 22, 640.0, 580.0),
]

print("%-28s %8s %8s %8s   %8s %8s" % ("case", "emu_fat", "model", "delta", "emu_FFM", "w-fat"))
for h, w, sex, age, z50, z250 in CASES:
    d = emu(h, w, sex, age, z50, z250)
    fat_emu, ffm = d[0x00], d[0x98]
    m = model_fat(h, w, age, z50, sex == 1)
    print("%-28s %8.2f %8.2f %+8.2f   %8.2f %8.2f" % (
        "%dcm %dkg %s %dy" % (h, w, "M" if sex == 1 else "F", age),
        fat_emu, m, fat_emu - m, ffm, w - round(fat_emu / 100 * w, 1)))
