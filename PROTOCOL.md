# Unionaire / Premium AC — IR protocol (reverse-engineered)

This documents the IR protocol behind the Broadlink Base64 codes in
`premium_ac_config.json`, so codes can be **generated** instead of captured one
by one. Companion tool: [`unionaire_ir.py`](unionaire_ir.py).

Every claim below is verified against the 90 captured codes: the decoder + the
model reproduce **88/88** consistent captures byte-for-byte, and every generated
code decodes back to its intended bytes (**90/90**).

## 1. Transport (Broadlink wrapper)

Each command is a standard Broadlink IR packet, Base64-encoded:

```
byte 0      : 0x26  (IR)
byte 1      : repeat count (0x00)
byte 2..3   : payload length, little-endian
byte 4..    : pulse list, then 0x0d 0x05 terminator
```

A pulse is one byte = N ticks (1 tick = 1/32768 s ≈ 30.5 µs); a `0x00` byte
escapes a 16-bit big-endian tick count for values ≥ 256.

## 2. Modulation & framing

Pulse-distance coding, carrier ~38 kHz:

| element        | mark            | space                          |
|----------------|-----------------|--------------------------------|
| leader         | ~4.6 ms         | ~2.6 ms                        |
| bit `0`        | ~0.4 ms         | ~0.4 ms                        |
| bit `1`        | ~0.4 ms         | ~1.05 ms                       |

Each command sends **two 64-bit frames** separated by a ~21 ms gap:

* **Frame 0** — mode / fan / temperature (§3).
* **Frame 1** — swing + ionizer (§3a). (Looked constant at first only because every
  original capture used the same swing=down + ionizer=on.)

Bits are **LSB-first within each byte**.

## 3. Frame 0 — 8 bytes

Byte values shown after LSB-first reassembly:

| byte | meaning | value |
|------|---------|-------|
| b0 | header | `0x16` (constant) |
| b1 | mode + fan | `(fan << 4) \| mode` |
| b2 | mode/fan/temp preset | **vendor lookup table** (§4) |
| b3 | constant | `0x09` |
| b4 | constant | `0x10` |
| b5 | constant | `0x10` |
| b6 | temperature | `0x20 + (T − 20)` → `0x20`=20 °C … `0x28`=28 °C |
| b7 | checksum | §5 |

**b1 codes**

* mode (low nibble): `cool = 0x2`, `heat = 0x8`
* fan (high nibble): `auto = 1`, `high = 2`, `medium = 4`, `low = 8`, `turbo = 0`

## 3a. Frame 1 — swing + ionizer

`[00, 00, SWING, 00, IONIZER, 00, 00, CHK]`

| field | byte | values |
|---|---|---|
| swing (vertical louver) | frame1[2] | bottom `0x10`, mid-low `0x20`, middle `0x30`, top `0x40`, oscillate `0xf0` |
| ionizer | frame1[4] | on `0x50`, off `0x00` |
| checksum | frame1[7] | `(nibblesum(frame1[0..6]) mod 16) << 4` |

The original 90 codes all have ionizer **on** (`0x50`). Verified on hardware that
editing only frame1 (swing/ionizer) on a working code changes the AC behaviour as
expected — which also proves **frame0 `b2` is ignored by the AC** (a cosmetic
"last-button" indicator), explaining why it never fit a checksum (§4).

Still uncharacterised: horizontal swing (left/right, on/off), sleep, and the
frame0 `b3 = 0x09` feature (on in all originals) — each needs one capture toggled.

## 4. b2 — the vendor preset byte

b2's high nibble equals the mode (`0` cool / `1` heat). Its low nibble is a
small per-`(mode,fan)` index that starts at a base value and steps up by 1 as
temperature crosses fixed thresholds:

| mode/fan | base | +1 at temp | mode/fan | base | +1 at temp |
|----------|------|-----------|----------|------|-----------|
| cool/auto   | `0x00` | 25 | heat/auto   | `0x10` | 26 |
| cool/low    | `0x02` | 24 | heat/low    | `0x11` | 21 **and** 26 |
| cool/medium | `0x04` | 25 | heat/medium | `0x13` | 23 |
| cool/high   | `0x06` | 25 | heat/high   | `0x15` | 25 |
| cool/turbo  | `0x08` | 24 | heat/turbo  | `0x17` | 25 |

**This is genuinely a lookup table, not a formula.** Four independent search
strategies (subset sums, all CRC-8 polynomials, `floor((a·rank+b·temp+c)/N)`
families, and an LP-feasibility solver over divisors `N = 2..40`) all failed to
find any closed form — the best any arithmetic rule achieves is 75/88, because
the per-fan thresholds are non-monotonic in fan rank and `heat/low` increments
twice while every other band increments once. The table above reproduces all 88
consistent cells exactly.

**Extrapolation beyond 20–28 °C is unverified.** The model saturates (holds the
base below the lowest threshold, the max above the highest). Real firmware may
add thresholds outside the captured window. The AC's documented range is 20–28
°C, so this rarely matters; if you need 16–19 or 29–30 °C, capture one real
frame at each to confirm.

## 5. b7 — checksum + feature flags (solved)

```
low nibble  = feature flags:  bit0 = horizontal swing (L/R)
                              bit1 = sleep
                              bit2 = turbo (fan)
high nibble = (nibblesum(b0..b6) + low_nibble) mod 16
```

`nibblesum` adds the high and low nibble of every byte b0..b6 (b2 included).
Verified against every captured frame (the 88 mode/fan/temp cells, plus the
sleep on/off and horizontal-swing on/off captures).

## 5a. Feature locations & SmartIR coverage

| feature | encoding | in SmartIR? |
|---|---|---|
| mode / fan / temperature | frame0 b1, b6 | ✅ |
| vertical louver swing | frame1[2] | ✅ (5 positions) |
| ionizer | frame1[4] = `0x50`/`0x00` | ❌ not exposed (originals have it **on**) |
| sleep | b7 flag bit1 | ❌ not exposed |
| horizontal swing (L/R, on/off) | b7 flag bit0 | ❌ not exposed |
| turbo | fan field, mirrored in b7 flag bit2 | ✅ (as a fan speed) |
| timer | not decoded (not needed) | ❌ |

Cosmetic / AC-ignored bytes: **b2** ("last button pressed") and **b3**
(`0x09` in the original session, `0x00` later — a session/default field). Both
are proven non-functional: editing frame 1 on a working code with stale b2/b3
controls the AC correctly on hardware.

## 6. Power, and what can't be derived

* **Power is a pure toggle** (no absolute on/off). The power button always emits
  one frame — a normal state frame carrying the power flag `b7` low-nibble `0x0a`.
  Confirmed by capturing the button with the AC running and with it off: both are
  byte-identical (and identical to the stored `off`/`on_once`). So discrete
  power_on/power_off IR codes are impossible; rely on SmartIR's `power_sensor`.
* **Vertical swing** (louver up/down): solved — `frame1[2]`, see §3a.
* **Modes** `dry` / `fan_only` / `auto`, **horizontal swing** (left/right),
  **sleep**, and the `b3=0x09` feature are not yet characterised. One capture
  toggled per state is enough to extend the model.

## 7. Two inconsistent captures

`cool/auto/20` and `cool/auto/21` were captured with the remote in a different
feature state (`b2=0x57, b3=0x08` instead of `0x00/0x09`); their checksums are
self-consistent, so they're valid frames but inconsistent with the rest of the
grid. Corrected values:

```
cool/auto/20 : 16 12 00 09 10 10 20 70
cool/auto/21 : 16 12 00 09 10 10 21 80
```

## 8. Usage

```bash
python3 unionaire_ir.py generate cool high 23   # -> frame0 bytes + Base64
python3 unionaire_ir.py decode "Jg...=="        # -> frame0 / frame1 bytes
```

```python
import unionaire_ir as u
u.generate("heat", "turbo", 26)   # Base64 string ready for Broadlink/SmartIR
```
