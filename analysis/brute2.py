#!/usr/bin/env python3
"""Crack byte2 = f(mode, fan, temp / data bytes). Also verify byte7 rule globally."""
import json
import itertools


def nib(b):
    return (b >> 4) + (b & 0xF)


def nibsum(bs):
    return sum(nib(b) for b in bs)


D = json.load(open("decoded_grid.json"))
cells = [c for c in D["cells"] if not c["anomaly"]]


# ---- Verify byte7 rule globally: H == (nibsum(b0..b6) + L) % 16 ----
print("=== verify byte7 H rule on all clean cells ===")
bad = 0
for c in cells:
    b = c["frame0_lsb"]
    pred_H = (nibsum(b[0:7]) + (b[7] & 0xF)) % 16
    if pred_H != c["byte7_H"]:
        bad += 1
        if bad <= 5:
            print("  MISMATCH", c["mode"], c["fan"], c["temp"],
                  "pred", pred_H, "act", c["byte7_H"])
print(f"byte7 H rule: {len(cells)-bad}/{len(cells)} match")

# also: is byte7_L exactly turbo flag?
print("byte7_L by fan:", {c["fan"]: c["byte7_L"] for c in cells})


# ---- Brute force byte2 ----
# features available at generation time: mode(0/1), fan_rank(0-4), temp(20-28),
# and the constant/known bytes b0,b1,b3,b4,b5,b6.
print("\n=== brute force byte2 ===")
fan_rank = {"auto": 0, "low": 1, "medium": 2, "high": 3, "turbo": 4}


def feats(c):
    b = c["frame0_lsb"]
    return {
        "mode": 0 if c["mode"] == "cool" else 1,
        "rank": fan_rank[c["fan"]],
        "temp": c["temp"], "t20": c["temp"] - 20,
        "b0": b[0], "b1": b[1], "b3": b[3], "b4": b[4], "b5": b[5], "b6": b[6],
        "nibsum_db": nibsum([b[0], b[1], b[3], b[4], b[5], b[6]]),
        "sum_db": b[0] + b[1] + b[3] + b[4] + b[5] + b[6],
        "byte2": c["byte2"],
    }


F = [feats(c) for c in cells]

# Hypothesis family 1: byte2 = (mode<<4) | (A*rank + floor((temp - 20 + off)/period) + base)
best = []
for A in range(0, 6):
    for base in range(-4, 6):
        for period in range(1, 12):
            for off in range(0, 12):
                ok = True
                for f in F:
                    low = A * f["rank"] + base + (f["t20"] + off) // period
                    pred = (f["mode"] << 4) | (low & 0xF)
                    if low < 0 or low > 15 or pred != f["byte2"]:
                        ok = False
                        break
                if ok:
                    best.append(("fam1", A, base, period, off))
print("fam1 (A*rank+base+floor((t20+off)/period)) matches:", len(best))
for x in best[:10]:
    print("  ", x)

# Hypothesis family 2: byte2 linear in nibsum/sum of data bytes
best2 = []
for src in ("nibsum_db", "sum_db"):
    for mult in range(0, 4):
        for div in range(1, 33):
            for add in range(-32, 33):
                ok = True
                for f in F:
                    val = (f[src] * (mult if mult else 1) + add) // div if mult else (f[src] + add) // div
                    pred = (f["mode"] << 4) | (val & 0xF)
                    if pred != f["byte2"]:
                        ok = False
                        break
                if ok:
                    best2.append(("fam2", src, mult, div, add))
print("fam2 (byte2low = (src*mult+add)//div) matches:", len(best2))
for x in best2[:10]:
    print("  ", x)
