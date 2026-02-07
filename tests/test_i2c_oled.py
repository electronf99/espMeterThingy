
# Import necessary modules
from machine import Pin, I2C, disable_irq, enable_irq

import micropython
from ssd1306 import SSD1306_I2C
from u8g2_font import Font

micropython.alloc_emergency_exception_buf(256)  # safer error text in IRQ

# ------------------------
# LCD config
# ------------------------
I2C_ADDR = 0x27
I2C_NUM_ROWS = 2
I2C_NUM_COLS = 16
use_I2C = False
use_OLED = True

# if use_I2C:
#     i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=1000000)
#     i2clcd = I2cLcd(i2c, I2C_ADDR, I2C_NUM_ROWS, I2C_NUM_COLS)
#     i2clcd.clear()
#     i2clcd.putstr("BT Listening..")

if use_OLED:
    i2c = I2C(0, scl=Pin(15), sda=Pin(16), freq=500_000)
    oled = SSD1306_I2C(128,64, i2c)
    font = Font('6x10_mf.u8f')

    oled.poweron()
    oled.fill(0)
    oled.show()
    oled.contrast(1)
    font.text(f"Hello World", 0, 20, 1, oled.hline)  # <- string first, then x,y, then hline
    oled.show()
    