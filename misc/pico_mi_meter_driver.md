
# Pico → Moving-Iron Meter Driver (Full-Scale with HV Booster)

This document captures the key design decisions, parts, links, wiring notes, and example code we discussed for driving a **600 V moving‑iron panel meter** from a **Raspberry Pi Pico 2** (MicroPython), using a **high‑voltage boost module**. Accuracy is not a goal; we prioritize simple, safe full‑scale movement.


---

## 1) Approach (Simple, Open‑Loop)

- Use a **Nixie‑style HV boost module** set around **120–170 V DC**.
- Limit meter current with a **fixed series resistor** and sink current with a **high‑voltage transistor**.
- Drive the transistor from the Pico via **PWM → RC low‑pass filter** (no feedback; needle position is approximate).

**Text diagram**
```
+150 V (HV module)
   |
  33 kΩ 2 W  <-- current limiter (conservative)
   |
 [ Meter ]
   |
[ HV NPN ]  <-- MJE340 (TO‑126) or MPSA42 (TO‑92)
   |
  GND

Pico PWM --> 1 kΩ --> base/gate of HV device
                 |
                10 µF (to GND)
               (optional 100 nF in parallel)
```

> You can flip meter polarity on a moving‑iron meter; it’s not polarity‑sensitive. The 33 kΩ value is deliberately conservative so full‑scale is attainable without stressing the movement.

---

## 2) Shopping List & Links

### High‑Voltage Boost (choose one)
- **Amazon (MC34063‑based, 130–190 V adj.)**: https://www.amazon.com/Voltage-Converter-Supply-10V-13VDC-130V-190V/dp/B0D3766FF3
- **Tindie (NCH8200HV, fixed 170 V)**: https://www.tindie.com/products/omnixie/nch8200hv-nixie-high-voltage-power-module/
- **AliExpress (90–250 V adj.)**: https://www.aliexpress.com/item/1005005940853404.html
- **Elecrow (165–170 V fixed)**: https://www.elecrow.com/nixie-hvsmps.html
- **eBay example**: https://www.ebay.com/itm/146340258304

### HV Transistor (choose one)
- **MJE340 (NPN, 300 V, TO‑126)** (Amazon example): https://www.amazon.com/Pcs-MJE340-126-Plastic-Transistor/dp/B09PBLKZBK
- **MPSA42 (NPN, 300 V, TO‑92)** (Amazon example): https://www.amazon.com/MPSA42-Transistor-3-Pins-92-Piece/dp/B099675MBR

### Resistors & Capacitors
- **33 kΩ 2 W (series limiter)** (Amazon example): https://www.amazon.com/Resistors-Resistor-Repairing-Electronic-Components/dp/B0BWCR5SLC
- **1 kΩ (Pico → base)** (any 1/4 W pack): https://www.amazon.com/1k-resistor-pack/s?k=1k+resistor+pack
- **10 µF ≥16 V electrolytic (PWM filter)** (Amazon search): https://www.amazon.com/10uf-16v-capacitor/s?k=10uf+16v+capacitor
- **Optional 100 nF ceramic (in parallel with 10 µF)** – any generic pack
- **470 kΩ bleeder (0.25–1 W)** (Amazon search): https://www.amazon.com/470k-resistor/s?k=470k+resistor

### Available from Core Electronics (AU)
- **10 µF/25 V Electrolytic (SparkFun)**: https://core-electronics.com.au/electrolytic-decoupling-capacitors-10uf-25v.html

*Note:* Core Electronics does not currently list the MJE340/MPSA42 or the exact 33 kΩ 2 W / 470 kΩ values; source those from Amazon/eBay/Mouser/Element14.

---

## 3) Wiring Notes

- **HV side**: Place **33 kΩ** in series with the meter on the **high side**; the HV transistor acts as a **low‑side sink**.
- **Base drive**: Pico PWM → **1 kΩ** → base. Add a **10 µF** from base to ground (after the 1 kΩ) to smooth PWM. Optionally parallel with **100 nF**.
- **Common ground**: Connect Pico ground to HV module ground **only** at the transistor’s emitter/ source node. Keep HV wiring physically separated and insulated.
- **Bleeder**: Put **470 kΩ** across the HV module output so it discharges on power‑off.
- **Fuse (nice‑to‑have)**: A small fast blow (e.g., 50–100 mA) in series with the HV output for extra protection.

---

## 4) Example MicroPython (Pico 2)

```python
from machine import Pin, PWM
import time

PWM_PIN = 15  # pick a free GPIO
pwm = PWM(Pin(PWM_PIN))
pwm.freq(1000)  # 1 kHz; works well with 1k/10uF filter


def set_meter(percent: float):
    """Set approximate meter position 0..100%"""
    percent = max(0.0, min(100.0, float(percent)))
    duty = int(65535 * (percent / 100.0))
    pwm.duty_u16(duty)

# demo sweep
if __name__ == "__main__":
    while True:
        for i in range(0, 101, 1):
            set_meter(i)
            time.sleep(0.02)
        for i in range(100, -1, -1):
            set_meter(i)
            time.sleep(0.02)
```

---

## 5) Safety Checklist (HV ~120–170 V DC)

- Treat as **dangerous**: enclose the HV board and terminals; insulate exposed conductors.
- Use a **bleeder resistor** and verify capacitors are discharged before touching.
- Keep **low‑voltage Pico wiring** physically separated from **HV**.
- Power up with the HV module set to the **lowest voltage**, then increase slowly while observing the needle.

---

## 6) Quick Calibration (since accuracy doesn’t matter)

1. Set HV module ~**140–150 V**.
2. With the 33 kΩ in place, increase PWM until the needle reaches full‑scale. Note the **duty cycle** (approx. percent you send).
3. Use that percent as your “100%” in code; you can map 0–100% UI range directly to PWM duty.

---

**Prepared for:** David Peters  
**Date:** 2026‑01‑17

