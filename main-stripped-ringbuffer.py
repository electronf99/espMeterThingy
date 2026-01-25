
# Import necessary modules
from machine import PWM, Pin, I2C, disable_irq, enable_irq
import machine
import bluetooth
import time
from ble_simple_peripheral import BLESimplePeripheral
from pico_i2c_lcd import I2cLcd
from time import sleep
from msgpack_decoder import decode
from custom_char import get_arrow_chars
import micropython
import gc

micropython.alloc_emergency_exception_buf(256)  # safer error text in IRQ

# ------------------------
# LCD config
# ------------------------
I2C_ADDR = 0x27
I2C_NUM_ROWS = 2
I2C_NUM_COLS = 16
use_I2C = False

if use_I2C:
    i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=1000000)
    i2clcd = I2cLcd(i2c, I2C_ADDR, I2C_NUM_ROWS, I2C_NUM_COLS)
    i2clcd.clear()
    i2clcd.putstr("BT Listening..")

# ------------------------
# PWM (meters)
# ------------------------
frequency = 5000
m1_volt_pin = machine.Pin(6)
m1_volt_meter = PWM(m1_volt_pin)
m1_volt_meter.freq(frequency)

m2_volt_pin = machine.Pin(15)
m2_volt_meter = PWM(m2_volt_pin)
m2_volt_meter.freq(frequency)

# ------------------------
# UI helpers
# ------------------------
spinner = ['-', '\\', '|', '/']
spincount = 0
custom = get_arrow_chars()
if use_I2C:
    for idx, custom_char in enumerate(custom):
        i2clcd.custom_char(idx, custom_char)

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

# ------------------------
# State / counters
# ------------------------
packet_count = 0
fail_count   = 0
reboots      = 0  # unused unless you add your reboot counter
heap_free_hwm = 0

# ------------------------
# Safe message assembly (pre-allocated)
# ------------------------
# TUNE: choose a maximum assembled message size you expect
_MAX_MSG = 8192           # bytes
_ASSEM   = bytearray(_MAX_MSG)
_ASSEM_LEN = 0            # how many bytes copied
_ASSEM_MSG_ID = -1        # last msg_id seen (optional)
_ASSEM_EXPECTED_SEQ = 0   # expected next seq
_ASSEM_TOTAL = 0          # total packets expected
_MESSAGE_READY = 0        # 0/1 flag
_MESSAGE_LEN = 0
_SCHEDULE_PENDING = 0     # avoid flooding scheduler

# Optional: strip trailing zero padding without allocations
def _trimmed_len(view):
    # walk backward for b'\x00' pad
    n = len(view)
    while n > 0 and view[n-1] == 0:
        n -= 1
    return n

def _reset_assembly(total, msg_id):
    global _ASSEM_LEN, _ASSEM_MSG_ID, _ASSEM_EXPECTED_SEQ, _ASSEM_TOTAL
    _ASSEM_LEN = 0
    _ASSEM_MSG_ID = msg_id
    _ASSEM_EXPECTED_SEQ = 0
    _ASSEM_TOTAL = total

def _commit_message():
    """Mark the currently assembled bytes as a complete message."""
    global _MESSAGE_READY, _MESSAGE_LEN
    _MESSAGE_LEN = _ASSEM_LEN
    _MESSAGE_READY = 1

def _schedule_process():
    global _SCHEDULE_PENDING
    if not _SCHEDULE_PENDING:
        _SCHEDULE_PENDING = 1
        micropython.schedule(_process_message, 0)

# -------------
# on_rx callback (IRQ/soft-IRQ context! Keep it tiny & no heavy allocs)
# -------------
def on_rx(data: bytes):
    # data format per your code:
    # [0]=seq, [1]=total_packets, [2]=msg_id, [3:]=payload (may be padded with NULs)
    global packet_count, fail_count
    global _ASSEM_LEN, _ASSEM_EXPECTED_SEQ, _ASSEM_TOTAL, _ASSEM_MSG_ID
    global _MESSAGE_READY

    if not data or len(data) < 3:
        return

    seq         = data[0]
    total_pkts  = data[1]
    msg_id      = data[2]

    # If first packet or new message id, reset assembly
    if seq == 0 or msg_id != _ASSEM_MSG_ID:
        _reset_assembly(total_pkts, msg_id)

    # drop if seq is not what we expect (out-of-order)
    if seq != _ASSEM_EXPECTED_SEQ:
        # out-of-sequence; restart assembly for robustness
        _reset_assembly(total_pkts, msg_id)
        # attempt to treat this packet as seq 0
        if seq != 0:
            return

    # Copy payload into pre-allocated buffer
    # Use memoryview to avoid creating new objects
    src  = memoryview(data)
    pay  = src[3:]  # payload slice (view)
    # Trim trailing zeros without allocating
    n = _trimmed_len(pay)
    if n:
        # bounds check against _MAX_MSG
        if _ASSEM_LEN + n > _MAX_MSG:
            # message too large; reset and drop
            _reset_assembly(total_pkts, msg_id)
            return
        _ASSEM[_ASSEM_LEN:_ASSEM_LEN+n] = pay[:n]
        _ASSEM_LEN += n

    _ASSEM_EXPECTED_SEQ += 1

    # If last packet, mark ready and schedule processing
    if (seq + 1) == total_pkts:
        packet_count += 1
        fail_count = 0
        _commit_message()
        _schedule_process()


def ljust_mp(s, width, fill=' '):
    """Left-justify s to exactly width chars using fill (ASCII).
       Truncates if s is longer. Works on MicroPython."""
    s = str(s)            # ensure it's a string
    n = width - len(s)
    if n > 0:
        return s + (fill * n)
    return s[:width]


# -------------
# Scheduled message processor (runs in main VM context)
# -------------
def _process_message(_arg):
    global _MESSAGE_READY, _MESSAGE_LEN, _SCHEDULE_PENDING, fail_count, heap_free_hwm
    try:
        # Atomically snapshot message length and clear READY
        state = disable_irq()
        try:
            ready = _MESSAGE_READY
            msg_len = _MESSAGE_LEN
            _MESSAGE_READY = 0
        finally:
            enable_irq(state)

        if not ready or msg_len <= 0:
            return

        # Decode (safe to allocate here)
        msg_bytes = bytes(memoryview(_ASSEM)[:msg_len])
        message = decode(msg_bytes)

        # ---- Do your work here (safe context) ----
        # For example: update meters and LCD if fields exist
        try:

            # heap_free_hwm = min(heap_free_hwm, gc.mem_free())
            # print(
            #     f"FC {fail_count} | Free Mem: {gc.mem_free()} | "
            #     f"USED: {gc.mem_alloc()} | HWM: {heap_free_hwm} | ",
            #     end=""
            # )

            #print(f"{packet_count} {ljust_mp(message["LCD"]["0"],16)}")

            print(message)
            # Clamp and drive meter 1
            m1_val = message["meter"]["m1"]["v"]
            if m1_val is not None:
                m1_val = min(62000, int(m1_val))
                m1_volt_meter.duty_u16(m1_val)

            # Drive meter 2 if > 0
            m2_val = int(message["meter"]["m2"]["v"])
            if m2_val > 0:
                m2_volt_meter.duty_u16(m2_val)

            if use_I2C:
                line0 = str(message["LCD"]["0"])[:16].ljust(16)
                line1 = str(message["LCD"]["1"])[:16].ljust(16)
                i2clcd.move_to(0, 0); i2clcd.putstr(line0)
                i2clcd.move_to(0, 1); i2clcd.putstr(line1)
        except Exception as e:
            # If message lacks fields, keep running
            print("Process msg error:", e)

    finally:
        _SCHEDULE_PENDING = 0  # allow another schedule

# ------------------------
# Main
# ------------------------
if __name__ == "__main__":
    in_failure = 0
    has_connected = False

    try:
        ble = bluetooth.BLE()
        print(">>------------")
        sp = BLESimplePeripheral(ble, "pico2w")
        print("------------<<")
        heap_free_hwm = gc.mem_free()

        # Register on_write ONCE (BLESimplePeripheral queues it internally)
        sp.on_write(on_rx)

        while True:
            if sp.is_connected():
                has_connected = True
                sleep(1)

                # heap_free_hwm = min(heap_free_hwm, gc.mem_free())
                # print(
                #     f"PC {packet_count} FC {fail_count} | Free Mem: {gc.mem_free()} | "
                #     f"USED: {gc.mem_alloc()} | HWM: {heap_free_hwm} | ",
                #     end=""
                # )
                # print("In Connected Loop.")

                # You were decrementing fail_count each loop; keep if you want a timeout counter
                fail_count -= 1

            else:
                in_failure += 1
                fail_count += 1
                sleep(1)

                print(f"Not Connected Fail Count {fail_count}")

                if use_I2C:
                    i2clcd.move_to(0, 1)
                    i2clcd.putstr(f"NC:{str(fail_count)}{' '*16}")

    except KeyboardInterrupt:
        print("Ctrl-C")
        sleep(0.1)
    finally:
        print("Ctrl-C final")
