import serial


class UART_Text_Reader:
    def __init__(
        self,
        port="/dev/ttyS0",
        baudrate=9600,
        timeout=1.0,
        ser=None,
    ):
        self._owns_serial = ser is None
        self.ser = ser if ser is not None else serial.Serial(port, baudrate, timeout=timeout)

    def __del__(self):
        if self._owns_serial and getattr(self, "ser", None) is not None:
            self.ser.close()

    def read_line(self):
        data = self.ser.readline()
        if not data:
            return None
        try:
            return data.decode("utf-8", "replace").rstrip("\r\n")
        except AttributeError:
            return data.rstrip("\r\n")

