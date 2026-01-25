# test_main.py (ESP32 / MicroPython)
import time
from ble_simple_peripheral import BLESimplePeripheral  # <-- change to the filename that contains your class
import bluetooth

def on_rx(data: bytes):
    print("RX len:", len(data), "data:", data)

def main():
    ble = bluetooth.BLE()
    sp = BLESimplePeripheral(ble, name="ESP32S3-UART")  # name must match the PC script
    sp.on_write(on_rx)

    print("Ready. Waiting for central...")
    while True:
        # You can also periodically send something back if you like:
        # if sp.is_connected():
        #     sp.send(b"hello-from-esp")
        time.sleep(0.5)

if __name__ == "__main__":
    main()
