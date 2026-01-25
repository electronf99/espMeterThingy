
import time
import bluetooth
from ble_advertising import advertising_payload
from micropython import const

_IRQ_CENTRAL_CONNECT     = const(1)
_IRQ_CENTRAL_DISCONNECT  = const(2)
_IRQ_GATTS_WRITE         = const(3)
_IRQ_MTU_EXCHANGED       = const(21)

_FLAG_READ               = const(0x0002)
_FLAG_WRITE_NO_RESPONSE  = const(0x0004)
_FLAG_WRITE              = const(0x0008)
_FLAG_NOTIFY             = const(0x0010)

_UART_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
_UART_TX   = (bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E"),
              _FLAG_READ | _FLAG_NOTIFY)
_UART_RX   = (bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E"),
              _FLAG_WRITE | _FLAG_WRITE_NO_RESPONSE)
_UART_SERVICE = (_UART_UUID, (_UART_TX, _UART_RX))

class BLESimplePeripheral:
    def __init__(self, ble, name="mpy-uart"):
        print("-----------------------------------------------------------------")
        self._ble = ble
        self._ble.active(True)
        # Give controller a moment before first advertise (helps on some builds)
        time.sleep_ms(100)

        # Preferred ATT MTU = 200 (final is min(local, remote)); payload per PDU = 197 bytes
        self._ble.config(mtu=200)

        self._ble.irq(self._irq)

        ((self._handle_tx, self._handle_rx),) = self._ble.gatts_register_services(
            (_UART_SERVICE,)
        )
        # Allow long writes to RX
        self._ble.gatts_set_buffer(self._handle_rx, 512, True)

        self._connections = set()
        self._write_callback = None

        # IMPORTANT: split payload into adv_data (small) and resp_data (UUIDs)
        # Keep adv name short to stay under 31 bytes.
        self._adv_data  = advertising_payload(name=name[:15])  # short name
        self._resp_data = advertising_payload(services=[_UART_UUID])

        # Debug lengths to confirm we’re under the limits
        print("adv len:", len(self._adv_data), "scan resp len:", len(self._resp_data))

        self._advertise()

    def _irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, _, _ = data
            print("New connection", conn_handle)
            self._connections.add(conn_handle)

        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn_handle, _, _ = data
            print("Disconnected", conn_handle)
            self._connections.discard(conn_handle)
            self._advertise()

        elif event == _IRQ_MTU_EXCHANGED:
            conn_handle, mtu = data
            print("Negotiated ATT MTU:", mtu, "ATT payload =", mtu - 3)

        elif event == _IRQ_GATTS_WRITE:
            conn_handle, value_handle = data
            if value_handle == self._handle_rx:
                value = self._ble.gatts_read(value_handle)
                if self._write_callback:
                    self._write_callback(value)
                self._ble.gatts_write(self._handle_rx, b"")

    def send(self, data: bytes):
        for conn_handle in tuple(self._connections):
            self._ble.gatts_notify(conn_handle, self._handle_tx, data)

    def is_connected(self):
        return len(self._connections) > 0

    def _advertise(self, interval_us=500_000):
        print("Starting advertising")
        print("-----------------------------------------------------------------")
        # If already advertising, stop first (defensive; safe to call)
        try:
            self._ble.gap_advertise(None)
        except Exception:
            pass
        # Use both adv_data and resp_data to avoid 31‑byte overflow
        self._ble.gap_advertise(interval_us, adv_data=self._adv_data, resp_data=self._resp_data)

    def on_write(self, callback):
        self._write_callback = callback
