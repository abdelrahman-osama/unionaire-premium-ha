#!/usr/bin/env python3
"""Locate fields in frame0 by diffing across the command matrix."""
import os
from collections import defaultdict
from decode import load, iter_commands, parse_envelope, pulses, demodulate


def bits_to_bytes(bits, lsb_first):
    out = []
    for i in range(0, len(bits), 8):
        chunk = bits[i:i + 8]
        if lsb_first:
            chunk = chunk[::-1]
        out.append(int(chunk, 2))
    return out


def decode_all(cfg):
    data = {}
    frame1_set = set()
    for key, code in iter_commands(cfg):
        *_, payload, raw = parse_envelope(code)
        frames, _ = demodulate(pulses(payload))
        data[key] = frames
        if len(frames) >= 2:
            frame1_set.add(frames[1])
    return data, frame1_set


if __name__ == "__main__":
    cfg = load()
    data, frame1_set = decode_all(cfg)
    print("distinct frame1 values:", len(frame1_set))
    for f in frame1_set:
        print("  frame1:", f, "->LSB bytes:", [hex(b) for b in bits_to_bytes(f, True)],
              "->MSB bytes:", [hex(b) for b in bits_to_bytes(f, False)])

    # focus: cool/auto across temps
    print("\n=== frame0 bytes, LSB-first ===")
    for lsb in (True, False):
        print(f"\n--- {'LSB' if lsb else 'MSB'}-first ---")
        print("vary TEMP (cool, auto):")
        for t in [str(x) for x in range(20, 29)]:
            b = bits_to_bytes(data[("cool", "auto", "down", t)][0], lsb)
            print(f"  {t}: " + " ".join(f"{x:02x}" for x in b))
        print("vary FAN (cool, 24):")
        for fan in cfg["fanModes"]:
            b = bits_to_bytes(data[("cool", fan, "down", "24")][0], lsb)
            print(f"  {fan:7s}: " + " ".join(f"{x:02x}" for x in b))
        print("vary MODE (auto, 24):")
        for mode in ("cool", "heat"):
            b = bits_to_bytes(data[(mode, "auto", "down", "24")][0], lsb)
            print(f"  {mode:5s}: " + " ".join(f"{x:02x}" for x in b))
        print("off / on_once:")
        for k in (("off",), ("on_once",)):
            b = bits_to_bytes(data[k][0], lsb)
            print(f"  {k[0]:8s}: " + " ".join(f"{x:02x}" for x in b))
