#!/usr/bin/env python3
"""Brute-force search for the checksum formula (byte7 and/or byte2:byte7)."""
import itertools
from decode import load
from analyze import bits_to_bytes, decode_all


def rev8(x):
    return int(f"{x:08b}"[::-1], 2)


def rows(cfg):
    data, _ = decode_all(cfg)
    out = []
    for key in data:
        if len(key) != 4:
            continue
        mode, fan, _, t = key
        # skip known anomalies
        if mode == "cool" and fan == "auto" and t in ("20", "21"):
            continue
        lsb = bits_to_bytes(data[key][0], True)
        msb = [rev8(b) for b in lsb]
        out.append((mode, fan, int(t), lsb, msb))
    return out


def nib_sum(bs):
    s = 0
    for b in bs:
        s += (b & 0xF) + (b >> 4)
    return s


if __name__ == "__main__":
    cfg = load()
    R = rows(cfg)
    n = len(R)
    print(f"{n} clean cells")

    # --- Search byte7 as f(bytes 0..6) ---
    print("\n=== searching byte7 (LSB target) ===")
    found = []
    for use_msb in (False, True):
        for op in ("sum", "nibsum", "xor"):
            for include in (range(7), [0, 1, 3, 4, 5, 6], [1, 6], [1, 3, 6]):
                for mult in range(1, 17):
                    for comp in (False, True):
                        for revout in (False, True):
                            ok = True
                            const = None
                            for mode, fan, t, lsb, msb in R:
                                bs = msb if use_msb else lsb
                                vals = [bs[i] for i in include]
                                if op == "sum":
                                    base = sum(vals)
                                elif op == "nibsum":
                                    base = nib_sum(vals)
                                else:
                                    base = 0
                                    for v in vals:
                                        base ^= v
                                x = base * mult
                                if comp:
                                    x = (~x) & 0xFFFFFFFF
                                x &= 0xFF
                                if revout:
                                    x = rev8(x)
                                target = lsb[7]
                                c = (target - x) & 0xFF
                                if const is None:
                                    const = c
                                elif const != c:
                                    ok = False
                                    break
                            if ok:
                                found.append((use_msb, op, tuple(include), mult, comp, revout, const))
    print(f"byte7 matches found: {len(found)}")
    for f in found[:20]:
        print("  msb=%s op=%s incl=%s mult=%d comp=%s revout=%s const=0x%02x" % f)

    # --- Search 16-bit chk = byte2*256+byte7 as f(bytes excl 2,7) ---
    print("\n=== searching chk16 = byte2*256+byte7 ===")
    found2 = []
    for use_msb in (False, True):
        for op in ("sum", "nibsum"):
            for include in ([0, 1, 3, 4, 5, 6], [1, 6], range(7)):
                for mult in range(1, 33):
                    ok = True
                    const = None
                    for mode, fan, t, lsb, msb in R:
                        bs = msb if use_msb else lsb
                        vals = [bs[i] for i in include if i not in (2, 7)]
                        base = sum(vals) if op == "sum" else nib_sum(vals)
                        x = base * mult
                        chk = (lsb[2] << 8) | lsb[7]
                        c = chk - x
                        if const is None:
                            const = c
                        elif const != c:
                            ok = False
                            break
                    if ok:
                        found2.append((use_msb, op, tuple(i for i in include if i not in (2,7)), mult, const))
    print(f"chk16 linear matches: {len(found2)}")
    for f in found2[:20]:
        print("  msb=%s op=%s incl=%s mult=%d const=%d(0x%x)" % f)
