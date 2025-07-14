import board
import digitalio
import time
import usb_cdc

led = digitalio.DigitalInOut(board.D7)
led.direction = digitalio.Direction.OUTPUT
led.value = True

serial = usb_cdc.data
buffer = ""

while True:
    if serial.in_waiting > 0:
        incoming = serial.read(serial.in_waiting).decode('utf-8').strip().strip("\n")
        print("Received:", incoming)

        if incoming == "NOFLIGHT":
            print("No flight detected")
            led.value = False
        elif incoming == "ARRIVAL":  # Optional if you send status labels
            print("Flight arrived")
            led.value = True
        elif incoming == "DEPARTURE":
            print("Flight departed")
            led.value = True

    time.sleep(0.1)