# I2C Scanner MicroPython
from machine import Pin, SoftI2C
from pico_i2c_lcd import I2cLcd

# You can choose any other combination of I2C pins
i2c = SoftI2C(scl=Pin(8), sda=Pin(7), freq=500_000)

print('I2C SCANNER')
devices = i2c.scan()

if len(devices) == 0:
  print("No i2c device !")
else:
  print('i2c devices found:', len(devices))

  for device in devices:
    print("I2C hexadecimal address: ", hex(device))

lcd = I2cLcd(i2c, 0x27, 2, 16)
lcd.putstr("Hello World")