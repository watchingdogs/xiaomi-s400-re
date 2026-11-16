"""Is bia_calc's machine code identical (just relocated) across S400 variants?"""
import pathlib

FW = pathlib.Path("/opt/data/fw")
IM = {
    "ms103": FW / "ec9e164a1f2cfabb8d94d10742db4596_dec_yunmai.scales.ms103.bin",
    "ms107": FW / "ebbfba21a04a09759eca97db44c7ce76_dec_yunmai.scales.ms107.bin",
    "ms115": FW / "e3cc8ad3b7d8f73e802fd52db24aa558_dec_xiaomi.scales.ms115.bin",
}
base = (FW / "ac2deeb70c29d94578aecaec3a7e53a0_dec_yunmai.scales.ms104.bin").read_bytes()
BIA = 0x83101C - 0x80E000          # file offset of bia_calc in ms104
AGE = 0x83108E - 0x80E000          # body-age routine


def probe(offset, n=192):
    pat = base[offset:offset + n]
    print("\nslice at file 0x%05x (%d B)" % (offset, n))
    for name, p in IM.items():
        blob = p.read_bytes()
        hits = [i for i in range(len(blob)) if blob.startswith(pat, i)]
        print("   %-6s %s" % (name, ["0x%05x" % h for h in hits[:4]] or "not found"))


for off in (BIA, AGE, 0x81F7E2 - 0x80E000, 0x81FEEC - 0x80E000, 0x83101C - 0x80E000 + 0x2000):
    probe(off)

print("\nsimilarity of whole images (same bytes at same offset, 1 KB blocks)")
for name, p in IM.items():
    blob = p.read_bytes()
    n = min(len(blob), len(base)) // 1024
    same = sum(1 for i in range(n) if blob[i * 1024:(i + 1) * 1024] == base[i * 1024:(i + 1) * 1024])
    print("   %-6s %d/%d blocks identical" % (name, same, n))
