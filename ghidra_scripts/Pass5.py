# Decompile the caller of the panel formatter (0x81f95a) and its callees.
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
import os

OUT = "/tmp/decomp3"
if not os.path.isdir(OUT):
    os.makedirs(OUT)

CALLSITE = 0x0081F95A
fm = currentProgram.getFunctionManager()
decomp = DecompInterface()
decomp.openProgram(currentProgram)
monitor = ConsoleTaskMonitor()

f = fm.getFunctionContaining(toAddr(CALLSITE))
if f is None:
    print("no function contains the call site")
else:
    print("owner: %s entry=0x%x body=%s" % (f.getName(), f.getEntryPoint().getOffset(), f.getBody()))
    wanted = {f.getEntryPoint().getOffset(): f}
    for c in f.getCalledFunctions(monitor):
        wanted.setdefault(c.getEntryPoint().getOffset(), c)
    print("callees: %s" % [hex(k) for k in sorted(wanted)])
    for ep in sorted(wanted):
        fn = wanted[ep]
        res = decomp.decompileFunction(fn, 240, monitor)
        ok = res is not None and res.decompileCompleted()
        body = res.getDecompiledFunction().getC() if ok else "// failed"
        with open(os.path.join(OUT, "FUN_%08x.c" % ep), "w") as fh:
            fh.write(body)
        print("  FUN_%08x ok=%s len=%d" % (ep, ok, len(body)))
