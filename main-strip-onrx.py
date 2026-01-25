
# Import necessary modules
from machine import PWM, Pin, I2C
import machine
import bluetooth
import time
from ble_simple_peripheral import BLESimplePeripheral
from pico_i2c_lcd import I2cLcd
from time import sleep
from msgpack_decoder import decode
from custom_char import get_arrow_chars
import micropython

# Make room for exception text if an IRQ throws
micropython.alloc_emergency_exception_buf(256)

# ===== Config =====
I2C_ADDR = 0x27
I2C_NUM_ROWS = 2
I2C_NUM_COLS = 16
use_I2C = False  # Run without I2C by default
DEVICE_NAME = "ESP32S3-UART"  # Keep this short; must match PC if connecting by name

# ===== Optional LCD init =====
if use_I2C:
    i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=1_000_000)
    i2clcd = I2cLcd(i2c, I2C_ADDR, I2C_NUM_ROWS, I2C_NUM_COLS)
    i2clcd.clear()
    i2clcd.putstr("BT Listening..")

# ===== PWM setup =====
frequency = 5000

m1_volt_pin = Pin(6)
m1_volt_meter = PWM(m1_volt_pin)
m1_volt_meter.freq(frequency)

m2_volt_pin = Pin(15)
m2_volt_meter = PWM(m2_volt_pin)
m2_volt_meter.freq(frequency)

displayed = 0
spinner = ['-', '\\', '|', '/']
spincount = 0

custom = get_arrow_chars()
fail_count = 0
reboots = 0

if use_I2C:
    a = 0
    for custom_char in custom:
        i2clcd.custom_char(a, custom_char)
        a += 1

def pprint(obj, indent=0):
    spacing = '  ' * indent
    if isinstance(obj, dict):
        for k, v in obj.items():
            print(f"{spacing}{k}:")
            pprint(v, indent + 1)
    elif isinstance(obj, list):
        for item in obj:
            pprint(item, indent + 1)
    else:
        print(f"{spacing}{obj}")

def restart_ble(ble, disconnect_handle=None, reinit_cb=None):
    """Restart BLE stack.
    ble: bluetooth.BLE() instance
    disconnect_handle: optional conn handle to disconnect first
    reinit_cb: callable to rebuild services/advertising after restart
    """
    try:
        ble.gap_advertise(None)
    except Exception:
        pass
    if disconnect_handle is not None:
        try:
            ble.gap_disconnect(disconnect_handle)
        except Exception:
            pass
    ble.active(False)
    time.sleep_ms(200)
    ble.active(True)
    if callable(reinit_cb):
        reinit_cb(ble)

def update_traffic(data):
    global spincount, reboots

    LCDLine0 = ""
    LCDLine1 = ""

    try:
        LCDLine0 = data['LCD']['0'][:15]
        LCDLine1 = data['LCD']['1'][:15]

        # Clamp to keep within PWM range
        moving_iron_volts = min(62000, data["meter"]["m1"]["v"])
        m1_volt_meter.duty_u16(int(moving_iron_volts))

        m2_volts = data["meter"]["m2"]["v"]
        if m2_volts > 0:
            m2_volt_meter.duty_u16(int(m2_volts))

    except Exception as e:
        print("update_traffic error:", e)

    if use_I2C:
        i2clcd.move_to(0, 0); i2clcd.putstr(LCDLine0.ljust(16))
        i2clcd.move_to(0, 1); i2clcd.putstr(LCDLine1.ljust(10))
        i2clcd.move_to(10, 1); i2clcd.putstr(f"B:{reboots}")
        i2clcd.move_to(15, 1); i2clcd.putstr(chr(spincount))

    spincount = (spincount + 1) % 8

def run_meter_down():
    pwm = m1_volt_meter.duty_u16()
    print(f"pwm={pwm}")
    while pwm > 32768:
        print(f"shutting down: {pwm}")
        pwm -= 1000
        m1_volt_meter.duty_u16(pwm)
        sleep(0.1)
    m1_volt_meter.duty_u16(32768)

def get_reboot_counter():
    file_path = "reboots.txt"
    try:
        with open(file_path, "r") as f:
            first_line = f.readline().strip()
            current = int(first_line) if first_line else 0
    except (OSError, ValueError):
        current = 0
    return current

def update_reboot_counter():
    file_path = "reboots.txt"
    try:
        with open(file_path, "r") as f:
            first_line = f.readline().strip()
            current = int(first_line) if first_line else 0
    except (OSError, ValueError):
        current = 0
    current += 1
    with open(file_path, "w") as f:
        f.write(str(current) + "\n")

# ============================
# Fast RX path (ISR/callback)
# ============================
# Move all expensive work out of on_rx (no prints/joins/decodes here).

# Choose a safe max number of fragments per message
MAX_FRAGS = 64  # adjust if your PC sender uses more

# Shared RX aggregator state (accessed by ISR + main loop)
_rx_expected = 0        # total fragments expected for current message
_rx_msg_id = -1         # current message id (from header)
_rx_frags = [None] * MAX_FRAGS  # store memoryview for each fragment
_rx_ready = False       # set to True when a full message has been received
_rx_overflow = 0        # count fragments dropped due to overflow/corruption
_rx_msg_count = 0       # for logging in main loop

# Helper: very quick reset of current aggregation
def _rx_reset(total, msg_id):
    global _rx_expected, _rx_msg_id
    _rx_expected = total
    _rx_msg_id = msg_id
    # Do NOT reallocate the list; just clear entries we might use
    # (only clear as many as needed for speed)
    for i in range(total if total <= MAX_FRAGS else MAX_FRAGS):
        _rx_frags[i] = None

def on_rx(data):
    """
    BLE write callback. Keep it tiny:
    - read header (seq,total,msg_id)
    - stash payload (memoryview) into pre-allocated table
    - when last fragment arrives, set _rx_ready flag
    """
    global _rx_ready, _rx_overflow, _rx_msg_count

    # Minimal validation
    if not data or len(data) < 3:
        # Too short; drop silently (no prints in callback)
        return

    seq = data[0]
    total = data[1]
    msg_id = data[2]

    # Guard against unreasonable totals
    if total == 0 or total > MAX_FRAGS:
        _rx_overflow += 1
        return

    # Start of new message: reset aggregator
    if seq == 0:
        _rx_reset(total, msg_id)

    # Only accept fragments within range of current message
    if seq >= total or seq >= MAX_FRAGS:
        _rx_overflow += 1
        return

    # Stash payload as memoryview (avoid copies/allocs)
    # Note: we intentionally avoid rstrip() here (expensive). We'll trim zeros later.
    _rx_frags[seq] = memoryview(data)[3:]

    # Last fragment received?
    if (seq + 1) == total:
        # Set ready flag; main loop will assemble+decode
        irq_state = machine.disable_irq()
        _rx_ready = True
        _rx_msg_count += 1
        machine.enable_irq(irq_state)

# ============================
# Main program
# ============================

if __name__ == "__main__":
    in_failure = 0
    has_connected = False
    reboots = get_reboot_counter()

    try:
        ble = bluetooth.BLE()
        print(">>------------")
        sp = BLESimplePeripheral(ble, DEVICE_NAME)
        sp.on_write(on_rx)  # fast callback set once
        print("------------<<")

        prev_connected = False
        last_print = 0  # rate-limit prints

        while True:
            connected = sp.is_connected()

            # Edge-triggered logs
            if connected != prev_connected:
                if connected:
                    print("Connected; resetting fail_count")
                    fail_count = 0
                    has_connected = True
                else:
                    print("Disconnected")
                prev_connected = connected

            # ======= Drain completed RX messages (heavy work here) =======
            # Check if a full message is ready
            do_process = False
            expected_local = 0
            msg_id_local = -1

            irq_state = machine.disable_irq()
            if _rx_ready:
                do_process = True
                _rx_ready = False
                expected_local = _rx_expected
                msg_id_local = _rx_msg_id
                # Copy references to current fragments quickly (shallow)
                # Avoid list slicing which allocates unpredictably;
                # we will read directly from _rx_frags[0..expected_local-1].
            machine.enable_irq(irq_state)

            if do_process:
                # Assemble full payload into a single bytearray
                # (We avoid b"".join for better control, and trim zeros only once)
                ba = bytearray()
                # Concatenate each fragment
                for i in range(expected_local):
                    frag = _rx_frags[i]
                    if frag is not None:
                        ba.extend(frag)
                    else:
                        # Missing fragment: count and abort this message
                        print("RX missing fragment at index", i)
                        ba = None
                        break

                if ba is not None:
                    # Trim trailing NUL padding once (applies if sender pads the last chunk)
                    # Manual trim avoids creating new objects repeatedly
                    j = len(ba) - 1
                    while j >= 0 and ba[j] == 0:
                        j -= 1
                    if j < (len(ba) - 1):
                        # slice only if needed
                        ba = ba[:j+1]

                    # Decode + handle
                    try:
                        message = decode(ba)
                        # Optional: print(message) is expensive; keep brief if needed
                        update_traffic(message)
                        fail_count = 0
                    except Exception as e:
                        print("decode error:", e)

            # ======= Slow, rate-limited status (every ~1s) =======
            now = time.ticks_ms()
            if time.ticks_diff(now, last_print) >= 1000:
                if connected:
                    print(f"In Connected Loop. Fail Count = {fail_count}")
                    # Original code decreased fail_count here; keep behavior
                    fail_count -= 1
                else:
                    in_failure += 1
                    fail_count += 1
                    print(f"Not Connected Fail Count {fail_count}")
                    if use_I2C:
                        i2clcd.move_to(0, 1)
                        i2clcd.putstr(f"NC:{fail_count}".ljust(16))
                last_print = now

            # Optional auto-reboot logic remains commented out
            # if fail_count >= 3 and has_connected and in_failure > 5:
            #     run_meter_down()
            #     machine.reset()

            time.sleep_ms(50)  # small sleep keeps loop responsive without spamming

    except KeyboardInterrupt:
        print("Ctrl-C")
        run_meter_down()
        sleep(0.1)
    finally:
        run_meter_down()
