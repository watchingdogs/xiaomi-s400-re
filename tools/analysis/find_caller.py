import pathlib

from capstone import *
from capstone.arm import ARM_OP_IMM

BASE = 0x0080E000
img = next(p for p in pathlib.Path("/opt/data/fw").iterdir()
           if p.name.endswith("_dec_yunmai.scales.ms104.bin")).read_bytes()
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
md.detail = True

TARGET = 0x0083108E
hits = []
for off in range(0, len(img) - 8, 2):
    for ins in md.disasm(img[off:off + 4], BASE + off):
        if ins.mnemonic in ("bl", "blx") and ins.operands:
            op = ins.operands[0]
            if op.type == ARM_OP_IMM and (op.imm & ~1) == TARGET:
                hits.append(ins.address)
            break

print("call sites into 0x%08x: %d" % (TARGET, len(hits)))
for h in hits:
    print("   0x%08x  (file 0x%05x)" % (h, h - BASE))
    start = h - 0x40
    for ins in md.disasm(img[start - BASE:start - BASE + 0x48], start):
        mark = "  <<<" if ins.address == h else ""
        print("       0x%08x  %-7s %s%s" % (ins.address, ins.mnemonic, ins.op_str, mark))
