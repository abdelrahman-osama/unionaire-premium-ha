#!/usr/bin/env python3
"""Verify the full protocol model (byte2 lookup + byte7 formula) reproduces
every captured frame0 exactly, and that generated base64 round-trips."""
from decode import (load, iter_commands, parse_envelope, pulses, demodulate)
from analyze import bits_to_bytes
from encode import encode_from_template

# byte2 lookup (consensus of 3 independent agents, re-verified here)
BYTE2 = {
    ("cool", "auto"):   (0x00, [25]),
    ("cool", "low"):    (0x02, [24]),
    ("cool", "medium"): (0x04, [25]),
    ("cool", "high"):   (0x06, [25]),
    ("cool", "turbo"):  (0x08, [24]),
    ("heat", "auto"):   (0x10, [26]),
    ("heat", "low"):    (0x11, [21, 26]),
    ("heat", "medium"): (0x13, [23]),
    ("heat", "high"):   (0x15, [25]),
    ("heat", "turbo"):  (0x17, [25]),
}
MODE_CODE = {"cool": 0x2, "heat": 0x8}
FAN_CODE = {"auto": 1, "high": 2, "medium": 4, "low": 8, "turbo": 0}


def nib(b):
    return (b >> 4) + (b & 0xF)


def byte2(mode, fan, temp):
    base, thr = BYTE2[(mode, fan)]
    return base + sum(1 for t in thr if temp >= t)


def build_frame0(mode, fan, temp):
    b = [0] * 8
    b[0] = 0x16
    b[1] = (FAN_CODE[fan] << 4) | MODE_CODE[mode]
    b[2] = byte2(mode, fan, temp)
    b[3] = 0x09
    b[4] = 0x10
    b[5] = 0x10
    b[6] = 0x20 + (temp - 20)
    L = 0x4 if fan == "turbo" else 0x0
    H = (sum(nib(x) for x in b[0:7]) + L) % 16
    b[7] = (H << 4) | L
    return b


if __name__ == "__main__":
    cfg = load()
    template = cfg["commands"]["off"]
    ok = bad = 0
    corrupt = []
    for key, code in iter_commands(cfg):
        if len(key) != 4:
            continue
        mode, fan, swing, t = key
        t = int(t)
        captured = bits_to_bytes(demodulate(pulses(parse_envelope(code)[3]))[0][0], True)
        built = build_frame0(mode, fan, t)
        if built == captured:
            ok += 1
        else:
            bad += 1
            corrupt.append((key, captured, built))

    print(f"model vs captured frame0: {ok} match, {bad} differ")
    for key, cap, built in corrupt:
        print(f"  {key}: captured={' '.join(f'{x:02x}' for x in cap)}"
              f"  model={' '.join(f'{x:02x}' for x in built)}")

    # Round-trip: generate base64 from model, decode, confirm bits match model
    print("\nround-trip generated base64 -> decode -> frame0 bytes:")
    rt_ok = 0
    total = 0
    for mode in ("cool", "heat"):
        for fan in FAN_CODE:
            for t in range(20, 29):
                total += 1
                f0 = build_frame0(mode, fan, t)
                b64 = encode_from_template(template, f0)
                dec = bits_to_bytes(demodulate(pulses(parse_envelope(b64)[3]))[0][0], True)
                if dec == f0:
                    rt_ok += 1
    print(f"  {rt_ok}/{total} generated codes decode back to the intended bytes")
