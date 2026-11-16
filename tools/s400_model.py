"""Reference implementation of the Xiaomi S400 body-composition panel.

Implements the formulas recovered from firmware 2.1.1_0006 and validated against the
device's own code (see S400_ALGORITHM_REFERENCE.md, §3). Pure float maths, no I/O.

Units: h in cm, w in kg, impedance in ohms. Sex: 0 = female, 1 = male.
"""
from __future__ import annotations

import math

# Nine-term regressions, coefficients x 1e6
WATER = (2935892, 149065, -468183, 589094, -63286091, -778045, 23941529, -29784715, 424044966)
BONE = (118543, 26106, -45544, 48749, -2271994, -155662, 2151182, -2248649, 12272558)
SOLIDS = (160696, 28769, -60093, 65412, -3163648, -169504, 2860478, -3043837, 18045896)
SKELETAL_MUSCLE = (2475795, 118673, -457174, 556218, -53616294, -574893,
                   23989719, -28648257, 352065003)
VISCERAL = (-1849883, 424124, 366784, -455322, 39648934, -359012,
            -20035428, 24213934, -265509571)

# body-fat coefficients: h, w, age, z50, constant
FAT_COEFFS = {1: (-0.3315, 0.6216, 0.0183, 0.0085, 22.554),
              0: (-0.3332, 0.7509, 0.0196, 0.0072, 22.7193)}


def round01(x: float) -> float:
    """Round half away from zero to 0.1 — the firmware's rounding."""
    return math.floor(x * 10.0 + 0.5) / 10.0 if x >= 0 else math.ceil(x * 10.0 - 0.5) / 10.0


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def regression(k, h, w, z50, z250):
    return (k[0] * h + k[1] * w + k[2] * z50 + k[3] * z250 + k[4] * math.sqrt(h)
            + k[5] * math.sqrt(w) + k[6] * math.sqrt(z50) + k[7] * math.sqrt(z250) + k[8]) / 1e6


def panel(h, w, age, sex, z50, z250):
    """Return the 14 fields the scale computes, in the firmware's rounding order."""
    c = FAT_COEFFS[1 if sex else 0]
    fat = clamp(100.0 * (c[0] * h + c[1] * w + c[2] * age + c[3] * z50 + c[4]) / w, 3.0, 55.0)

    # the firmware rounds the percentage to 0.1 before turning it into a mass
    fat_mass = round01(round01(fat) / 100.0 * w)
    lbm = w - fat_mass

    bone = regression(BONE, h, w, z50, z250)
    bone = 0.0 if round01(bone) < 0.3 else clamp(bone, 0.0, 5.0)

    solids = round01(regression(SOLIDS, h, w, z50, z250))
    water = round01(round01(regression(WATER, h, w, z50, z250)) + 0.03 * w)
    water_pct = round01(clamp(round01(water / w * 100.0), 20.0, 85.0))
    water_mass = round01(water_pct * w / 100.0)

    protein_pct = (lbm - solids - water_mass) / w * 100.0
    protein_mass = round01(clamp(round01(protein_pct), 5.0, 32.0) * w / 100.0)

    muscle = clamp(lbm - round01(bone), 7.0, 141.5)
    smm = clamp(regression(SKELETAL_MUSCLE, h, w, z50, z250),
                0.45 * round01(muscle), 0.70 * round01(muscle))
    visceral = int(clamp(int(regression(VISCERAL, h, w, z50, z250) + 0.5), 1, 59))

    bmr = int(clamp(21.6 * round01(lbm) + 370.0 + 0.5, 400.0, 3500.0))
    bmi = w / (h / 100.0) ** 2
    ideal = (h - 80.0) * 0.7 if sex else (h - 70.0) * 0.6

    return {
        "fat_percent": round(fat, 1),
        "muscle_kg": round(muscle, 1),
        "water_percent": round(water_pct, 1),
        "bone_kg": round(bone, 1),
        "visceral": visceral,
        "protein_percent": round(clamp(protein_pct, 5.0, 32.0), 1),
        "skeletal_muscle_kg": round(smm, 1),
        "bmi": round(bmi, 1),
        "ideal_weight_kg": round(ideal, 1),
        "bmr_kcal": bmr,
        "fat_mass_kg": round(fat_mass, 1),
        "fat_free_mass_kg": round(lbm, 1),
        "water_mass_kg": round(water_mass, 1),
        "protein_mass_kg": round(protein_mass, 1),
    }


if __name__ == "__main__":
    for args in [(180, 75, 38, 1, 520, 475), (165, 60, 30, 0, 600, 540)]:
        print(args, panel(*args))
