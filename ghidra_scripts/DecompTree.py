# Decompile FUN_0083101c (the bia_calc_t consumer) and its callees.
import os

from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor

OUT = "/tmp/decomp"
if not os.path.isdir(OUT):
    os.makedirs(OUT)

decomp = DecompInterface()
decomp.openProgram(currentProgram)
monitor = ConsoleTaskMonitor()

ROOTS = [0x0083101c, 0x0081cf9a]

seen = set()
queue = list(ROOTS)
depth = {r: 0 for r in ROOTS}

while queue:
    ep = queue.pop(0)
    func = getFunctionAt(toAddr(ep)) or getFunctionContaining(toAddr(ep))
    if func is None or func.getEntryPoint().getOffset() in seen:
        continue
    seen.add(func.getEntryPoint().getOffset())
    res = decomp.decompileFunction(func, 180, monitor)
    ok = res is not None and res.decompileCompleted()
    name = "FUN_%08x" % func.getEntryPoint().getOffset()
    body = res.getDecompiledFunction().getC() if ok else "// failed"
    with open(os.path.join(OUT, name + ".c"), "w") as f:
        f.write(body)
    print("%s %s  len=%d  depth=%d" % (name, "OK " if ok else "FAIL", len(body), depth.get(ep, 0)))
    if ok and depth.get(ep, 0) < 2:
        for callee in func.getCalledFunctions(monitor):
            cep = callee.getEntryPoint().getOffset()
            if cep not in depth:
                depth[cep] = depth.get(ep, 0) + 1
                queue.append(cep)

print("\n=== files written to %s ===" % OUT)
for n in sorted(os.listdir(OUT)):
    print("  ", n, os.path.getsize(os.path.join(OUT, n)))
