#!/usr/bin/env python3
"""Brute-force the checksum: express byte2/byte7 from bytes 0,1,3,4,5,6."""
from decode import load
from analyze import bits_to_bytes, decode_all


def rows(cfg):
    data, _ = decode_all(cfg)
    out = []
    for key in data:
        if len(key) != 4:
            continue
        mode, fan, _, t = key
        bys = bits_to_bytes(data[key][0], True)
        out.append((mode, fan, int(t), bys))
    return out


if __name__ == "__main__":
    cfg = load()
    R = rows(cfg)
    print("mode fan T  | b0 b1 b2 b3 b4 b5 b6 b7 | sumData  b2*256+b7  b7*256+b2")
    for mode, fan, t, b in sorted(R, key=lambda r: (r[0], r[1], r[2])):
        sumdata = b[0] + b[1] + b[3] + b[4] + b[5] + b[6]
        sumall = sum(b[:7])
        pair_be = b[2] * 256 + b[7]
        pair_le = b[7] * 256 + b[2]
        print(f"{mode:5s} {fan:6s} {t} | " + " ".join(f"{x:02x}" for x in b)
              + f" | sumD={sumdata:3d}(0x{sumdata:02x}) sum07={sumall:3d}(0x{sumall:02x})"
              + f" BE={pair_be:5d}(0x{pair_be:04x}) LE={pair_le:5d}")

    # Try: is (b2, b7high_nibble) a function of sum?
    print("\n=== relationship of checksum to sumData ===")
    for mode, fan, t, b in sorted(R, key=lambda r: (r[0], r[1], r[2])):
        if mode == "cool" and fan == "auto" and t in (20, 21):
            continue  # known anomaly
        sumdata = b[0] + b[1] + b[3] + b[4] + b[5] + b[6]
        chk16 = (b[2] << 8) | b[7]          # treat b2:b7 as 16-bit checksum value
        # hypothesis: chk16 == sumdata * 16 ?
        print(f"{mode:5s} {fan:6s} {t}: sumD=0x{sumdata:02x}({sumdata})"
              f" chk16=0x{chk16:04x}({chk16}) chk16/16={chk16/16:.2f}"
              f" chk16-16*sumD={chk16 - 16*sumdata}")
