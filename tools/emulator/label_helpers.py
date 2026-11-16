"""Identify the soft-float helpers by emulating them with known arguments.

ARM AAPCS: a double argument occupies an even/odd register pair (r0:r1, r2:r3);
the result comes back in r0:r1.
"""
import pathlib
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                               UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR,
                               UC_ARM_REG_PC)

BASE = 0x0080E000
img = next(p for p in pathlib.Path("/opt/data/fw").iterdir()
           if p.name.endswith("_dec_yunmai.scales.ms104.bin")).read_bytes()
SIZE = (len(img) + 0xFFF) & ~0xFFF
STACK = 0x20000000
STACK_SIZE = 0x8000


def run(func_addr, a, b):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    uc.mem_map(BASE, SIZE)
    uc.mem_write(BASE, img)
    uc.mem_map(STACK, STACK_SIZE)
    uc.mem_write(STACK, b"\x00" * STACK_SIZE)
    uc.reg_write(UC_ARM_REG_SP, STACK + STACK_SIZE - 0x100)
    lo, hi = struct.unpack("<II", struct.pack("<d", a))
    lo2, hi2 = struct.unpack("<II", struct.pack("<d", b))
    uc.reg_write(UC_ARM_REG_R0, lo)
    uc.reg_write(UC_ARM_REG_R1, hi)
    uc.reg_write(UC_ARM_REG_R2, lo2)
    uc.reg_write(UC_ARM_REG_R3, hi2)
    SENTINEL = STACK + 0x40          # inside mapped stack
    uc.reg_write(UC_ARM_REG_LR, SENTINEL | 1)

    stop = []

    def hook(uc_, address, size_, _):
        stop.append(True)
        uc_.emu_stop()

    uc.hook_add(UC_HOOK_CODE, hook, begin=SENTINEL, end=SENTINEL + 2)
    try:
        uc.emu_start(func_addr | 1, SENTINEL | 1, count=200000)
    except Exception as e:
        return "EXC:%s pc=0x%08x" % (str(e)[:60], uc.reg_read(UC_ARM_REG_PC))
    if not stop:
        return "NO-RETURN"
    out = struct.unpack("<d", struct.pack("<II", uc.reg_read(UC_ARM_REG_R0),
                                          uc.reg_read(UC_ARM_REG_R1)))[0]
    return out


CANDIDATES = [0x00834820, 0x0083428c, 0x0083400c, 0x00834908,
              0x00834cf8, 0x00834c46, 0x00834890, 0x0083467c, 0x00832240]
for f in CANDIDATES:
    r = run(f, 2.0, 3.0)
    print("0x%08x  f(2,3) = %s" % (f, r if isinstance(r, str) else "%.10g" % r))
