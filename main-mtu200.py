
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
rx_packets = []

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

# Define a callback function to handle received data
count = 0
def on_rx(data):
    global rx_packets, fail_count,count
    
    if not data or len(data) < 3:
        print("on_rx: short packet")
        return

    seq, total_packets, msg_id = data[0], data[1], data[2]  # noqa: F841
    #print(f"{seq} ------> {data}")
    
    if seq == 0:
        rx_packets = []

    # payload = data[3:].rstrip(b"\x00")
    # rx_packets.append(payload)

    if total_packets == seq + 1:
        full_payload = b"".join(rx_packets)
        count += 1
        print(count)
    
        try:
            message = decode(full_payload)
            print(total_packets, message)
            update_traffic(message)
            fail_count = 0
        except Exception as e:
            print("decode error:", e)
    

def run_meter_down():
    pwm = m1_volt_meter.duty_u16()
    print(f"pwm={pwm}")
    while pwm > 32768:
        print(f"shutting down: {pwm}")
        pwm -= 1000
        m1_volt_meter.duty_u16(pwm)  # FIX: actually set the reduced value
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


if __name__ == "__main__":
    in_failure = 0
    has_connected = False
    reboots = get_reboot_counter()

    try:
        ble = bluetooth.BLE()
        print(">>------------")
        sp = BLESimplePeripheral(ble, DEVICE_NAME)
        sp.on_write(on_rx)  # set once
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

            # Slow, rate-limited status (every ~1s)
            now = time.ticks_ms()
            if time.ticks_diff(now, last_print) >= 1000:
                if connected:
                    print(f"In Connected Loop. Fail Count = {fail_count}")
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
