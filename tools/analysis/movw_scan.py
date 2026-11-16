"""Find movw/movt pairs that build addresses inside the image.

If the compiler materialises string/function addresses with MOVW/MOVT (typical for
a base far from PC), those pairs give us exact xrefs without any base register
guesswork. Cheap: pure capstone, no Ghidra.
"""
import pathlib
import collections

from capstone import *
from capstone.arm import ARM_OP_IMM

out = pathlib.Path("/opt/data/fw")
blob = next(p for p in out.iterdir() if p.name.endswith("_dec_yunmai.scales.ms104.bin")).read_bytes()

BASE = 0x0080E000
END = BASE + len(blob)
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_MCLASS)
md.detail = True

pairs = []
for off in range(0, len(blob) - 8, 2):
    ins = list(md.disasm(blob[off:off + 8], off))
    if len(ins) < 2:
        continue
    a, b = ins[0], ins[1]
    if a.mnemonic != "movw" or b.mnemonic != "movt":
        continue
    if len(a.operands) < 2 or len(b.operands) < 2:
        continue
    if a.operands[0].reg != b.operands[0].reg:
        continue
    lo, hi = a.operands[1].imm, b.operands[1].imm
    addr = ((hi & 0xFFFF) << 16) | (lo & 0xFFFF)
    if BASE <= addr < END:
        pairs.append((off, addr, addr - BASE))

print("movw/movt pairs pointing into the image: %d" % len(pairs))
if pairs:
    print("  first 15: (code off, address, target off)")
    for off, addr, tgt in pairs[:15]:
        snippet = blob[tgt:tgt + 40]
        txt = "".join(chr(c) if 32 <= c < 127 else "." for c in snippet)
        print("   code 0x%05x -> 0x%08x -> file 0x%05x  %s" % (off, addr, tgt, txt[:38]))

    tgts = collections.Counter(t for _, _, t in pairs)
    print("\n  distinct targets: %d, most referenced:" % len(tgts))
    for t, n in tgts.most_common(8):
        txt = blob[t:t + 32]
        print("   0x%05x x%d  %s" % (t, n, "".join(chr(c) if 32 <= c < 127 else "." for c in txt)))
