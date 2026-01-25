
import machine
import utime

# IMPORTANT:
# VSYS/3 is routed to ADC channel 3 via GPIO29 on Pico/Pico 2 boards.
adc = machine.ADC(3)  # ADC channel 3 (GPIO29)

# If you prefer pin form:
# adc = machine.ADC(machine.Pin(29))  # same thing

# Optionally measure 3V3 reference drift with ADC Vref if available on your build.
# Most builds use 3.3 V as the reference.
VREF = 3.3

# The hardware divider is approx 1/3 (VSYS -> GPIO29). Multiply by ~3 to get VSYS.
DIVIDER_SCALE = 3.0

def read_vsys():
    raw = adc.read_u16()  # 0..65535
    v_gpio29 = (raw / 65535.0) * VREF
    vsys = v_gpio29 * DIVIDER_SCALE
    return raw, v_gpio29, vsys

while True:
    raw, v_gp29, vsys = read_vsys()
    print(f"ADC raw={raw}  GPIO29={v_gp29:.3f} V  VSYS≈{vsys:.3f} V")
    utime.sleep(1)
