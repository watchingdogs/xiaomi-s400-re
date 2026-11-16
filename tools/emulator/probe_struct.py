"""Probe the bia_calc_t struct layout field by field (byte granularity)."""
import pathlib
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                               UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC)

BASE = 0x0080E000
img = next(p for p in pathlib.Path("/opt/data/fw").iterdir()
           if p.name.endswith("_dec_yunmai.scales.ms104.bin")).read_bytes()
SIZE = (len(img) + 0xFFF) & ~0xFFF
FUNC = 0x0083101C
STACK, IN, OUT, SENT = 0x20000000, 0x20001000, 0x20002000, 0x20003000
STUB = b"\x00\x20\x70\x47"
STUBS = [0x00832240, 0x00813afc, 0x0005a060, 0x0005a070]
MAPS = [(0x0, 0x400000), (BASE, SIZE), (STACK, 0x10000),
        (0x40000000, 0x100000), (0xC0000000, 0x100000)]


def run(buf, count=8000000):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    for a, s in MAPS:
        uc.mem_map(a, s)
    uc.mem_write(BASE, img)
    for s in STUBS:
        uc.mem_write(s, STUB)
    uc.mem_write(OUT, b"\x00" * 0x200)
    uc.mem_write(IN, bytes(buf))
    uc.reg_write(UC_ARM_REG_SP, STACK + 0xF000)
    uc.reg_write(UC_ARM_REG_R0, OUT)
    uc.reg_write(UC_ARM_REG_R1, IN)
    uc.reg_write(UC_ARM_REG_R2, 0)
    uc.reg_write(UC_ARM_REG_LR, SENT | 1)

    def hook(u, addr, size, _):
        if addr == SENT:
            u.emu_stop()

    uc.hook_add(UC_HOOK_CODE, hook, begin=SENT, end=SENT + 2)
    try:
        uc.emu_start(FUNC | 1, SENT | 1, count=count)
    except Exception as e:
        return None, "%s pc=0x%08x" % (str(e)[:40], uc.reg_read(UC_ARM_REG_PC))
    return uc.mem_read(OUT, 0xC0), None


def dbls(blob):
    return {o: struct.unpack("<d", blob[o:o + 8])[0] for o in range(0, 0xB8, 8)}


base = bytearray(16)
struct.pack_into("<H", base, 0, 1800)   # height 180.0 cm
struct.pack_into("<H", base, 2, 750)    # weight 75.0 kg
base[4] = 1                             # sex male
base[5] = 38                            # age
base[6] = 4                             # electrodes
struct.pack_into("<H", base, 8, 5200)   # imp0
struct.pack_into("<H", base, 10, 4750)  # imp1

ref, err = run(base)
if ref is None:
    raise SystemExit("baseline failed: " + err)
refd = dbls(ref)
print("baseline: " + " ".join("+0x%02x=%.2f" % (o, v) for o, v in sorted(refd.items())))

print("\n=== byte perturbations (+10) ===")
for b in range(0, 14):
    buf = bytearray(base)
    buf[b] = (buf[b] + 10) & 0xFF
    blob, err = run(buf)
    if blob is None:
        print("  byte %2d: %s" % (b, err))
        continue
    d = dbls(blob)
    moved = [(o, refd[o], d[o]) for o in sorted(refd) if abs(d[o] - refd[o]) > 1e-6 * (abs(refd[o]) + 1)]
    sample = "; ".join("+0x%02x %.2f->%.2f" % m for m in moved[:3])
    print("  byte %2d: %2d moved   %s" % (b, len(moved), sample))
