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

import gc

# Define the LCD I2C address and dimensions
I2C_ADDR = 0x27
I2C_NUM_ROWS = 2
I2C_NUM_COLS = 16

# Run without I2C
use_I2C=False

# Initialize I2C and LCD objects
if use_I2C:
    i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=1000000)
    i2clcd = I2cLcd(i2c, I2C_ADDR, I2C_NUM_ROWS, I2C_NUM_COLS)
    i2clcd.clear()
    i2clcd.putstr("BT Listening..")

packet_count = 0

# Set PWM frequency
frequency = 5000

# Set up PWM Pin
m1_volt_pin = machine.Pin(6)
m1_volt_meter = PWM(m1_volt_pin)
m1_volt_meter.freq(frequency)

m2_volt_pin = machine.Pin(15)
m2_volt_meter = PWM(m2_volt_pin)
m2_volt_meter.freq(frequency)

displayed = 0

spinner = ['-', '\\', '|', '/']
spincount = 0

rx_packets = []

custom = get_arrow_chars()

fail_count=0
reboots = 0

if use_I2C:
    a=0
    for custom_char in custom:
        i2clcd.custom_char(a,custom_char)
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


# def restart_ble(ble, disconnect_handle=None, reinit_cb=None):
#     """Restart BLE stack.
#     ble: bluetooth.BLE() instance
#     disconnect_handle: optional conn handle to disconnect first
#     reinit_cb: callable to rebuild services/advertising after restart
#     """
#     try:
#         ble.gap_advertise(None)
#     except Exception:
#         pass

#     if disconnect_handle is not None:
#         try:
#             ble.gap_disconnect(disconnect_handle)
#         except Exception:
#             pass

#     ble.active(False)
#     time.sleep_ms(200)
#     ble.active(True)

#     if callable(reinit_cb):
#         reinit_cb(ble)



# def update_traffic(data):

#     global spincount
#     global reboots
    
#     LCDLine0 = ""
#     LCDLine1 = ""

#     try:
#         LCDLine0 = data['LCD']['0'][:15]
#         LCDLine1 = data['LCD']['1'][:15]
    
#         #moving_iron_volts = data["meter"]["m1"]["v"]
#         moving_iron_volts = min(62000, data["meter"]["m1"]["v"])
#         m1_volt_meter.duty_u16(int(moving_iron_volts))
#         m2_volts = data["meter"]["m2"]["v"]
#         if m2_volts > 0:
#             m2_volt_meter.duty_u16(int(m2_volts))
#     except Exception as e:
#         print(e)

#     if use_I2C:
#         i2clcd.move_to(0,0)
#         i2clcd.putstr(LCDLine0)
#         i2clcd.move_to(0,1)
#         i2clcd.putstr(LCDLine1)
#         i2clcd.move_to(10,1)
#         i2clcd.putstr(f"B:{str(reboots)}")
        
#         i2clcd.move_to(15,1)
#         i2clcd.putstr(chr(spincount))
        
#     spincount += 1
#     spincount = spincount % 8


# Define a callback function to handle received data
def on_rx(data):

    global rx_packets
    global fail_count
    
    global packet_count
    #sleep(1)

    seq, total_packets, msg_id = data[0], data[1], data[2]  # noqa: F841
    if(seq==0):
        rx_packets = []
    
    payload = data[3:].rstrip(b"\x00")
    rx_packets.append(payload)
    print(payload)    
    if( total_packets == seq + 1):
        packet_count += 1
        full_payload = b""
        for packet in rx_packets:
            full_payload = full_payload + packet

        
        message = decode(full_payload)
        
        # update_traffic(message)
        fail_count = 0

# def run_meter_down():
#     pwm = m1_volt_meter.duty_u16()
#     print(f"pwm={pwm}")
#     while pwm > 32768:
#         print(f"shutting down: {pwm}")
#         pwm -= 1000
#         m1_volt_meter.duty_u16()
#         sleep(0.1)
    
#     m1_volt_meter.duty_u16(int(32768))


# def get_reboot_counter():

#     file_path = "reboots.txt"

#     # Read current value (default to 0 if file or content is invalid)
#     try:
#         with open(file_path, "r") as f:
#             first_line = f.readline().strip()
#             current = int(first_line) if first_line else 0
#     except (OSError, ValueError):
#         current = 0

#     return current

# def update_reboot_counter():

#     file_path = "reboots.txt"

#     # Read current value (default to 0 if file or content is invalid)
#     try:
#         with open(file_path, "r") as f:
#             first_line = f.readline().strip()
#             current = int(first_line) if first_line else 0
#     except (OSError, ValueError):
#         current = 0

#     # Increment
#     current += 1

#     # Write back (overwrite the whole file)
#     with open(file_path, "w") as f:
#         f.write(str(current) + "\n")


if __name__ == "__main__":
    in_failure = 0
    has_connected = False
    
    # reboots = get_reboot_counter()

    try:
        # Create a Bluetooth Low Energy (BLE) object
        ble = bluetooth.BLE()
        print(">>------------")
        sp = BLESimplePeripheral(ble, "pico2w")
        print("------------<<")
        heap_free_hwm = gc.mem_free()

        # Start an infinite loop
        while True:
            if sp.is_connected():  # Check if a BLE connection is established
                sp.on_write(on_rx)  # Set the callback function for data reception
                has_connected = True
                sleep(1)
                heap_free_hwm = min(heap_free_hwm, gc.mem_free())
               
                print(f"PC {packet_count} FC {fail_count} | Free Mem: {gc.mem_free()} | " 
                      f"USED: {gc.mem_alloc()} | "
                      f"HWM: {min(heap_free_hwm, gc.mem_free())} | ",
                      end="")


                print(f"In Connected Loop. Fail Count = {fail_count}") 
                fail_count -= 1
                # if fail_count <= -5:
                #     if use_I2C:
                #         i2clcd.move_to(0,1)
                #         i2clcd.putstr(f"Shutting down after {fail_count}")
                    
                #     update_reboot_counter()
                    
                #     run_meter_down()
                #     sleep(1)
                #     machine.reset()
                    

                
            else:
                in_failure += 1
                fail_count += 1
                sleep(1)
                heap_free_hwm = min(heap_free_hwm, gc.mem_free())
               
                print(f"FC {fail_count} | Free Mem: {gc.mem_free()} | " 
                      f"USED: {gc.mem_alloc()} | "
                      f"HWM: {min(heap_free_hwm, gc.mem_free())} | ",
                      end="")



                print(f"Not Connected Fail Count {fail_count}")
                if use_I2C:
                    i2clcd.move_to(0,1)
                    i2clcd.putstr(f"NC:{str(fail_count)}{' '*16}")

                # if fail_count >= 3 and has_connected and in_failure > 5:
                #     run_meter_down()
                #     machine.reset()

    except KeyboardInterrupt:
        print("Ctrl-c")
        # run_meter_down()
        sleep(0.1)
    finally:
        print("Ctrl-c final")
        # run_meter_down()

            # m1_volt_meter.duty_u16(int(32768))
