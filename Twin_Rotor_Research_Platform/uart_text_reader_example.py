#!/usr/bin/env python3

import serial
import sys
import time


def main() -> None:
    if len(sys.argv) > 1:
        port = sys.argv[1]
    else:
        port = "/dev/ttyS0"

    if len(sys.argv) > 2:
        baudrate = int(sys.argv[2])
    else:
        baudrate = 115200

    ser = serial.Serial(port, baudrate, timeout=1)

    print("Listening for STM32 UART messages on {0} at {1} baud".format(port, baudrate))

    try:
        while True:
            data = ser.readline()
            if not data:
                continue

            line = data.decode("utf-8", "replace").rstrip("\r\n")

            print("STM32: {0}".format(line))
            sys.stdout.flush()
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("Stopped")
    finally:
        ser.close()


if __name__ == "__main__":
    main()

