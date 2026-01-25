
# main.py — ESP32‑S3 MicroPython BLE peripheral that prints incoming data
import bluetooth
from micropython import const
import utime

# UUIDs for a simple UART-like service
_UART_SERVICE_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DC4179")
_UART_RX_UUID      = bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DC4179")  # PC -> ESP (Write)
_UART_TX_UUID      = bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DC4179")  # ESP -> PC (Notify, unused here)

_FLAG_READ   = const(0x0002)
_FLAG_WRITE  = const(0x0008)
_FLAG_NOTIFY = const(0x0010)

ble = bluetooth.BLE()
ble.active(True)

# Preferred MTU for ATT exchange (final MTU = min(local, remote))
ble.config(mtu=247)  # 247 is common; payload up to 244 bytes when negotiated
# (Final size depends on what the PC/OS accepts)  # [1](https://docs.micropython.org/en/latest/library/bluetooth.html)

# GATT database
UART_RX = (_UART_RX_UUID, _FLAG_WRITE)
UART_TX = (_UART_TX_UUID, _FLAG_NOTIFY | _FLAG_READ)
UART_SERVICE = (_UART_SERVICE_UUID, (UART_TX, UART_RX))
services = (UART_SERVICE, )

((tx_handle, rx_handle),) = ble.gatts_register_services(services)

# Allow long writes to RX (growable buffer, e.g. 512 bytes)
ble.gatts_set_buffer(rx_handle, 512, True)  # required to go beyond 20 bytes  # [1](https://docs.micropython.org/en/latest/library/bluetooth.html)[2](https://github.com/orgs/micropython/discussions/11945)

_connected = False
_name = "ESP32S3-UART"

def _irq(event, data):
    global _connected
    if event == 1:   # _IRQ_CENTRAL_CONNECT
        _connected = True
    elif event == 2: # _IRQ_CENTRAL_DISCONNECT
        _connected = False
        # Resume advertising so the PC can reconnect
        ble.gap_advertise(250_000, adv_payload(_name))
    elif event == 3: # _IRQ_GATTS_WRITE
        conn_handle, attr_handle = data
        if attr_handle == rx_handle:
            # Read whatever was written this time and print it
            msg = ble.gatts_read(rx_handle)
            if msg:
                print("RX:", msg)
                # Clear the value so the next write reads fresh data
                ble.gatts_write(rx_handle, b"")

def adv_payload(name: str) -> bytes:
    name_b = name.encode()
    # Flags + Complete Local Name
    return b"\x02\x01\x06" + bytes((len(name_b) + 1, 0x09)) + name_b

ble.irq(_irq)
ble.gap_advertise(250_000, adv_payload(_name))  # slow, connectable advertising

# Keep main alive; all printing happens in the IRQ above.
while True:
    utime.sleep_ms(500)
