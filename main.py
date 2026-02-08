
# Import necessary modules
from machine import PWM, Pin, I2C, disable_irq, enable_irq
import machine
import bluetooth
from ble_simple_peripheral import BLESimplePeripheral
from time import sleep
from msgpack_decoder import decode
import micropython
import gc
from ssd1306 import SSD1306_I2C
from u8g2_font import Font
import framebuf

micropython.alloc_emergency_exception_buf(256)  # safer error text in IRQ

# ------------------------
# LCD config
# ------------------------
I2C_ADDR = 0x27
I2C_NUM_ROWS = 2
I2C_NUM_COLS = 16
use_I2C = False
use_OLED = True

if use_OLED:

    bt_icon_data_fg = bytearray([

        0b00000000, 0b00000000,
        0b00001000, 0b00000000,
        0b00001100, 0b00000000,
        0b00001010, 0b00000000,
        0b00101001, 0b00000000,
        0b00011110, 0b00000000,
        0b00011010, 0b00000000,
        0b00101001, 0b00000000,
        0b00001010, 0b00000000,
        0b00001100, 0b00000000,
        0b00001000, 0b00000000,
        0b00000000, 0b00000000,

    ])


    bt_icon_data_bg = bytearray([
        0b00011110, 0b00000000, #    *    
        0b00110111, 0b00000000, #    *    
        0b01110011, 0b10000000, #    **   
        0b01110101, 0b10000000, #    * *   
        0b01010110, 0b10000000, #  * **  
        0b01100001, 0b10000000, #   ***   
        0b01100101, 0b10000000, #   ***   
        0b01010110, 0b10000000, #  * * *  
        0b01110101, 0b10000000, #    **   
        0b01110011, 0b10000000, #    *    
        0b00110111, 0b00000000, #    *    
        0b00011110, 0b00000000  #
    ])


    icon_fg = framebuf.FrameBuffer(bt_icon_data_fg, 16, 12, framebuf.MONO_HLSB)
    icon_bg = framebuf.FrameBuffer(bt_icon_data_bg, 16, 12, framebuf.MONO_HLSB)
    
    i2c = I2C(0, scl=Pin(15), sda=Pin(16), freq=500_000)
    oled = SSD1306_I2C(128,64, i2c)
    font = Font('6x10_mf.u8f')

    oled.poweroff()
    oled.poweron()
    oled.fill(0)
    oled.show()
    oled.contrast(1)

    oled.show()

# ------------------------
# PWM (meters)
# ------------------------
frequency = 5000
m1_volt_pin = machine.Pin(6)
m1_volt_meter = PWM(m1_volt_pin)
m1_volt_meter.freq(frequency)

m2_volt_pin = machine.Pin(5)
m2_volt_meter = PWM(m2_volt_pin)
m2_volt_meter.freq(frequency)

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

# -------------
# Run the needle down gently
# -------------
def run_meter_down():
    pwm = m1_volt_meter.duty_u16()
    print(f"pwm={pwm}")
    while pwm > 32768:
        pwm -= 1000
        print(f"running down: {pwm}")
        m1_volt_meter.duty_u16(pwm)
        sleep(0.1)
    
    
    m1_volt_meter.duty_u16(int(32768))

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

        try:

            print(message)
            # Clamp and drive meter 1
            m1_val = message["meter"]["m1"]["v"] # type: ignore
            if m1_val is not None:
                m1_val = min(62000, int(m1_val))
                m1_volt_meter.duty_u16(m1_val)

            # Drive meter 2 if > 0
            m2_val = int(message["meter"]["m2"]["v"]) # type: ignore
            if m2_val > 0:
                m2_volt_meter.duty_u16(m2_val)

            if use_OLED:
                
                oled.fill(0)
                for i in range(3):
                    line = str(message["LCD"][str(i)]) # type: ignore
                    font.text(f"{line}", 0, (10*i)+10, 1, oled.hline)  # <- string first, then x,y, then hline
                
                rx_int = int(line.split(' ')[1])
                lag = abs(rx_int - packet_count)

                font.text(f"BRX: {packet_count:<7} L{lag}", 0, 40, 1, oled.hline)  # <- string first, then x,y, then hline
                font.text(f"CPU: {str(message['meta']['cpu'])}", 0, 50, 1, oled.hline ) # type: ignore
                
                oled.blit(icon_bg, 118, 52)
                oled.show()

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

    #oled.poweroff()

    try:
        ble = bluetooth.BLE()
        print(">>------------")
        sp = BLESimplePeripheral(ble, "pico2w")
        print("------------<<")
        
        mac = ble.config('mac')[1]
        mac_str = (':'.join('%02X' % b for b in mac))
        font.text(f"{mac_str}", 10, 62, 1, oled.hline)

        # Register on_write ONCE (BLESimplePeripheral queues it internally)
        sp.on_write(on_rx)
        icon = 0

        while True:
            if sp.is_connected():
                has_connected = True
                oled.blit(icon_bg, 118, 52)
                oled.show()
                icon = 0

                sleep(1)
                fail_count -= 1
                if fail_count < -10:
                    run_meter_down()

            else:
                in_failure += 1
                fail_count += 1
                sleep(1)
                if icon == 0:
                    oled.blit(icon_bg, 118, 52)
                    oled.show()
                    icon = 1
                else:
                    oled.blit(icon_fg, 118, 52)
                    oled.show()
                    icon = 0

                print(f"Not Connected Fail Count {fail_count}")
                if fail_count == 5:
                    run_meter_down()
    except KeyboardInterrupt:
        print("Ctrl-C")
        run_meter_down()
        oled.poweroff()
        sleep(0.1)
    finally:
        run_meter_down()
        oled.poweroff()
        print("Ctrl-C final")
