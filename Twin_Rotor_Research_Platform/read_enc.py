#!/usr/bin/env python3

import struct
import sys
import time

import serial


COMMAND_BYTE = b'\x63'
DATA_SIZE = 8


def read_encoder_values(ser):
    if ser.in_waiting:
        ser.reset_input_buffer()

    ser.write(COMMAND_BYTE)
    data = ser.read(DATA_SIZE)
    if len(data) != DATA_SIZE:
        return None

    return struct.unpack("<ii", data)


def main() -> None:
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyS0"
    baudrate = int(sys.argv[2]) if len(sys.argv) > 2 else 115200

    ser = serial.Serial(port, baudrate, timeout=1)
    print("Reading encoder values from {0} at {1} baud".format(port, baudrate))

    try:
        while True:
            values = read_encoder_values(ser)
            if values is None:
                print("No encoder response")
            else:
                encoder_1, encoder_2 = values
                print("Encoder1={0} Encoder2={1}".format(encoder_1, encoder_2))
            sys.stdout.flush()
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("Stopped")
    finally:
        ser.close()


if __name__ == "__main__":
    main()