# Locate the function that logs/applies the panel (bt, ma, score) using the correct
# string addresses (with the "[I] : " prefix).
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
import os

BASE = 0x0080E000
OUT = "/tmp/decomp3"
if not os.path.isdir(OUT):
    os.makedirs(OUT)

TARGETS = {
    0x29B60: "panel log fmt (bmr bt ma sbc slp bmp bfm ffm bwm pm)",
    0x29BAC: "user record log (miid duid usrtype weight heart status time bfp slm bwp)",
    0x29C0C: "metrics log (bmc vfr pp smm bmi sbw mc wc fc whr)",
    0x29C54: "CSV fmt 32",
    0x29DC0: "CSV fmt 33",
}

fm = currentProgram.getFunctionManager()
refmgr = currentProgram.getReferenceManager()
decomp = DecompInterface()
decomp.openProgram(currentProgram)
monitor = ConsoleTaskMonitor()

found = {}
for off, name in TARGETS.items():
    addr = toAddr(BASE + off)
    refs = list(refmgr.getReferencesTo(addr))
    print("\n### %s @0x%x refs=%d" % (name, BASE + off, len(refs)))
    for r in refs[:6]:
        fr = r.getFromAddress()
        func = fm.getFunctionContaining(fr)
        print("   from 0x%s (%s) func=%s" % (fr, r.getReferenceType(),
                                             func.getName() if func else "NONE"))
        if func:
            found[func.getEntryPoint().getOffset()] = func

print("\n### decompiling %d functions" % len(found))
for ep in sorted(found):
    f = found[ep]
    res = decomp.decompileFunction(f, 240, monitor)
    ok = res is not None and res.decompileCompleted()
    body = res.getDecompiledFunction().getC() if ok else "// failed"
    with open(os.path.join(OUT, "FUN_%08x.c" % ep), "w") as fh:
        fh.write(body)
    print("  FUN_%08x ok=%s len=%d entry_body=%s" % (ep, ok, len(body), f.getBody()))
