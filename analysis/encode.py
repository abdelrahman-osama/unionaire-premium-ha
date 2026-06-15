#!/usr/bin/env python3
"""Encoder: build a Broadlink IR base64 command for given frame0 bytes, using a
real captured code as the structural template (only the 64 frame0 data bits change)."""
import base64
from decode import (load, iter_commands, parse_envelope, pulses, demodulate,
                    b64decode, STRUCT)
from analyze import bits_to_bytes

# canonical bit timings in broadlink ticks (well within observed tolerance)
MARK = 0x0c        # ~366us
SHORT = 0x0d       # ~397us  -> bit 0
LONG = 0x21        # ~1007us -> bit 1


def bytes_to_bits(byts, lsb_first=True):
    out = []
    for b in byts:
        bs = f"{b:08b}"
        if lsb_first:
            bs = bs[::-1]
        out.extend(bs)
    return "".join(out)


def pulses_to_payload(ps):
    out = bytearray()
    for v in ps:
        if v < 256:
            out.append(v)
        else:
            out += bytes([0x00, (v >> 8) & 0xFF, v & 0xFF])
    return bytes(out)


def encode_from_template(template_b64, frame0_bytes):
    """Return new base64 IR code = template with frame0's 64 data bits replaced."""
    typ, repeat, length, payload, raw = parse_envelope(template_b64)
    ps = pulses(payload)
    # locate frame0: leader = ps[0],ps[1]; data bit-pairs start at index 2 until
    # the first structural pulse (>STRUCT).
    i = 2
    frame0_pulse_start = 2
    n_bits = 0
    while i + 1 < len(ps) and ps[i] <= STRUCT and ps[i + 1] <= STRUCT:
        n_bits += 1
        i += 2
    assert n_bits == 64, f"expected 64 frame0 bits, got {n_bits}"
    bits = bytes_to_bits(frame0_bytes, lsb_first=True)
    assert len(bits) == 64
    new_ps = list(ps)
    for bi, bit in enumerate(bits):
        new_ps[frame0_pulse_start + 2 * bi] = MARK
        new_ps[frame0_pulse_start + 2 * bi + 1] = LONG if bit == "1" else SHORT
    payload2 = pulses_to_payload(new_ps)
    hdr = bytes([typ, repeat, len(payload2) & 0xFF, (len(payload2) >> 8) & 0xFF])
    return base64.b64encode(hdr + payload2).decode()


if __name__ == "__main__":
    cfg = load()
    template = cfg["commands"]["off"]
    # round-trip verification: regenerate every captured code from its OWN frame0
    # bytes and confirm the decoded bits match the original exactly.
    ok = bad = 0
    for key, code in iter_commands(cfg):
        frames_orig, _ = demodulate(pulses(parse_envelope(code)[3]))
        f0_bytes = bits_to_bytes(frames_orig[0], True)
        regen = encode_from_template(template, f0_bytes)
        frames_new, _ = demodulate(pulses(parse_envelope(regen)[3]))
        if frames_new[0] == frames_orig[0] and frames_new[1] == frames_orig[1]:
            ok += 1
        else:
            bad += 1
            if bad <= 3:
                print("MISMATCH", key)
                print("  orig f0:", frames_orig[0])
                print("  new  f0:", frames_new[0])
    print(f"round-trip: {ok} ok, {bad} bad (of {ok+bad})")
