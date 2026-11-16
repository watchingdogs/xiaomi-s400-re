# Dump xrefs + decompiled C around the S400 report / BIA functions.
# Image loads at 0x0080E000, so string addresses = BASE + file offset.
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor

BASE = 0x0080E000

TARGETS = {
    0x29a4e: "bia_calc_t 1",
    0x29aac: "bia_calc_t 2",
    0x29b66: "bmr/bt/ma panel",
    0x29c54: "report CSV fmt (32)",
    0x29dc0: "record CSV fmt (33)",
    0x11a1e: "[report][body composition]len",
    0xf1ee: "send body composition to BLE peer",
    0xdffe: "receive impedance",
}

fm = currentProgram.getFunctionManager()
refmgr = currentProgram.getReferenceManager()
decomp = DecompInterface()
decomp.openProgram(currentProgram)
monitor = ConsoleTaskMonitor()

seen = {}
for off, name in TARGETS.items():
    if name == "unused":
        continue
    addr = toAddr(BASE + off)
    refs = list(refmgr.getReferencesTo(addr))
    print("\n### %s  file 0x%x  addr 0x%x  refs=%d" % (name, off, BASE + off, len(refs)))
    for r in refs[:12]:
        frm = r.getFromAddress()
        func = fm.getFunctionContaining(frm)
        print("   from 0x%s (%s) in %s" % (frm, r.getReferenceType(),
                                           func.getName() if func else "?"))
        if func is not None:
            seen.setdefault(func.getEntryPoint().getOffset(), func)

print("\nfunctions found: %d" % len(seen))
for off in sorted(seen):
    func = seen[off]
    print("\n\n/* ===== %s @0x%x ===== */" % (func.getName(), off))
    res = decomp.decompileFunction(func, 120, monitor)
    if res and res.decompileCompleted():
        c = res.getDecompiledFunction().getC()
        print(c[:12000])
    else:
        print("// decompile failed")
