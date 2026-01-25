# Import necessary modules
from machine import PWM, Pin, I2C
import machine
import time


frequency = 5000
duty=32768

m1_dir = Pin(21, Pin.OUT)
m1_dir.value(1)
m1_volt_pin = machine.Pin(22)
m1_volt_meter = PWM(m1_volt_pin)
m1_volt_meter.freq(frequency)
print(duty)

dir=0
try:
    while 1==1:
        print(duty)
        m1_volt_meter.duty_u16(int(duty))
        print("*******************")

        time.sleep(0.1)
        print(duty)
        if(dir==0):
            duty += 200
        if(dir==-1):
            duty -= 200
        
        if duty > 60000:
            dir=-1
        if duty < 32800:
            dir=0
except KeyboardInterrupt:
    print("Ctrl-C Pressed")
finally:
    print("Setting to neutral")
    m1_volt_meter.duty_u16(32768)
    time.sleep(1)
    m1_volt_meter.duty_u16(32768)
