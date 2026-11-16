"""Compare the emulated firmware panel against a real MS104 record.

Usage:
    python compare_real.py "<33 comma-separated record fields>" <height cm> <age> <sex: 0 female, 1 male>

The record comes from tools/s400_records.py. Weight and impedances are read from the record
itself; height, age and sex are the profile the scale had for that user slot.
"""
import contextlib
import io
import struct
import sys

if len(sys.argv) != 5:
    sys.exit(__doc__)

REC = [int(x) for x in sys.argv[1].split(",")]
if len(REC) != 33:
    sys.exit("expected 33 record fields, got %d" % len(REC))

sys.path.insert(0, "/opt/data")
with contextlib.redirect_stdout(io.StringIO()):
    from probe_struct import run

H, AGE, SEX = float(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
W = REC[4] / 10.0
Z50, Z250 = REC[31] / 10.0, REC[32] / 10.0

buf = bytearray(16)
struct.pack_into("<H", buf, 0, int(H * 10))
struct.pack_into("<H", buf, 2, int(W * 10))
buf[4], buf[5], buf[6] = SEX, AGE, 4
struct.pack_into("<H", buf, 8, int(Z50 * 10))
struct.pack_into("<H", buf, 10, int(Z250 * 10))
out, err = run(buf)
if err:
    raise SystemExit("emulation failed: " + err)

dbl = {o: struct.unpack_from("<d", out, o)[0] for o in range(0, 0xB8 + 1, 8)}
sho = {o: struct.unpack_from("<h", out, o)[0] for o in range(0x70, 0x8C, 2)}

print("emulator panel, h=%.1f w=%.1f %s %dy z50=%.1f z250=%.1f"
      % (H, W, "male" if SEX else "female", AGE, Z50, Z250))
for o in sorted(dbl):
    v = dbl[o]
    if abs(v) < 1e6:
        print("   +%#04x  %10.2f" % (o, v))
print("   shorts  " + "  ".join("+%#04x=%d" % (o, v) for o, v in sorted(sho.items())))

# record field -> (name, divisor)
FIELDS = {
    4: ("weight", 10), 8: ("fat %", 10), 9: ("muscle kg", 10), 10: ("water %", 10),
    11: ("bone kg", 10), 12: ("visceral", 1), 13: ("protein %", 10), 14: ("field14", 10),
    15: ("BMI", 10), 16: ("ideal wt", 10), 17: ("field17", 10), 18: ("field18", 10),
    19: ("field19", 10), 20: ("field20", 1), 21: ("BMR", 1), 22: ("field22", 1),
    23: ("body age", 1), 24: ("field24", 1), 25: ("muscle %", 10), 26: ("bone %", 10),
    27: ("fat kg", 10), 28: ("FFM", 10), 29: ("water kg", 10), 30: ("protein kg", 10),
}

print("\n%-4s %-11s %8s   %-12s %8s  %s" % ("idx", "meaning", "record", "panel", "emu", ""))
for idx in sorted(FIELDS):
    name, div = FIELDS[idx]
    target = REC[idx] / float(div)
    bd = min(dbl.items(), key=lambda kv: abs(kv[1] - target))
    bs = min(sho.items(), key=lambda kv: abs(kv[1] - target))
    if abs(bd[1] - target) <= 0.051:
        print("%-4d %-11s %8.2f   double +%#04x %8.2f  MATCH" % (idx, name, target, bd[0], bd[1]))
    elif abs(bs[1] - target) <= 0.5:
        print("%-4d %-11s %8.2f   short  +%#04x %8d  MATCH" % (idx, name, target, bs[0], bs[1]))
    else:
        print("%-4d %-11s %8.2f   %-12s %8s  no match"
              % (idx, name, target, "-", "(closest %.2f)" % bd[1]))
