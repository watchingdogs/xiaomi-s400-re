#!/usr/bin/env python3
"""Query Xiaomi's /home/latest_version for firmware URLs, using a completed login."""
import json
import pathlib
import sys
import time

import requests
from micloud import miutils

LOGIN = json.load(open("/tmp/mi_login.json"))
SSECURITY = LOGIN["ssecurity"]
BASE = "https://api.io.mi.com/app"

MODELS = sys.argv[1:] or [
    "yunmai.scales.ms104",   # S400 global (DE/SG/US/RU) - MJTZC01YM
    "yunmai.scales.ms103",   # S400 China
    "xiaomi.scales.ms115",   # S400 overseas JP/KR
    "yunmai.scales.ms107",
    "xiaomi.scales.ms110",   # S400 Pro (MJTZC03YM)
]


def session():
    s = requests.Session()
    ck = dict(LOGIN["cookies"])
    ck.update({
        "userId": str(LOGIN["userId"]),
        "cUserId": LOGIN["cUserId"],
        "serviceToken": ck.get("serviceToken", ""),
        "yetAnotherServiceToken": ck.get("serviceToken", ""),
        "locale": "en_US",
        "timezone": "Europe/Copenhagen",
        "is_daylight": "0",
        "dst_offset": "0",
        "channel": "MI_APP_STORE",
    })
    for k, v in ck.items():
        s.cookies.set(k, v, domain=".mi.com")
    s.headers.update({
        "Accept-Encoding": "identity",
        "x-xiaomi-protocal-flag-cli": "PROTOCAL-HTTP2",
        "content-type": "application/x-www-form-urlencoded",
        "MIOT-ENCRYPT-ALGORITHM": "ENCRYPT-RC4",
        "User-Agent": "Android-7.1.1-1.0.0-ONEPLUS A3010-136-1A2B3C4D5E6F7 APP/xiaomi.smarthome APPV/62830",
    })
    return s


def call(s, path, params):
    url = BASE + path
    nonce = miutils.gen_nonce()
    signed = miutils.signed_nonce(SSECURITY, nonce)
    body = miutils.generate_enc_params(url, "POST", signed, nonce, params, SSECURITY)
    t0 = time.time()
    r = s.post(url, data=body, timeout=60)
    txt = miutils.decrypt_rc4(miutils.signed_nonce(SSECURITY, body["_nonce"]), r.text)
    print(f"[{path}] http={r.status_code} {time.time()-t0:.1f}s bytes={len(txt)}")
    return txt


if __name__ == "__main__":
    s = session()
    out = {}
    for m in MODELS:
        print(f"\n=== {m} ===")
        try:
            txt = call(s, "/home/latest_version", {"data": json.dumps({"model": m})})
            print(txt[:1500])
            out[m] = json.loads(txt)
        except Exception as e:
            print("ERR", type(e).__name__, e)
    pathlib.Path("/opt/data/fw").mkdir(exist_ok=True)
    pathlib.Path("/opt/data/fw/latest_version.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
