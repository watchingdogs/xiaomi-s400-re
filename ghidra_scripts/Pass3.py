# Who owns the call site 0x008319a0, and how does it set r4-r7 before calling 0x83108e?
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
import os

OUT = "/tmp/decomp3"
if not os.path.isdir(OUT):
    os.makedirs(OUT)

CALLSITE = 0x008319A0
CALLEE = 0x0083108E

fm = currentProgram.getFunctionManager()
listing = currentProgram.getListing()
decomp = DecompInterface()
decomp.openProgram(currentProgram)
monitor = ConsoleTaskMonitor()

f = fm.getFunctionContaining(toAddr(CALLSITE))
print("\ncall site owner: %s" % (f.getName() if f else "none"))
if f is not None:
    print("  entry=0x%x  body=%s  params=%s" % (
        f.getEntryPoint().getOffset(), f.getBody(), f.getSignature()))
    print("  callers:")
    for r in f.getEntryPoint().getReferences():
        print("     from 0x%s (%s)" % (r.getFromAddress(), r.getReferenceType()))

    res = decomp.decompileFunction(f, 240, monitor)
    ok = res is not None and res.decompileCompleted()
    body = res.getDecompiledFunction().getC() if ok else "// failed"
    with open(os.path.join(OUT, "owner.c"), "w") as fh:
        fh.write(body)
    print("  decompile ok=%s len=%d -> %s/owner.c" % (ok, len(body), OUT))

print("\n=== disassembly 0x8318a0 .. 0x8319c0 ===")
addr = toAddr(0x008318A0)
while addr.getOffset() < 0x008319C0:
    ins = listing.getInstructionAt(addr)
    if ins is None:
        addr = addr.add(2)
        continue
    print("  0x%08x  %-8s %s" % (ins.getAddress().getOffset(), ins.getMnemonicString(),
                                 ins.toString().split(" ", 1)[-1] if " " in ins.toString() else ""))
    addr = addr.add(ins.getLength())
