#!/usr/bin/env python3
"""
Unionaire / Premium air-conditioner IR protocol — decoder + code generator.

Reverse-engineered from the Broadlink Base64 codes in premium_ac_config.json.
Lets you GENERATE new SmartIR/Broadlink codes for any cool/heat * fan * temp
combination instead of capturing each one from the physical remote.

------------------------------------------------------------------------------
PROTOCOL SUMMARY  (see PROTOCOL.md for the full write-up)
------------------------------------------------------------------------------
Transport : Broadlink IR packet (0x26), pulse-distance modulation, ~38 kHz.
Framing   : leader (~4.6 ms / ~2.6 ms) + 64 data bits, sent as TWO frames
            separated by a ~21 ms gap. Frame 0 carries mode/fan/temp; frame 1
            carries swing + ionizer. Bits are LSB-first within each byte; a bit is a
            fixed ~0.4 ms mark followed by a ~0.4 ms space (0) or ~1.05 ms (1).

Frame 0 = 8 bytes (shown as the LSB-first byte value):
  b0 = 0x16                      constant header
  b1 = (fan << 4) | mode         mode: cool=0x2, heat=0x8
                                 fan : auto=1, high=2, medium=4, low=8, turbo=0
  b2 = mode/fan/temp preset      VENDOR LOOKUP TABLE (no arithmetic rule — this
                                 was proven by exhaustive + LP search). See B2_*.
  b3 = 0x09                      constant
  b4 = 0x10                      constant
  b5 = 0x10                      constant
  b6 = 0x20 + (temp - 20)        temperature, 0x20=20 C ... 0x28=28 C
  b7 = checksum + feature flags  low nibble = flags: bit0 horizontal-swing,
                                   bit1 sleep, bit2 turbo
                                 high nibble = (nibblesum(b0..b6) + flags) mod 16

Frame 1 = 8 bytes [00, 00, SWING, 00, IONIZER, 00, 00, checksum]:
  frame1[2] = swing   : bottom=0x10, mid-low=0x20, middle=0x30, top=0x40, oscillate=0xf0
  frame1[4] = ionizer : 0x50 = on, 0x00 = off
  frame1[7] = (nibblesum(frame1[0..6]) mod 16) << 4

Feature summary (which SmartIR supports vs not):
  SmartIR-mapped  : mode, fan, temp (frame0); vertical-louver swing (frame1[2]).
  Known but not in SmartIR : ionizer (frame1[4]); sleep (b7 flag bit1);
                             horizontal swing on/off (b7 flag bit0); turbo
                             (fan, mirrored in b7 flag bit2). timer: not decoded.
Note: frame0 b2 is a "last-button-pressed" indicator the AC ignores (verified on
hardware), which is why it never fit a checksum. b3 = 0x09 in all original
captures, 0x00 in later sessions (a session/default field, also AC-ignored);
build_frame0 keeps 0x09 to match the originals.

Power on/off is a single TOGGLE command (captured 'off' and 'on_once' are
byte-identical). The original captured codes all have ionizer ON.
"""
from __future__ import annotations
import base64

# --- one captured code, used purely as a STRUCTURAL template -----------------
# Only frame 0's 64 data bits are rewritten; leaders, the inter-frame gap, the
# constant frame 1 and the trailer are reused verbatim from this real code.
_TEMPLATE = ("JgAUAZlVCw0NIQojDQwKIw0MCg8NDAoODSALDg0MDSANDAsODAwNDAoODgwJDwsODQwKIwsOCg4N"
             "DAoODSEKDg0MDQsNDA0MCg8NDAoPCiMKDg0MCw4KDg0MCg4NDA0gDQwLDg0MDQwKDg0hCg4NDAoj"
             "DQwKDg0MDSANDAojDQwLDg0MDSANAAKwm9QAATOpDgsKDw0MCg4NDA0MCg4NDAsODQwMDAwNDQwK"
             "Dg0MCw4KDg0NCQ8NDAsiDQwKDg0MDQwKDg0MCg8NDAwNCg4NDAoODQwLDg0MDSANDAwhDQwMDQoO"
             "DQwKDg0MDQwKDg0NCg4NDAsNDQwNDAoODQwKDwsODQwKDg0MCw0NIQojDQwKAAKypwANBQ==")

# Power toggle (captured). Pressing it flips the AC on/off.
POWER_TOGGLE = _TEMPLATE

MODE_CODE = {"cool": 0x2, "heat": 0x8}
FAN_CODE = {"auto": 1, "high": 2, "medium": 4, "low": 8, "turbo": 0}
# louver positions (frame1[2]); keys are the SmartIR-facing swing-mode names.
SWING = {"bottom": 0x10, "mid-low": 0x20, "middle": 0x30, "top": 0x40, "oscillate": 0xf0}
IONIZER = {True: 0x50, False: 0x00}

# byte2 vendor table: (base value, [temperatures at which it increments by 1]).
# Reproduces all 88 clean captured cells exactly (the two corrupt cool/auto
# 20 & 21 captures excluded). Confirmed independently by 4 search methods.
B2_TABLE = {
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

# canonical bit timings (broadlink ticks; comfortably inside observed tolerance).
# _STRUCT (80) separates data bits (mark/space <= ~40) from leaders/gaps (>= ~84).
_MARK, _SHORT, _LONG, _STRUCT = 0x0C, 0x0D, 0x21, 80


def _nib(b):
    return (b >> 4) + (b & 0xF)


def byte2(mode, fan, temp):
    """Vendor preset byte (b2). Exact for temp 20..28; saturates outside."""
    base, thr = B2_TABLE[(mode, fan)]
    return base + sum(1 for t in thr if temp >= t)


def checksum(b, sleep=False, hswing=False):
    """b7 from bytes b0..b6 plus feature flags (b is a list of >=7 ints).

    b7 low nibble = feature flags: bit0 horizontal-swing, bit1 sleep,
    bit2 turbo (turbo == fan_code 0). High nibble = (nibblesum(b0..b6) +
    flags) mod 16. Verified against every captured frame.
    """
    flags = ((1 if hswing else 0) | (2 if sleep else 0)
             | (0x4 if (b[1] >> 4) == FAN_CODE["turbo"] else 0))
    high = (sum(_nib(x) for x in b[0:7]) + flags) & 0xF
    return (high << 4) | flags


def build_frame0(mode, fan, temp, sleep=False, hswing=False):
    """Return the 8 data bytes for the given state.

    sleep / hswing (horizontal swing) are not SmartIR-mappable but supported
    here for completeness; both default off.
    """
    if mode not in MODE_CODE:
        raise ValueError(f"mode must be one of {list(MODE_CODE)}")
    if fan not in FAN_CODE:
        raise ValueError(f"fan must be one of {list(FAN_CODE)}")
    b = [0x16, (FAN_CODE[fan] << 4) | MODE_CODE[mode],
         byte2(mode, fan, temp), 0x09, 0x10, 0x10, 0x20 + (temp - 20), 0]
    b[7] = checksum(b, sleep, hswing)
    return b


def build_frame1(swing="bottom", ionizer=True):
    """Return the 8 bytes of frame 1 (swing + ionizer)."""
    if swing not in SWING:
        raise ValueError(f"swing must be one of {list(SWING)}")
    f = [0, 0, SWING[swing], 0, IONIZER[bool(ionizer)], 0, 0, 0]
    f[7] = (sum(_nib(x) for x in f[0:7]) & 0xF) << 4
    return f


# --- Broadlink (de)serialisation ---------------------------------------------
def _b64decode(s):
    return base64.b64decode(s + "=" * (-len(s) % 4))


def _pulses(payload):
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


def _to_payload(ps):
    out = bytearray()
    for v in ps:
        out += bytes([v]) if v < 256 else bytes([0, (v >> 8) & 0xFF, v & 0xFF])
    return bytes(out)


def _bits(byts):
    return "".join(f"{b:08b}"[::-1] for b in byts)  # LSB-first per byte


def _frame_runs(ps):
    """Return [(start_index, n_bits), ...] for each run of data-bit pairs."""
    runs, i = [], 0
    while i < len(ps):
        if ps[i] <= _STRUCT and i + 1 < len(ps) and ps[i + 1] <= _STRUCT:
            start = i
            while i + 1 < len(ps) and ps[i] <= _STRUCT and ps[i + 1] <= _STRUCT:
                i += 2
            runs.append((start, (i - start) // 2))
        else:
            i += 1
    return runs


def generate(mode, fan, temp, swing="bottom", ionizer=True, sleep=False, hswing=False):
    """Return a Broadlink Base64 IR code for the given AC state.

    Rewrites both frames of the template: frame 0 = mode/fan/temp (+sleep/hswing
    flags), frame 1 = swing + ionizer. Canonical bit timings verified on hardware.
    """
    raw = _b64decode(_TEMPLATE)
    typ, repeat = raw[0], raw[1]
    length = raw[2] | (raw[3] << 8)
    ps = _pulses(raw[4:4 + length])
    runs = _frame_runs(ps)
    assert len(runs) >= 2 and runs[0][1] == 64 and runs[1][1] == 64, runs
    for (start, _), byts in zip(runs, (build_frame0(mode, fan, temp, sleep, hswing),
                                       build_frame1(swing, ionizer))):
        for k, bit in enumerate(_bits(byts)):
            ps[start + 2 * k] = _MARK
            ps[start + 2 * k + 1] = _LONG if bit == "1" else _SHORT
    payload = _to_payload(ps)
    hdr = bytes([typ, repeat, len(payload) & 0xFF, (len(payload) >> 8) & 0xFF])
    return base64.b64encode(hdr + payload).decode()


def decode(b64):
    """Decode a Broadlink Base64 IR code to (frame0_bytes, frame1_bytes)."""
    raw = _b64decode(b64)
    length = raw[2] | (raw[3] << 8)
    ps = _pulses(raw[4:4 + length])
    frames, cur, i = [], [], 0
    while i < len(ps):
        if ps[i] > _STRUCT:
            if cur:
                frames.append(cur)
                cur = []
            i += 1
            continue
        if i + 1 >= len(ps):
            break
        if ps[i + 1] > _STRUCT:
            if cur:
                frames.append(cur)
                cur = []
            i += 2
            continue
        cur.append("1" if ps[i + 1] > 22 else "0")
        i += 2
    if cur:
        frames.append(cur)
    out = []
    for fr in frames:
        bs = "".join(fr)
        out.append([int(bs[j:j + 8][::-1], 2) for j in range(0, len(bs) - 7, 8)])
    return out


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Unionaire/Premium AC IR tool")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="make a Base64 code")
    g.add_argument("mode", choices=list(MODE_CODE))
    g.add_argument("fan", choices=list(FAN_CODE))
    g.add_argument("temp", type=int)
    g.add_argument("swing", nargs="?", default="down", choices=list(SWING))
    g.add_argument("--no-ionizer", action="store_true")
    d = sub.add_parser("decode", help="decode a Base64 code to bytes")
    d.add_argument("code")
    a = p.parse_args()
    if a.cmd == "generate":
        ion = not a.no_ionizer
        print("frame0 :", " ".join(f"{x:02x}" for x in build_frame0(a.mode, a.fan, a.temp)))
        print("frame1 :", " ".join(f"{x:02x}" for x in build_frame1(a.swing, ion)))
        print("base64 :", generate(a.mode, a.fan, a.temp, a.swing, ion))
    else:
        for k, fr in enumerate(decode(a.code)):
            print(f"frame{k}:", " ".join(f"{x:02x}" for x in fr))
