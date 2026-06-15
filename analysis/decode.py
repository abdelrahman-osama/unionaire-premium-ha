#!/usr/bin/env python3
"""Decode Broadlink IR codes from the Unionaire/Premium SmartIR config."""
import base64
import json
import os
from collections import Counter, defaultdict

HERE = os.path.dirname(__file__)
CFG = os.path.join(HERE, "..", "premium_ac_config.json")
TICK_US = 1_000_000 / 32768  # ~30.5176 us per broadlink tick


def b64decode(s):
    return base64.b64decode(s + "=" * (-len(s) % 4))


def parse_envelope(b64):
    raw = b64decode(b64)
    typ, repeat = raw[0], raw[1]
    length = raw[2] | (raw[3] << 8)
    payload = raw[4:4 + length]
    return typ, repeat, length, payload, raw


def pulses(payload):
    out, i, n = [], 0, len(payload)
    while i < n:
        v = payload[i]
        if v == 0:
            if i + 2 >= n:
                break
            v = (payload[i + 1] << 8) | payload[i + 2]
            i += 3
        else:
            i += 1
        out.append(v)
    return out


def load():
    with open(CFG) as f:
        return json.load(f)


def iter_commands(cfg):
    cmds = cfg["commands"]
    for k in ("off", "on_once"):
        yield (k,), cmds[k]
    for mode in ("cool", "heat"):
        for fan in cfg["fanModes"]:
            for swing in cfg["swingModes"]:
                for temp, code in cmds[mode][fan][swing].items():
                    yield (mode, fan, swing, temp), code


STRUCT = 80  # ticks; anything bigger is a leader/gap, not a data bit


def demodulate(ps):
    """Return list of frames; each frame is a bitstring. Structural pulses
    (>STRUCT ticks) delimit frames. Within a frame, read (mark,space) pairs;
    space long => 1, short => 0."""
    frames = []
    cur = []
    i = 0
    n = len(ps)
    structural = []
    # walk pairs (mark, space)
    while i < n:
        v = ps[i]
        if v > STRUCT:
            # structural element; flush current frame
            if cur:
                frames.append("".join(cur))
                cur = []
            structural.append((i, v))
            i += 1
            continue
        # v is a mark; next should be a space
        if i + 1 >= n:
            break
        space = ps[i + 1]
        if space > STRUCT:
            # mark followed by structural space -> end of frame after this bit?
            # treat trailing mark as frame boundary
            if cur:
                frames.append("".join(cur))
                cur = []
            structural.append((i + 1, space))
            i += 2
            continue
        bit = "1" if space > 22 else "0"
        cur.append(bit)
        i += 2
    if cur:
        frames.append("".join(cur))
    return frames, structural


if __name__ == "__main__":
    cfg = load()
    marks, spaces = Counter(), Counter()
    all_decoded = {}
    for key, code in iter_commands(cfg):
        typ, repeat, length, payload, raw = parse_envelope(code)
        ps = pulses(payload)
        # collect mark/space distributions (data region only)
        for i in range(0, len(ps) - 1, 2):
            m, s = ps[i], ps[i + 1]
            if m <= STRUCT:
                marks[m] += 1
            if s <= STRUCT:
                spaces[s] += 1
        frames, structural = demodulate(ps)
        all_decoded[key] = (frames, structural)

    print("=== MARK durations (ticks) histogram ===")
    for v in sorted(marks):
        print(f"  {v:3d} ({round(v*TICK_US):4d}us): {marks[v]}")
    print("=== SPACE durations (ticks) histogram ===")
    for v in sorted(spaces):
        print(f"  {v:3d} ({round(v*TICK_US):4d}us): {spaces[v]}")

    print("\n=== Frame structure for sample commands ===")
    for key in [("off",), ("on_once",), ("cool", "auto", "down", "20"),
                ("cool", "auto", "down", "28"), ("heat", "auto", "down", "20")]:
        frames, structural = all_decoded[key]
        print(key)
        print("  nframes:", len(frames), "frame lens:", [len(f) for f in frames])
        print("  structural pulses:", [(idx, v) for idx, v in structural])
        for fi, f in enumerate(frames):
            print(f"  frame{fi} ({len(f)} bits): {f}")
