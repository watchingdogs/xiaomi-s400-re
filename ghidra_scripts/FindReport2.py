# Refs + disassembly + decompile diagnostics for the S400 report/BIA functions.
# Image base 0x0080E000.
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor

BASE = 0x0080E000
TARGETS = {
    0x29aac: "bia_calc_t 2",
    0x29c54: "report CSV fmt (32)",
    0x29dc0: "record CSV fmt (33)",
    0x29a4e: "bia_calc_t 1",
    0x29b66: "panel fmt",
}

fm = currentProgram.getFunctionManager()
refmgr = currentProgram.getReferenceManager()
listing = currentProgram.getListing()
decomp = DecompInterface()
decomp.openProgram(currentProgram)
monitor = ConsoleTaskMonitor()

for off, name in TARGETS.items():
    addr = toAddr(BASE + off)
    refs = list(refmgr.getReferencesTo(addr))
    print("\n### %s @0x%x refs=%d" % (name, BASE + off, len(refs)))
    for r in refs[:6]:
        frm = r.getFromAddress()
        func = fm.getFunctionContaining(frm)
        print("  ref from 0x%s type=%s func=%s entry=0x%s" % (
            frm, r.getReferenceType(), func.getName() if func else "?",
            func.getEntryPoint() if func else "-"))
        if func is None:
            continue
        ep = func.getEntryPoint()
        print("  --- disassembly around ref ---")
        cur = frm
        start = cur.subtract(16)
        for i in range(14):
            ins = listing.getInstructionAt(start)
            if ins is not None:
                print("    0x%s  %s" % (ins.getAddress(), ins.toString()))
            start = start.add(2 if ins is None else ins.getLength())
        res = decomp.decompileFunction(func, 120, monitor)
        ok = res is not None and res.decompileCompleted()
        print("  --- decompile completed=%s err=%s ---" % (
            ok, (res.getErrorMessage() if res else "no result")))
        if ok:
            print(res.getDecompiledFunction().getC()[:9000])
        else:
            body = func.getBody()
            print("  function body: %s (numAddresses=%d)" % (body, body.getNumAddresses()))
