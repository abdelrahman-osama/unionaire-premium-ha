#!/usr/bin/env python3
"""Full byte grid + per-byte correlation analysis."""
from collections import defaultdict
from decode import load, iter_commands, parse_envelope, pulses, demodulate
from analyze import bits_to_bytes, decode_all


def b(key, data):
    return bits_to_bytes(data[key][0], True)


if __name__ == "__main__":
    cfg = load()
    data, _ = decode_all(cfg)
    temps = [str(x) for x in range(20, 29)]

    for mode in ("cool", "heat"):
        print(f"\n################ MODE={mode} ################")
        for fan in cfg["fanModes"]:
            print(f"--- fan={fan} ---  (T : b0 b1 b2 b3 b4 b5 b6 b7)")
            for t in temps:
                row = b((mode, fan, "down", t), data)
                print(f"  {t}: " + " ".join(f"{x:02x}" for x in row))

    # Per-byte: does it depend on temp? fan? mode?
    print("\n=== byte dependency analysis ===")
    for pos in range(8):
        # gather value as function of each axis
        by_temp = defaultdict(set)   # fixing cool/auto, vary temp
        by_fan = defaultdict(set)
        by_mode = defaultdict(set)
        distinct = set()
        for key in data:
            if len(key) != 4:
                continue
            mode, fan, _, t = key
            val = b(key, data)[pos]
            distinct.add(val)
        print(f"byte{pos}: {len(distinct)} distinct values: "
              + " ".join(f"{x:02x}" for x in sorted(distinct)))
