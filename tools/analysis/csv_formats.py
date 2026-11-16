import pathlib
import re

out = pathlib.Path("/opt/data/fw")
blob = next(p for p in out.iterdir() if p.name.endswith("_dec_yunmai.scales.ms104.bin")).read_bytes()


def s_at(off):
    end = blob.find(b"\x00", off)
    return blob[off:end].decode("latin-1")


for off, label in ((0x29c54, "record/report format A"), (0x29dc0, "record/report format B")):
    s = s_at(off)
    fields = len(re.findall(r"%[0-9.*]*[dulxs]", s))
    print("=== %s @0x%x ===" % (label, off))
    print("  len=%d chars, specifiers=%d" % (len(s), fields))
    print("  " + s[:400])
    print()

# every long csv-ish format string in the image
print("=== all strings with >= 10 comma-separated specifiers ===")
for m in re.finditer(rb"[ -~]{20,}", blob):
    t = m.group().decode("latin-1")
    if t.count(",") >= 9 and t.count("%") >= 8:
        print("  0x%06x  spec=%2d  %s" % (m.start(), len(re.findall(r"%[0-9.*]*[dulxs]", t)), t[:150]))
