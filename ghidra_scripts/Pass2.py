# Next pass: report/record builders + whoever uses the body-age constants.
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
import os

BASE = 0x0080E000
OUT = "/tmp/decomp2"
if not os.path.isdir(OUT):
    os.makedirs(OUT)

fm = currentProgram.getFunctionManager()
refmgr = currentProgram.getReferenceManager()
decomp = DecompInterface()
decomp.openProgram(currentProgram)
monitor = ConsoleTaskMonitor()

# functions known to build the CSV strings
ROOTS = [0x0081f7e2, 0x0081feec, 0x0081cf9a]

# double constants of interest: body-age coeffs (adult+youth), 0.944, 2.5, 21.6, 370
CONSTS = [0x00831908, 0x00831920, 0x00831928, 0x00831930, 0x00831938,
          0x00831940, 0x00831948, 0x00831950, 0x008318e8, 0x008318c8,
          0x00831d5c, 0x00831d64, 0x00831d6c, 0x00831d74, 0x00831d7c,
          0x00831d84, 0x00831d98, 0x00831da0, 0x00831da8, 0x00831db0,
          0x00831dbc, 0x00831dc8]

print("\n### who reads the body-age / reference constants")
for c in CONSTS:
    refs = list(refmgr.getReferencesTo(toAddr(c)))
    for r in refs[:4]:
        f = fm.getFunctionContaining(r.getFromAddress())
        print("  0x%08x read from 0x%s in %s" % (
            c, r.getFromAddress(), f.getName() if f else "?"))

# collect functions to decompile: roots + constant users + callees (depth 1)
wanted = {}
for a in ROOTS:
    f = fm.getFunctionAt(toAddr(a)) or fm.getFunctionContaining(toAddr(a))
    if f:
        wanted[f.getEntryPoint().getOffset()] = f

for c in CONSTS:
    for r in refmgr.getReferencesTo(toAddr(c)):
        f = fm.getFunctionContaining(r.getFromAddress())
        if f:
            wanted[f.getEntryPoint().getOffset()] = f

for ep in list(wanted):
    for callee in wanted[ep].getCalledFunctions(monitor):
        wanted.setdefault(callee.getEntryPoint().getOffset(), callee)

print("\n### decompiling %d functions" % len(wanted))
for ep in sorted(wanted):
    f = wanted[ep]
    res = decomp.decompileFunction(f, 180, monitor)
    ok = res is not None and res.decompileCompleted()
    body = res.getDecompiledFunction().getC() if ok else "// failed"
    name = "FUN_%08x" % ep
    with open(os.path.join(OUT, name + ".c"), "w") as fh:
        fh.write("// %s  %s\n" % (f.getName(), f.getSignature()))
        fh.write(body)
    print("  %s %s len=%d" % (name, "OK" if ok else "FAIL", len(body)))
