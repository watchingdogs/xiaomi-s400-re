"""Execute FUN_0083101c (S400 BIA) under emulation with real inputs.

Stubs (patched in-place with `movs r0,#0; bx lr`): the input validator and the
logging helpers, so we exercise only the maths.

Input struct (short[]): [0] height [1] weight [2] sex [3] age
                        [4] electrodes_number [5] imp0 [6] imp1
"""
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
STUB_BYTES = b"\x00\x20\x70\x47"          # movs r0,#0 ; bx lr
STUBS = [0x00832240, 0x00813afc, 0x0005a060, 0x0005a070]
MAPS = [(0x00000000, 0x00400000), (BASE, SIZE),
        (STACK, 0x00010000), (0x40000000, 0x00100000), (0xC0000000, 0x00100000)]


def call(h, w, sex, age, elec, imp0, imp1, count=8000000):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    for addr, size in MAPS:
        uc.mem_map(addr, size)
    uc.mem_write(BASE, img)
    for s in STUBS:
        uc.mem_write(s, STUB_BYTES)
    uc.mem_write(OUT, b"\x00" * 0x200)
    uc.reg_write(UC_ARM_REG_SP, STACK + 0xF000)
    uc.mem_write(IN, struct.pack("<7h", h, w, sex, age, elec, imp0, imp1))
    uc.reg_write(UC_ARM_REG_R0, OUT)
    uc.reg_write(UC_ARM_REG_R1, IN)
    uc.reg_write(UC_ARM_REG_R2, 0)
    uc.reg_write(UC_ARM_REG_LR, SENT | 1)

    def hook(uc_, addr, size_, _):
        if addr == SENT:
            uc_.emu_stop()

    uc.hook_add(UC_HOOK_CODE, hook, begin=SENT, end=SENT + 2)
    try:
        uc.emu_start(FUNC | 1, SENT | 1, count=count)
    except Exception as e:
        return None, "EXC %s pc=0x%08x" % (str(e)[:40], uc.reg_read(UC_ARM_REG_PC))
    return uc.mem_read(OUT, 0xC0), None


def show(blob):
    print("  shorts:", [struct.unpack("<h", blob[i:i + 2])[0] for i in range(0, 0x80, 2)])
    print("  doubles:")
    for off in range(0, 0xC0 - 8, 4):
        d = struct.unpack("<d", blob[off:off + 8])[0]
        if d == d and 1e-3 < abs(d) < 1e8:
            print("    +0x%02x  %16.6f" % (off, d))


if __name__ == "__main__":
    for name, args in [
        ("male 1800/750/38", (1800, 750, 1, 38, 4, 5200, 4750)),
        ("male 180/750/38", (180, 750, 1, 38, 4, 5200, 4750)),
        ("female 1650/600/30", (1650, 600, 2, 30, 4, 6000, 5400)),
    ]:
        blob, err = call(*args)
        print("\n=== %s ===" % name)
        print("  ", err) if blob is None else show(blob)
