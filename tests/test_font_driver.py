from machine import Pin, I2C
from ssd1306 import SSD1306_I2C
from u8g2_font import Font

# Init display
i2c = I2C(0, scl=Pin(15), sda=Pin(16))  # adjust pins
oled = SSD1306_I2C(128, 64, i2c)

# Load a u8g2 font (file must be on the device)
font = Font('6x10_mn.u8f')

oled.fill(0)
oled.contrast(2)
font.text("123-", 0, 20, 1, oled.hline)  # <- string first, then x,y, then hline
oled.show()
