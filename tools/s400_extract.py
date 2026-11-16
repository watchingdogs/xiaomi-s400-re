#!/usr/bin/env python3
"""Extract Xiaomi S400-family BLE images.

Layout discovered on ms104 (2.1.1_0006):
  0x00000  48B outer container header, magic 0x41960005
  0x00030  plaintext stage-1 (DFU bootloader, Thumb-2, shared by all S400 builds)
  0x0A000  48B inner container header, magic 0x21810005
  0x0A030.. a series of raw LZMA1 ("alone") streams, 16 KiB uncompressed each

The app payload is NOT encrypted - it is LZMA-compressed. Each stream carries a
13-byte LZMA-alone header (props 0x5D, dict size, uncompressed size).
"""
import lzma
import pathlib
import sys

DICTS = (0x1000, 0x2000, 0x4000, 0x8000, 0x10000, 0x20000, 0x40000, 0x100000)


def find_streams(data, start):
    """Scan for valid LZMA-alone streams from `start`; return [(offset, out_bytes)]."""
    found = []
    i = start
    while i < len(data) - 13:
        if data[i] == 0x5D:
            dictsz = int.from_bytes(data[i + 1:i + 5], "little")
            size = int.from_bytes(data[i + 5:i + 13], "little")
            if dictsz in DICTS and 0 < size <= 0x40000:
                try:
                    dec = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
                    out = dec.decompress(data[i:])
                except Exception:
                    out = b""
                if len(out) > 100:
                    found.append((i, out))
                    consumed = len(data) - i - len(dec.unused_data)
                    i += max(consumed, 1)
                    continue
        i += 1
    return found


def extract(path, app_start=0xA000):
    data = path.read_bytes()
    streams = find_streams(data, app_start)
    blob = b"".join(o for _, o in streams)
    return data, streams, blob


if __name__ == "__main__":
    targets = sys.argv[1:] or [str(p) for p in sorted(pathlib.Path("/opt/data/fw").glob("*_upd_*.bin"))]
    for t in targets:
        p = pathlib.Path(t)
        data, streams, blob = extract(p)
        out = p.with_name(p.name.replace("_upd_", "_dec_"))
        out.write_bytes(blob)
        print(f"{p.name}\n  container {len(data):,}B -> {len(streams)} LZMA streams -> {len(blob):,}B  => {out.name}")
