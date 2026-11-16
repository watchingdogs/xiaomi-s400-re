"""Re-test whether the S400 SoC contains a body-composition coefficient table,
at more fixed-point scales than the single 1e6 I tried before.

Signal: a genuine coefficient table shows MULTIPLE coefficients of the SAME
vector present in the image. One coefficient matching is coincidence.
"""
import pathlib
import re

out = pathlib.Path("/opt/data/fw")
blob = next(p for p in out.iterdir() if p.name.endswith("_dec_yunmai.scales.ms104.bin")).read_bytes()

VECTORS = {
    "WATER": [2.935892, 0.149065, -0.468183, 0.589094, -63.286091, -0.778045,
              23.941529, -29.784715, 424.044966],
    "BONE": [0.118543, 0.026106, -0.045544, 0.048749, -2.271994, -0.155662,
             2.151182, -2.248649, 12.272558],
    "SOLIDS": [0.160696, 0.028769, -0.060093, 0.065412, -3.163648, -0.169504,
               2.860478, -3.043837, 18.045896],
    "SMM": [2.475795, 0.118673, -0.457174, 0.556218, -53.616294, -0.574893,
            23.989719, -28.648257, 352.065003],
    "VISC": [-1.849883, 0.424124, 0.366784, -0.455322, 39.648934, -0.359012,
             -20.035428, 24.213934, -265.509571],
    "BODYFAT_M": [-0.3315, 0.6216, 0.0183, 0.0085, 22.554],
    "BODYFAT_F": [-0.3332, 0.7509, 0.0196, 0.0072, 22.7193],
}

SCALES = [1e2, 1e3, 1e4, 1e5, 1e6, 1e7, 1e8, 2**8, 2**10, 2**12, 2**14, 2**16, 2**20, 2**24]
WIDTHS = [2, 3, 4]


def find_all(buf, pat, limit=3):
    n = 0
    i = buf.find(pat)
    while i >= 0 and n < limit:
        n += 1
        i = buf.find(pat, i + 1)
    return n


best = []
for name, coeffs in VECTORS.items():
    for scale in SCALES:
        present = 0
        for c in coeffs:
            v = int(round(c * scale))
            for w in WIDTHS:
                try:
                    pat = v.to_bytes(w, "little", signed=True)
                except OverflowError:
                    continue
                if pat.strip(b"\x00") and find_all(blob, pat):
                    present += 1
                    break
        best.append((present, len(coeffs), name, scale))

best.sort(reverse=True)
print("coefficients of the same vector found, per scale (top 15):")
for p, n, name, s in best[:15]:
    print("  %-10s scale=%-10g  %d/%d coefficients present%s" % (
        name, s, p, n, "   <-- suspicious" if p >= 3 else ""))

# --- what the log lines look like in context ---
print("\n=== strings around the bia/panel log lines ===")
for anchor in (0x29a4e, 0x29b66):
    lo, hi = anchor - 0x600, anchor + 0x600
    print("\n--- window 0x%x..0x%x ---" % (lo, hi))
    for m in re.finditer(rb"[ -~]{6,}", blob[lo:hi]):
        t = m.group().decode()
        if ":" in t or "%" in t:
            print("   0x%06x  %s" % (lo + m.start(), t[:100]))
