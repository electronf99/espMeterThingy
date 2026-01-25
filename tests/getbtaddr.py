## Micropython Pico 2 and maybe others, get BT Mac Address
## David Peters

import bluetooth

ble = bluetooth.BLE()
ble.active(True)
mac = ble.config('mac')[1]
print(':'.join('%02X' % b for b in mac))