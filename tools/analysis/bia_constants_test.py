"""Is the S400's BIA coefficient data in the image at all - as doubles, or as
integers at a scale I haven't tried?

Guillaume99 verified on real records that BMR = 370 + 21.6 * fat_free_mass
exactly, which is the same BMR equation bodymiscale's Xiaomi mode uses. So the
algorithm family IS shared; the question is whether the *regression* constants
are present and I simply searched the wrong representation.
"""
import pathlib
import struct

out = pathlib.Path("/opt/data/fw")
blob = next(p for p in out.iterdir() if p.name.endswith("_dec_yunmai.scales.ms104.bin")).read_bytes()

XIAOMI = {
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
}

print("=== exact float64 hits for Xiaomi regression coefficients ===")
n64 = 0
for name, vec in XIAOMI.items():
    for c in vec:
        i = blob.find(struct.pack("<d", c))
        if i >= 0:
            n64 += 1
            print("   %s %f @0x%x" % (name, c, i))
print("   total:", n64)

print("\n=== integer ordered chains, classic Mi/Zeven model constants ===")
# LBM = (h*9.058/100)*(h/100) + w*0.32 + 12.226 - z*0.0068 - age*0.0542
CLASSIC = {
    "LBM": [9.058, 0.32, 12.226, 0.0068, 0.0542],
    "BMR_m": [14.916, 0.726, 8.976, 877.8],
    "BMR_f": [10.2036, 0.39336, 6.204, 864.6],
    "MA_m": [0.7471, 0.9161, 0.4184, 0.0517, 54.2267],
}


def chain(vec, scale, width):
    try:
        first = int(round(abs(vec[0]) * scale)).to_bytes(width, "little", signed=True)
    except OverflowError:
        return 0
    best = 0
    start = blob.find(first)
    tries = 0
    while start >= 0 and tries < 40:
        tries += 1
        pos, run = start, 1
        for c in vec[1:]:
            try:
                pat = int(round(abs(c) * scale)).to_bytes(width, "little", signed=True)
            except OverflowError:
                break
            nxt = blob.find(pat, pos, pos + 0x100)
            if nxt < 0:
                break
            run += 1
            pos = nxt
        best = max(best, run)
        start = blob.find(first, start + 1)
    return best


hits = []
for name, vec in CLASSIC.items():
    for scale in (1e2, 1e3, 1e4, 1e5, 1e6, 2**10, 2**12, 2**14, 2**16):
        for w in (2, 3, 4):
            b = chain(vec, scale, w)
            if b >= 3:
                hits.append((b, name, scale, w))
hits.sort(reverse=True)
print("   chains >=3:", hits if hits else "NONE")
