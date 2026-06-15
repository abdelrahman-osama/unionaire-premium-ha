#!/usr/bin/env python3
"""Emit canonical decoded dataset as JSON for downstream analysis."""
import json
from decode import load, iter_commands, parse_envelope, pulses, demodulate
from analyze import bits_to_bytes


def rev8(x):
    return int(f"{x:08b}"[::-1], 2)


if __name__ == "__main__":
    cfg = load()
    out = {"cells": [], "special": {}}
    fan_rank = {"auto": 0, "low": 1, "medium": 2, "high": 3, "turbo": 4}
    for key, code in iter_commands(cfg):
        frames, _ = demodulate(pulses(parse_envelope(code)[3]))
        lsb = bits_to_bytes(frames[0], True)
        f1 = bits_to_bytes(frames[1], True)
        rec = {
            "frame0_lsb": lsb,
            "frame0_hex": " ".join(f"{b:02x}" for b in lsb),
            "frame1_lsb": f1,
        }
        if len(key) == 4:
            mode, fan, swing, t = key
            anomaly = (mode == "cool" and fan == "auto" and t in ("20", "21"))
            out["cells"].append({
                "mode": mode, "fan": fan, "swing": swing, "temp": int(t),
                "frame0_lsb": lsb,
                "fan_rank": fan_rank[fan],
                "mode_code": lsb[1] & 0x0F, "fan_code": lsb[1] >> 4,
                "byte2": lsb[2], "byte6_temp": lsb[6], "byte7": lsb[7],
                "byte7_H": lsb[7] >> 4, "byte7_L": lsb[7] & 0x0F,
                "frame0_hex": rec["frame0_hex"], "anomaly": anomaly,
            })
        else:
            out["special"][key[0]] = rec
    with open("decoded_grid.json", "w") as f:
        json.dump(out, f, indent=1)
    print("wrote decoded_grid.json:", len(out["cells"]), "cells +", list(out["special"]))
    # also print a compact table
    print("\nmode fan temp | b1(mode/fan) byte2 byte6 byte7(H/L)")
    for c in out["cells"]:
        flag = " *ANOMALY*" if c["anomaly"] else ""
        print(f"{c['mode']:5s} {c['fan']:6s} {c['temp']} | "
              f"m{c['mode_code']:x}/f{c['fan_code']:x} b2={c['byte2']:02x} "
              f"t={c['byte6_temp']:02x} b7={c['byte7']:02x}(H{c['byte7_H']:x}/L{c['byte7_L']:x}){flag}")
