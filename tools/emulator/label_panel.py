"""Identify every panel field by matching against the Xiaomi formulas."""
import math
import struct
import sys

sys.path.insert(0, "/opt/data")
from probe_struct import run

_WATER = (2935892, 149065, -468183, 589094, -63286091, -778045, 23941529, -29784715, 424044966)
_BONE = (118543, 26106, -45544, 48749, -2271994, -155662, 2151182, -2248649, 12272558)
_SOLIDS = (160696, 28769, -60093, 65412, -3163648, -169504, 2860478, -3043837, 18045896)
_SMM = (2475795, 118673, -457174, 556218, -53616294, -574893, 23989719, -28648257, 352065003)
_VISC = (-1849883, 424124, 366784, -455322, 39648934, -359012, -20035428, 24213934, -265509571)
_FAT = {1: (-0.3315, 0.6216, 0.0183, 0.0085, 22.554), 0: (-0.3332, 0.7509, 0.0196, 0.0072, 22.7193)}


def r01(x):
    return math.floor(x * 10 + 0.5) / 10 if x >= 0 else math.ceil(x * 10 - 0.5) / 10


def reg(k, h, w, z50, z250):
    return (k[0] * h + k[1] * w + k[2] * z50 + k[3] * z250 + k[4] * math.sqrt(h)
            + k[5] * math.sqrt(w) + k[6] * math.sqrt(z50) + k[7] * math.sqrt(z250) + k[8]) / 1e6


def expected(h, w, age, sex, z50, z250):
    c = _FAT[sex]
    fat = max(3.0, min(55.0, 100.0 * (c[0] * h + c[1] * w + c[2] * age + c[3] * z50 + c[4]) / w))
    fat_mass = r01(fat / 100.0 * w)
    lbm = w - fat_mass
    bone = reg(_BONE, h, w, z50, z250)
    bone = 0.0 if r01(bone) < 0.3 else max(0.0, min(5.0, bone))
    solids = r01(reg(_SOLIDS, h, w, z50, z250))
    water = r01(r01(reg(_WATER, h, w, z50, z250)) + 3.0 * w / 100.0)
    water = r01(max(20.0, min(85.0, r01(water / w * 100.0))) * w / 100.0)
    protein_pct = (lbm - solids - water) / w * 100.0
    protein = r01(max(5.0, min(32.0, r01(protein_pct))) * w / 100.0)
    muscle = max(7.0, min(141.5, lbm - r01(bone)))
    smm = reg(_SMM, h, w, z50, z250)
    smm = max(0.45 * r01(muscle), min(0.70 * r01(muscle), smm))
    visc = max(1, min(59, int(reg(_VISC, h, w, z50, z250) + 0.5)))
    bmr = 21.6 * r01(lbm) + 370.0
    return {
        "fat%": fat, "fat_mass": fat_mass, "lbm": lbm, "bone": bone, "solids": solids,
        "water_mass": water, "water%": r01(water) / w * 100.0, "protein_mass": protein,
        "protein%": max(5.0, min(32.0, protein_pct)), "muscle": muscle, "smm": smm,
        "visceral": visc, "bmr": bmr, "bmi": w / (h / 100.0) ** 2,
        "ideal": (h - 80) * 0.7 if sex else (h - 70) * 0.6,
    }


def emu_panel(h, w, sex, age, z50, z250):
    buf = bytearray(16)
    struct.pack_into("<H", buf, 0, int(round(h * 10)))
    struct.pack_into("<H", buf, 2, int(round(w * 10)))
    buf[4], buf[5], buf[6] = sex, age, 4
    struct.pack_into("<H", buf, 8, int(round(z50 * 10)))
    struct.pack_into("<H", buf, 10, int(round(z250 * 10)))
    blob, err = run(buf)
    if blob is None:
        raise SystemExit(err)
    return blob


if __name__ == "__main__":
    cases = [(180, 75, 1, 38, 520.0, 475.0), (165, 60, 0, 30, 600.0, 540.0)]
    for h, w, sex, age, z50, z250 in cases:
        blob = emu_panel(h, w, sex, age, z50, z250)
        exp = expected(h, w, age, sex, z50, z250)
        print("\n=== %dcm %dkg %s %dy  z=%.0f/%.0f ===" % (h, w, "M" if sex else "F", age, z50, z250))
        print("  %-12s %10s   best panel match" % ("quantity", "formula"))
        for name, val in sorted(exp.items(), key=lambda kv: -abs(kv[1])):
            best = None
            for off in range(0, 0xC0 - 8, 2):
                d = struct.unpack("<d", blob[off:off + 8])[0]
                if d == d and best is None or (d == d and abs(d - val) < abs(best[1] - val)):
                    best = (off, d)
            for off in range(0, 0xC0 - 2, 2):
                s = struct.unpack("<h", blob[off:off + 2])[0]
                if abs(s - val) < abs(best[1] - val):
                    best = (off, float(s))
            ok = "OK " if abs(best[1] - val) < max(0.2, abs(val) * 0.002) else "   "
            print("  %-12s %10.2f   %s +0x%02x = %10.2f" % (name, val, ok, best[0], best[1]))
