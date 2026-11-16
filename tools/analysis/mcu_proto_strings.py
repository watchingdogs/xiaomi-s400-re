import pathlib
import re

out = pathlib.Path("/opt/data/fw")
blob = next(p for p in out.iterdir() if p.name.endswith("_dec_yunmai.scales.ms104.bin")).read_bytes()

s = [x.decode() for x in re.findall(rb"[ -~]{5,}", blob)]

print("=== MCU / UART protocol strings ===")
for t in s:
    low = t.lower()
    if ("mible_mcu" in low or " mcu" in low or "mcu_" in low or "m91" in low
            or "uart" in low or "omijia" in low):
        print("  ", t[:110])

print("\n=== anything that looks like a BIA request/result message ===")
for t in s:
    low = t.lower()
    if any(k in low for k in ("bia", "impedance", "res_", "body_res", "composition")):
        print("  ", t[:110])
