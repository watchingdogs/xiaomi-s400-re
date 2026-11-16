#!/usr/bin/env python3
"""Analyse Xiaomi S400 stored weigh-in records (MIoT service 9, offline-data).

Records are separated by "_"; each is 33 comma-separated integers.
Field map per community RE (HA thread 662778, post 51) + arithmetic checks here.

Usage:
    python3 s400_analyze.py records.txt
    python3 s400_analyze.py --adverts adverts.txt records.txt

records.txt  : raw record string(s), e.g. 42,1234567,1,1,750,0,1,...,4750_43,...
adverts.txt  : optional, one line per broadcast:  <z50_raw>,<z250_raw>,<weight_raw>,<hr>
               (raw = the integers before the /10, so we compare like with like)
"""
import math
import sys

FIELDS = {
    0: ("index", "record index, wraps at 256"),
    1: ("account", "Xiaomi account id"),
    2: ("user", "profile number recognised by the scale (0 = unknown)"),
    3: ("?", "unidentified"),
    4: ("weight", "x0.1 kg"),
    5: ("?", "likely heart rate (0 in stored records)"),
    6: ("?", "unidentified"),
    7: ("timestamp", "unix, scale clock"),
    8: ("fat%", "x0.1"),
    9: ("muscle_kg", "x0.1"),
    10: ("water%", "x0.1"),
    11: ("bone_kg", "x0.1"),
    12: ("visceral", "level"),
    13: ("protein%", "x0.1"),
    14: ("skeletal_muscle", "x0.1 kg"),
    15: ("bmi", "x0.1"),
    16: ("ideal_weight", "x0.1 kg"),
    17: ("delta_lean", "x0.1 kg = 0.85*ideal - LBM"),
    18: ("delta_weight", "x0.1 kg = ideal - weight"),
    19: ("delta_fat", "x0.1 kg = 0.15*ideal - fat mass"),
    20: ("?", "unknown (10 on sample)"),
    21: ("bmr", "kcal/day"),
    22: ("body_type", "index, see BODY_TYPES"),
    23: ("metabolic_age", "years"),
    24: ("body_score", "score"),
    25: ("muscle%", "x0.1"),
    26: ("bone%", "x0.1"),
    27: ("fat_mass_kg", "x0.1"),
    28: ("fat_free_kg", "x0.1"),
    29: ("water_mass_kg", "x0.1"),
    30: ("protein_kg", "x0.1"),
    31: ("z50", "50 kHz impedance, ohm x0.1"),
    32: ("z250", "250 kHz impedance, ohm x0.1"),
}

BODY_TYPES = {-5: "lean", -4: "underweight", -3: "invisibly-obese", -2: "slim-muscular",
              -1: "slim", 0: "fit", 1: "muscular", 2: "overweight", 3: "athletic", 4: "obese"}


def parse(text):
    recs = []
    for chunk in text.strip().split("_"):
        chunk = chunk.strip().replace("\n", "")
        if not chunk:
            continue
        try:
            f = [int(x) for x in chunk.split(",")]
        except ValueError:
            continue
        if len(f) < 33:
            print("  ! skipped record with %d fields" % len(f))
            continue
        recs.append(f)
    return recs


def show(f, i):
    print("\n--- record %d ---" % i)
    for idx in range(33):
        name, note = FIELDS.get(idx, ("?", ""))
        print("  [%2d] %-16s %8d   %s" % (idx, name, f[idx], note))
    if f[22] in BODY_TYPES:
        print("  body_type decoded: %s" % BODY_TYPES[f[22]])


def identities(f):
    w = f[4] / 10.0
    fat_mass = f[27] / 10.0
    ffm = f[28] / 10.0
    print("\n--- identity checks (weight %.1f kg) ---" % w)
    checks = []
    checks.append(("fat%% x weight == fat mass",
                   f[8] / 1000.0 * w, fat_mass, 0.15))
    checks.append(("weight - fat mass == fat-free mass",
                   w - fat_mass, ffm, 0.15))
    checks.append(("370 + 21.6 x FFM == BMR",
                   370 + 21.6 * ffm, float(f[21]), 1.5))
    h_cm = None
    if f[15]:
        h_cm = math.sqrt(w / (f[15] / 10.0)) * 100.0
        print("  implied height from BMI: %.1f cm" % h_cm)
    if f[16] and h_cm:
        for sex, fn in (("male", lambda h: (h - 80) * 0.7), ("female", lambda h: (h - 70) * 0.6)):
            checks.append(("ideal weight if %s" % sex, fn(h_cm), f[16] / 10.0, 1.0))
    checks.append(("water + protein + bone == fat-free mass",
                   (f[29] + f[30] + f[11]) / 10.0, ffm, 0.6))
    for label, got, want, tol in checks:
        ok = abs(got - want) <= tol if tol < 900 else True
        print("  %-46s %10.2f vs %10.2f  %s" % (label, got, want, "OK" if ok else "MISMATCH"))


def smoothing(recs):
    print("\n--- impedance series (stored) ---")
    for i, f in enumerate(recs):
        print("  #%d user=%d t=%d w=%.1f z50=%.1f z250=%.1f"
              % (i, f[2], f[7], f[4] / 10.0, f[31] / 10.0, f[32] / 10.0))
    if len(recs) < 3:
        print("  (need >=3 records from the same profile to fit an EMA)")
        return
    print("\n  reciprocal-lag autocorrelation gives the smoothing factor if it is an EMA:")
    for field, name in ((31, "z50"), (32, "z250")):
        xs = [f[field] for f in recs if f[2] == recs[-1][2]]
        if len(xs) < 4:
            continue
        d = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
        num = sum(d[i] * d[i + 1] for i in range(len(d) - 1))
        den = sum(x * x for x in d[:-1]) or 1
        rho = num / den
        alpha = 1 + rho if -1 < rho < 0 else None
        print("    %s: lag-1 corr of deltas = %+.3f -> alpha ~ %s"
              % (name, rho, ("%.2f" % alpha) if alpha else "not an EMA"))


def compare_adverts(text, recs):
    print("\n--- advert vs stored (same weigh-in: advert should be the fresher value) ---")
    adv = []
    for line in text.strip().splitlines():
        parts = [p.strip() for p in line.replace(";", ",").split(",")]
        if len(parts) >= 3:
            try:
                adv.append([int(float(p)) for p in parts[:4]])
            except ValueError:
                pass
    for i, (a, f) in enumerate(zip(adv, recs)):
        print("  #%d advert z50=%d z250=%d w=%d | stored z50=%d z250=%d w=%d | dz50=%+d dz250=%+d"
              % (i, a[0], a[1], a[2], f[31], f[32], f[4], f[31] - a[0], f[32] - a[1]))


if __name__ == "__main__":
    args = sys.argv[1:]
    adv_text = None
    if args and args[0] == "--adverts":
        adv_text = open(args[1]).read()
        args = args[2:]
    if not args:
        print(__doc__)
        sys.exit(1)
    recs = parse(open(args[0]).read())
    print("parsed %d record(s)" % len(recs))
    for i, f in enumerate(recs[:3]):
        show(f, i)
        identities(f)
    smoothing(recs)
    if adv_text:
        compare_adverts(adv_text, recs)
