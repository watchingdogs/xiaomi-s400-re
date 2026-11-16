"""Ordered-table detector: a real coefficient table stores the coefficients in
order, close together. Coincidental hits do not chain.
"""
import pathlib

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

SCALES = [1e2, 1e3, 1e4, 1e5, 1e6, 1e7, 2**10, 2**12, 2**14, 2**16]
WIDTHS = [2, 3, 4]
WINDOW = 0x100  # coefficients must sit within 256 bytes of the previous one


def offsets_of(pat, limit=400):
    res, i = [], blob.find(pat)
    while i >= 0 and len(res) < limit:
        res.append(i)
        i = blob.find(pat, i + 1)
    return res


results = []
for name, coeffs in VECTORS.items():
    for scale in SCALES:
        for w in WIDTHS:
            chain_best, chain_info = 0, None
            try:
                first = int(round(coeffs[0] * scale)).to_bytes(w, "little", signed=True)
            except OverflowError:
                continue
            for start_off in offsets_of(first, 50):
                cur, pos = 1, start_off
                for c in coeffs[1:]:
                    v = int(round(c * scale))
                    try:
                        pat = v.to_bytes(w, "little", signed=True)
                    except OverflowError:
                        break
                    nxt = blob.find(pat, pos, pos + WINDOW)
                    if nxt < 0:
                        break
                    cur += 1
                    pos = nxt
                if cur > chain_best:
                    chain_best, chain_info = cur, start_off
            if chain_best >= 3:
                results.append((chain_best, len(coeffs), name, scale, w, chain_info))

results.sort(reverse=True)
print("longest ordered chain found per (vector, scale, width):")
if not results:
    print("  NONE - no vector appears as an ordered table at any tested scale")
for r in results[:15]:
    print("  %-10s chain=%d/%d scale=%-8g width=%d at 0x%x" % (r[2], r[0], r[1], r[3], r[4], r[5]))
