import os
import sys
import math
import time
import struct
import csv
import threading
from collections import deque, defaultdict
from abc import ABC, abstractmethod
from typing import Tuple, List, Dict, Optional, Callable, Iterable

# Try importing serial and can (hardware communication libraries)
try:
    import serial
except ImportError:
    serial = None

try:
    import can
except ImportError:
    can = None

# Try importing IMU hardware libraries
try:
    import board
    import adafruit_icm20x
    HAS_IMU_HARDWARE = True
except ImportError:
    HAS_IMU_HARDWARE = False

# Try importing PyQt5 and pyqtgraph
try:
    from PyQt5 import QtWidgets, QtCore, QtGui
    import pyqtgraph as pg
    HAS_GUI = True
except ImportError:
    HAS_GUI = False

# Try importing numpy
try:
    import numpy as np
except ImportError:
    np = None

# Try importing matplotlib
try:
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# Try importing filterpy
try:
    from filterpy.kalman import KalmanFilter
except ImportError:
    KalmanFilter = None


# =====================================================================
# MODULE: pid_lib
# =====================================================================
class PID:
    """
    PID controller
    """
    def __init__(self, Kp: float, Ki: float, Kd: float, limits: Tuple[float, float], derivative_filter_omega: float = float('inf'), derivative_on_measurement: bool = False):
        """
        limits - Limits on the output of the PID controller based on the limits of the inputs of the control system. Tuple of floats (a,b) where a <= b
        derivative_filter_omega = omega for low pass derivative filter on derivative make sure it is larger than half the average sampling time 
        derivative_on_measurement = Enable derivative on measurement instead of error
        """
        self._Kp = Kp
        self._Ki = Ki
        self._Kd = Kd

        self._derivative_filter_omega = derivative_filter_omega
        self._tau = 1.0 / self._derivative_filter_omega if self._derivative_filter_omega != 0 else float('inf')
        self._derivative_on_measurement = derivative_on_measurement
        self._limits = limits
        assert(self._limits[0] <= self._limits[1])

        self._set_point = 0.0

        self._pre_i = 0.0
        self._pre_d = 0.0
        self._pre_e = 0.0
        self._pre_measurement = 0.0

    def set_set_point(self, set_point: float):
        self._set_point = set_point

    @property
    def parameteres(self):
        return (self._Kp, self._Ki, self._Kd, self._derivative_filter_omega)

    def set_parameteres(self, Kp: float, Ki: float, Kd: float):
        self._Kp = Kp
        self._Ki = Ki
        self._Kd = Kd

    def clamp(self, val):
        """
        clamp the value between the limits
        """
        if val < self._limits[0]:
            return self._limits[0]
        if val > self._limits[1]:
            return self._limits[1]
        return val

    def get_val(self, measurement: float, time_delta: float):
        """
        p[n] = K_p*e[n]
        i[n] = (Ki*T/2)*(e[n]+e[n-1])+i[n-1]
        d[n] = (2*Kd)/(2*tau+T)*(e[n]-e[n-1])+(2*tau-T)/(2*tau+T)*d[n-1]
        """
        e = self._set_point - measurement # error
        T = time_delta 
        tau = self._tau if (self._tau * 2 > T) else T / 2

        # Proportional 
        p = self._Kp * e

        # Integral
        i = (self._Ki * T) / 2 * (e + self._pre_e) + self._pre_i

        # derivative with low pass
        d = (2 * self._Kd) / (2 * tau + T) * (e - self._pre_e) + (2 * tau - T) / (2 * tau + T) * self._pre_d

        if self._derivative_on_measurement:
            # derivative on measurement with low pass
            d = (2 * self._Kd) / (2 * tau + T) * (-(measurement - self._pre_measurement)) + (2 * tau - T) / (2 * tau + T) * self._pre_d

        output = p + i + d

        self._pre_i = i
        self._pre_d = d 
        self._pre_e = e
        self._pre_measurement = measurement

        return self.clamp(output)

    def __call__(self, measurement: float, time_delta: float):
        """
        Return the calculated control value
        """
        return self.get_val(measurement, time_delta)


# =====================================================================
# MODULE: motor_driver
# =====================================================================
class Motor:
    CONVERSION_FACTOR = 0.01 # dps/LSB
    
    def __init__(self):
        # M0 CAN ID
        self.motor0ID = 0x141
        # M1 CAN ID
        self.motor1ID = 0x142
        # Speed control command ID
        self.speedControlCommandID = 0xA2
        # Motor off command ID
        self.motorOffID = 0x80
        # Motor stop command ID
        self.motorStopID = 0x81
        # Motor run command ID
        self.motoRunID = 0x88

        # SocketCAN initialization (specific to Linux/Raspberry Pi)
        try:
            os.system('sudo ip link set can0 type can bitrate 1000000')
            os.system('sudo ifconfig can0 up')
        except Exception as e:
            print(f"Warning: Could not configure can0 interface: {e}")

        try:
            if can is not None:
                self.can0 = can.interface.Bus(channel='can0', bustype='socketcan') # type: ignore
            else:
                self.can0 = None
                print("Warning: python-can is not installed. CAN communication disabled.")
        except Exception as e:
            print(f"Warning: Could not open CAN bus: {e}")
            self.can0 = None

        self.set_speed_M0(0)
        self.set_speed_M1(0)

    def __del__(self):
        print("Shutting down motors")
        try:
            self._speedControlM1(0)
            self._speedControlM0(0)
            self.stop()
        except Exception:
            pass
        
        if hasattr(self, 'can0') and self.can0 is not None:
            try:
                self.can0.shutdown()
            except Exception:
                pass
        try:
            os.system('sudo ifconfig can0 down')
        except Exception:
            pass

    @classmethod
    def _convert_speed(cls, speed):
        speed_dps = speed * 360 / 60
        raw_speed = speed_dps / 0.01
        return int(raw_speed)

    def stop(self):
        self.stopM0()
        self.stopM1()

    def set_speed(self, m0_speed_rpm, m1_speed_rpm):
        self.set_speed_M0(m0_speed_rpm)
        self.set_speed_M1(m1_speed_rpm)

    def set_speed_M0(self, speed_rpm):
        self._speedControlM0(self._convert_speed(speed_rpm))

    def set_speed_M1(self, speed_rpm):
        self._speedControlM1(self._convert_speed(speed_rpm))

    def _speedControlM0(self, speed):
        byte1 = speed & 0xFF
        byte2 = (speed & 0xFF00) >> 8
        byte3 = (speed & 0xFF0000) >> 16
        byte4 = (speed & 0xFF000000) >> 24

        msg = None
        if can is not None:
            msg = can.Message(arbitration_id=self.motor0ID, data=[self.speedControlCommandID, 0, 0, 0, byte1, byte2, byte3, byte4], is_extended_id=False)
        if msg is not None and self.can0 is not None:
            try:
                self.can0.send(msg)
            except Exception:
                pass

    def _speedControlM1(self, speed):
        byte1 = speed & 0xFF
        byte2 = (speed & 0xFF00) >> 8
        byte3 = (speed & 0xFF0000) >> 16
        byte4 = (speed & 0xFF000000) >> 24

        msg = None
        if can is not None:
            msg = can.Message(arbitration_id=self.motor1ID, data=[self.speedControlCommandID, 0, 0, 0, byte1, byte2, byte3, byte4], is_extended_id=False)
        if msg is not None and self.can0 is not None:
            try:
                self.can0.send(msg)
            except Exception:
                pass

    def turnOffM0(self):
        msg = None
        if can is not None:
            msg = can.Message(arbitration_id=self.motor0ID, data=[self.motorOffID, 0, 0, 0, 0, 0, 0, 0], is_extended_id=False)
        if msg is not None and self.can0 is not None:
            try:
                self.can0.send(msg)
            except Exception:
                pass

    def turnOffM1(self):
        msg = None
        if can is not None:
            msg = can.Message(arbitration_id=self.motor1ID, data=[self.motorOffID, 0, 0, 0, 0, 0, 0, 0], is_extended_id=False)
        if msg is not None and self.can0 is not None:
            try:
                self.can0.send(msg)
            except Exception:
                pass

    def stopM0(self):
        msg = None
        if can is not None:
            msg = can.Message(arbitration_id=self.motor0ID, data=[self.motorStopID, 0, 0, 0, 0, 0, 0, 0], is_extended_id=False)
        if msg is not None and self.can0 is not None:
            try:
                self.can0.send(msg)
            except Exception:
                pass

    def stopM1(self):
        msg = None
        if can is not None:
            msg = can.Message(arbitration_id=self.motor1ID, data=[self.motorStopID, 0, 0, 0, 0, 0, 0, 0], is_extended_id=False)
        if msg is not None and self.can0 is not None:
            try:
                self.can0.send(msg)
            except Exception:
                pass

    def runM0(self):
        msg = None
        if can is not None:
            msg = can.Message(arbitration_id=self.motor0ID, data=[self.motoRunID, 0, 0, 0, 0, 0, 0, 0], is_extended_id=False)
        if msg is not None and self.can0 is not None:
            try:
                self.can0.send(msg)
            except Exception:
                pass

    def runM1(self):
        msg = None
        if can is not None:
            msg = can.Message(arbitration_id=self.motor1ID, data=[self.motoRunID, 0, 0, 0, 0, 0, 0, 0], is_extended_id=False)
        if msg is not None and self.can0 is not None:
            try:
                self.can0.send(msg)
            except Exception:
                pass


# =====================================================================
# MODULE: encoder
# =====================================================================
class Encoder:
    COMMAND_BYTE = b'\x63' 
    DATA_SIZE = 8 

    def __init__(self, ser) -> None:
        self._ser = ser
        self._encoder_1 = 0
        self._encoder_2 = 0
        self._zero_point_1 = 0
        self._zero_point_2 = 0

    def wait_until_ready(self):
        """
        Blocks until the system is ready
        """
        while True:
            data = self._get_data()
            if data is not None:
                break
            print("STM32 Not Ready yet")
            time.sleep(1)

    def set_zero_point(self, zero_point1, zero_point2):
        self._zero_point_1 = zero_point1
        self._zero_point_2 = zero_point2

    def set_current_to_zero_point(self):
        self.update()
        self._zero_point_1, self._zero_point_2 = self._encoder_1, self._encoder_2

    def _get_data(self) -> Optional[Tuple[int, int]]:
        """
        queries the encoders and gets the data. Returns a tuple of ints
        if unable to acquire within the timeout, returns None
        """
        if self._ser is None:
            return None
        try:
            if self._ser.in_waiting:
                self._ser.flushInput()
            self._ser.write(self.COMMAND_BYTE)
            read_val = self._ser.read(self.DATA_SIZE)
            if len(read_val) != 8:
                return None
            return struct.unpack('<ii', read_val)
        except Exception:
            return None

    @property
    def encoder1(self):
        """
        value of encoder1 after last update
        """
        return self._encoder_1 - self._zero_point_1

    @property
    def encoder2(self):
        """
        value of encoder2 after last update
        """
        return self._encoder_2 - self._zero_point_2
    
    def update(self):
        """
        updates the internally stored encoder values
        returns True on success, False otherwise
        """
        data = self._get_data()
        if data is None:
            return False
        self._encoder_1, self._encoder_2 = data
        return True

    def __str__(self):
        return f"Encoder1={self.encoder1} Encoder2={self.encoder2}"
    
    def __repr__(self):
        return self.__str__()


# =====================================================================
# MODULE: IMU_lib
# =====================================================================
class IMU:
    def __init__(self, address=0x69):
        if HAS_IMU_HARDWARE:
            try:
                self._i2c = board.I2C() # type: ignore
                self._icm = adafruit_icm20x.ICM20948(self._i2c, address=address) # type: ignore
                self._acceleration = self._icm.acceleration
                self._gyro = self._icm.gyro
                self._mag = self._icm.magnetic
                return
            except Exception as e:
                print(f"Warning: Failed to initialize IMU hardware: {e}")
        
        # Fallback dummy values
        self._acceleration = (0.0, 0.0, 9.81)
        self._gyro = (0.0, 0.0, 0.0)
        self._mag = (0.0, 0.0, 0.0)

    @property
    def acceleration(self):
        return self._acceleration
    
    @property
    def magnetic(self):
        return self._mag
    
    @property
    def gyro(self):
        return self._gyro

    def update(self):
        if HAS_IMU_HARDWARE and hasattr(self, '_icm'):
            try:
                self._acceleration = self._icm.acceleration
                self._gyro = self._icm.gyro
                self._mag = self._icm.magnetic
            except Exception:
                pass

    @property
    def simple_pitch_from_g_fusion(self):
        """
        simply finding the pitch using atan2(x,z)
        """
        x, y, z = self.acceleration
        val = math.atan2(x, z)
        return val

    def acceleration_string(self):
        return f"acc.x={self.acceleration[0]} acc.y={self.acceleration[1]} acc.z={self.acceleration[2]}"

    def gyro_string(self):
        return f"gyro.x={self.gyro[0]} gyro.y={self.gyro[1]} gyro.z={self.gyro[2]}"

    def __str__(self):
        return f"{self.acceleration_string()} {self.gyro_string()}"

    def __repr__(self):
        return self.__str__()


# =====================================================================
# MODULE: twin_rotor
# =====================================================================
class Twin_Rotor:
    __RUNNING_CODE = b'\x65'
    __ERROR_CODE = b'\x66'
    __STANDBY_CODE = b'\x64'

    def __init__(self, timer_function: Optional[Callable[[], float]] = None):
        """
        timer_function : function used to time updates. If None, time.monotonic is used
        """
        self.motors = Motor()
        try:
            if serial is not None:
                self.ser = serial.Serial('/dev/ttyS0', 9600, timeout=1)
            else:
                self.ser = None
                print("Warning: pyserial is not installed. Serial communication disabled.")
        except Exception as e:
            print(f"Warning: Could not open serial port /dev/ttyS0: {e}")
            self.ser = None

        self.encoder = Encoder(self.ser)
        if self.ser:
            try:
                self.encoder.wait_until_ready()
            except Exception:
                pass
        self.imu = IMU()

        self._init_time = time.monotonic()
        self.timer_function: Callable[[], float] = self.default_timer_function

        if timer_function is not None:
            self.timer_function = timer_function

        self._time: float = self.timer_function()
        if self.ser:
            try:
                self.encoder._get_data()
                self.encoder.set_current_to_zero_point()
                self.__set_running()
            except Exception:
                pass

    def __del__(self):
        try:
            self.__set_standby()
        except Exception:
            pass
        if hasattr(self, 'ser') and self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass

    def default_timer_function(self) -> float:
        return time.monotonic() - self._init_time

    def stop(self):
        self.motors.stop()

    def update_readings(self) -> float:
        """
        updates the readings for imu and encoder and sets the update time
        returns the time delta 
        """
        self.imu.update()
        self.encoder.update()
        ct = self.timer_function()
        pt = self._time
        self._time = ct
        return (ct - pt)

    @property
    def time_of_last_update(self):
        return self._time

    def __str__(self):
        return f"t={self.time_of_last_update:.4f} {self.encoder} {self.imu}"

    def __set_led(self, command):
        if self.ser:
            try:
                self.ser.write(command)
            except Exception:
                pass

    def __set_running(self):
        self.__set_led(self.__RUNNING_CODE)

    def __set_error(self):
        self.__set_led(self.__ERROR_CODE)

    def __set_standby(self):
        self.__set_led(self.__STANDBY_CODE)

    def show_error(self):
        self.__set_error()


# =====================================================================
# MODULE: data_buffers
# =====================================================================
class Buffer:
    def __init__(self, size: int):
        self._buffer = deque((0.0 for _ in range(size)), maxlen=size)
        self._size = size
    
    def push(self, val: float):
        """
        push new values to the buffer
        """
        self._buffer.append(val)

    @property
    def data(self):
        """
        get data as a deque of floats
        """
        return self._buffer

    @property
    def numpy_data(self):
        if np is not None:
            return np.array(self._buffer)
        return list(self._buffer)


class Data_Buffers:
    def __init__(self, size: int):
        """
        create data buffers to store the twin rotor data.
        size is how much data the buffer stores.
        """
        self._size = size
        self.time = Buffer(size)
        self.encoder1 = Buffer(size)
        self.acc_x = Buffer(size)
        self.acc_y = Buffer(size)
        self.acc_z = Buffer(size)
        self.gyro_x = Buffer(size)
        self.gyro_y = Buffer(size)
        self.gyro_z = Buffer(size)
        self.mag_x = Buffer(size)
        self.mag_y = Buffer(size)
        self.mag_z = Buffer(size)
        self.lock = threading.Lock()

    def update_buffers(self, twin_rotor: Twin_Rotor):
        self.lock.acquire()
        self.time.push(twin_rotor.time_of_last_update)
        self.encoder1.push(twin_rotor.encoder.encoder1)
        self.acc_x.push(twin_rotor.imu.acceleration[0])
        self.acc_y.push(twin_rotor.imu.acceleration[1])
        self.acc_z.push(twin_rotor.imu.acceleration[2])
        self.gyro_x.push(twin_rotor.imu.gyro[0])
        self.gyro_y.push(twin_rotor.imu.gyro[1])
        self.gyro_z.push(twin_rotor.imu.gyro[2])
        self.mag_x.push(twin_rotor.imu.magnetic[0])
        self.mag_y.push(twin_rotor.imu.magnetic[1])
        self.mag_z.push(twin_rotor.imu.magnetic[2])
        self.lock.release()

    def get_custom_buffer(self):
        return Custom_Buffer(self)


class Custom_Buffer(Buffer):
    def __init__(self, data_buffers: Data_Buffers):
        super().__init__(data_buffers._size)
        self.lock = threading.Lock()

    def push(self, val: float):
        self.lock.acquire()
        super().push(val)
        self.lock.release()

    @property
    def data(self):
        self.lock.acquire()
        ret = self._buffer.copy()
        self.lock.release()
        return ret

    @property
    def numpy_data(self):
        self.lock.acquire()
        if np is not None:
            ret = np.array(self._buffer)
        else:
            ret = list(self._buffer)
        self.lock.release()
        return ret


# =====================================================================
# MODULE: data_logger
# =====================================================================
class Logger(ABC):
    @abstractmethod
    def write(self, str_val: str):
        ...

    def writeln(self, str_val: str):
        self.write(f"{str_val}\n")


class Print_Logger(Logger):
    """
    Simple Logger to print to standard out
    """
    def write(self, str_val: str):
        print(str_val, end='')


class File_Logger(Logger):
    def __init__(self, file_path: str, mode: str = 'w'):
        """
        file_path : path to file
        mode: 'a' to append or 'w' to overwrite
        """
        if mode not in {'a', 'w'}:
            raise Exception("mode must be either a or w")
        self.file_path = file_path
        self.file = open(self.file_path, mode)

    def write(self, str_val: str):
        self.file.write(str_val)

    def __del__(self):
        if hasattr(self, 'file') and not self.file.closed:
            self.file.close()


# Protocol fallback
try:
    from typing import Protocol
except ImportError:
    Protocol = object # type: ignore


class Twin_Rotor_Logger(Protocol):
    def log(self, twin_rotor: Twin_Rotor) -> None:
        ...


class Simple_Logger(Twin_Rotor_Logger):
    """
    Can provide any Logging Function, by default it logs in human readable format.
    writes each log entry on a new line
    """
    def __init__(self, data_logger: Logger, logging_func: Optional[Callable[[Twin_Rotor], str]] = None):
        self.data_logger = data_logger
        self.logging_function = self.basic_logging 
        if logging_func is not None:
            self.logging_function = logging_func

    @staticmethod
    def basic_logging(twin_rotor: Twin_Rotor):
        return str(twin_rotor)

    def log(self, twin_rotor: Twin_Rotor):
        self.data_logger.writeln(self.logging_function(twin_rotor))


class CSV_Logger(Twin_Rotor_Logger):
    """
    Logs data as a csv file
    """
    def __init__(self, file_path: str, append=False):
        """
        file_path:str : path to the csv file if a file is not found it will be created
        append:bool   : whether to append to a file or overwrite
        """
        mode = 'a' if append else 'w'
        self._file = open(file_path, mode, newline='')
        self._writer = csv.writer(self._file)
        header = ['time', 'encoder1', 'encoder2', 'acc.x', 'acc.y', 'acc.z', 'gyro.x', 'gyro.y', 'gyro.z']
        if not append:
            self._writer.writerow(header)

    def __del__(self):
        if hasattr(self, '_file') and not self._file.closed:
            self._file.close()

    def log(self, twin_rotor: Twin_Rotor):
        data = [
            twin_rotor.time_of_last_update,
            twin_rotor.encoder.encoder1,
            twin_rotor.encoder.encoder2,
            *twin_rotor.imu.acceleration,
            *twin_rotor.imu.gyro
        ]
        self._writer.writerow(data)


# =====================================================================
# MODULE: data_plotter (PyQt5 GUI)
# =====================================================================
class Colors:
    ORISE_YELLOW  = (251, 170, 29)
    ORISE_ORANGE  = (242, 107, 36)
    WHITE = (255, 255, 255)


class READING_NAMES:
    """
    available readings in the data buffer
    """
    ENCODER1 = "encoder1"
    ACC_X  = "acc_x"
    ACC_Y = "acc_y"
    ACC_Z = "acc_z"
    GYRO_X = "gyro_x"
    GYRO_Y = "gyro_y"
    GYRO_Z = "gyro_z"
    MAG_X = "mag_x"
    MAG_Y = "mag_y"
    MAG_Z = "mag_z"


if HAS_GUI:
    class Graph_Window(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.main_layout = QtWidgets.QVBoxLayout()
            self.plot_widgets: List[pg.PlotWidget] = []
            self.setLayout(self.main_layout)
            self.plots: List[pg.PlotDataItem] = []
            self.update_functions: List[Callable[[Data_Buffers], Iterable[float]]] = []

        def add_time_graph(self, title: str, *buffer_data_func: Callable[[Data_Buffers], Iterable[float]], colors, names):
            self.plot_widgets.append(pg.PlotWidget())
            self.plot_widgets[-1].getPlotItem().showGrid(True, True) # type: ignore
            self.plot_widgets[-1].getPlotItem().setTitle(title, color=Colors.WHITE) # type: ignore
            legend = self.plot_widgets[-1].getPlotItem().addLegend(labelTextColor=Colors.WHITE) # type: ignore
            for func, color, name in zip(buffer_data_func, colors, names):
                self.plots.append(self.plot_widgets[-1].plot(pen=pg.mkPen(color=color)))
                if name is not None:
                    legend.addItem(self.plots[-1], name)
                self.update_functions.append(func)
            self.main_layout.addWidget(self.plot_widgets[-1])
            return self.plot_widgets[-1], self.plots[-1]

        def update(self, data_buffer: Data_Buffers):
            for plot, update_function in zip(self.plots, self.update_functions):
                data = update_function(data_buffer)
                plot.setData(data_buffer.time.data, data)


    class Main_Window(QtWidgets.QMainWindow):
        def __init__(self, update_interval: int, data_buffers: Data_Buffers, *args, **kwargs):
            super(Main_Window, self).__init__(*args, **kwargs)
            self.main_widget = QtWidgets.QWidget()
            self.setCentralWidget(self.main_widget)
            self.main_layout = QtWidgets.QVBoxLayout()
            self.main_widget.setLayout(self.main_layout)
            self.setWindowTitle("Orise Twin Rotor")

            self.label = QtWidgets.QLabel()
            
            # Dynamic path resolution for logo/slider asset
            possible_paths = [
                os.path.join(os.path.dirname(__file__), "Library/src/Orise_Twin_Rotor/assets/orise_slider.png"),
                os.path.join(os.path.dirname(__file__), "assets/orise_slider.png"),
                "Library/src/Orise_Twin_Rotor/assets/orise_slider.png",
                "assets/orise_slider.png"
            ]
            path = ""
            for p in possible_paths:
                if os.path.exists(p):
                    path = os.path.abspath(p)
                    break

            if path:
                self.pixmap = QtGui.QPixmap(path)
                self.pixmap = self.pixmap.scaled(self.pixmap.width() // 4, self.pixmap.height() // 4)
                self.label.setPixmap(self.pixmap)
            else:
                self.label.setText("Orise Twin Rotor Research Platform")
                self.label.setStyleSheet("color: #fbaa1d; font-size: 18px; font-weight: bold; padding: 10px;")

            self.main_layout.addWidget(self.label)

            self.graph_window = Graph_Window()
            self.update_timer = QtCore.QTimer()
            self.update_timer.setInterval(update_interval)
            self.update_timer.start()
            self.update_timer.timeout.connect(self.on_graph_update)
            self.main_layout.addWidget(self.graph_window)

            self.data_buffers = data_buffers
            self.on_graph_update()

        def on_graph_update(self):
            self.data_buffers.lock.acquire()
            self.graph_window.update(self.data_buffers)
            self.data_buffers.lock.release()


    class Create_Gui:
        def __init__(self, data_buffers: Data_Buffers):
            """
            Simple Gui to easily plot data obtained from the twin rotor. Runs in a separate thread.
            """
            self.data_buffers = data_buffers
            self.t = threading.Thread(target=self.__run)
            self.time_graphs = defaultdict(lambda: [])

        def start(self):
            self.t.start()

        def add_time_graph(self, title: str, buffer_data_func: Callable[[Data_Buffers], Iterable[float]], color: Tuple[int,int,int]=Colors.ORISE_YELLOW, name: Optional[str]=None):
            self.time_graphs[title].append((buffer_data_func, color, name))

        def add_twin_rotor_data(self, title: str, reading_name: str, color: Tuple[int,int,int]=Colors.ORISE_YELLOW, name: Optional[str]=None):
            if not hasattr(self.data_buffers, reading_name):
                print(f"Reading name '{reading_name}' is invalid -- ignoring the plot")
                return
            self.add_time_graph(title, lambda x: getattr(x, reading_name).data, color, name)

        def add_custom_buffer_graph(self, title: str, buffer: Custom_Buffer, color: Tuple[int,int,int]=Colors.ORISE_YELLOW, name: Optional[str]=None):
            self.add_time_graph(title, lambda x: buffer.numpy_data, color, name)

        @property
        def active(self):
            return self.t.is_alive()

        def __del__(self):
            if hasattr(self, 't') and self.t.is_alive():
                self.t.join()

        def __run(self):
            app = QtWidgets.QApplication(sys.argv)
            w = Main_Window(50, self.data_buffers)
            for title in self.time_graphs:
                graphs = tuple(a[0] for a in self.time_graphs[title])
                colors = tuple(a[1] for a in self.time_graphs[title])
                names = tuple(a[2] for a in self.time_graphs[title])
                w.graph_window.add_time_graph(title, *graphs, colors=colors, names=names)
            w.show()
            app.exec()
            w.update_timer.stop()

else:
    class Create_Gui:
        def __init__(self, data_buffers: Data_Buffers):
            print("Warning: PyQt5 or pyqtgraph is not installed. GUI features are disabled.")
            self.data_buffers = data_buffers
            self._active = False

        def start(self):
            pass

        def add_time_graph(self, *args, **kwargs):
            pass

        def add_twin_rotor_data(self, *args, **kwargs):
            pass

        def add_custom_buffer_graph(self, *args, **kwargs):
            pass

        @property
        def active(self):
            return False


# =====================================================================
# MODULE: matplotlib_plotter
# =====================================================================
if HAS_MATPLOTLIB:
    class Matplotlib_Plotter:
        def __init__(self, data_buffers: Data_Buffers, plot_shape: Tuple[int, int]):
            self.data_buffers = data_buffers
            self.fig, self.axes = plt.subplots(*plot_shape, squeeze=False)
            self.plot_shape = plot_shape
            self.plot_funcs = [[None for _ in range(self.plot_shape[1])] for _ in range(self.plot_shape[0])]

        def add_time_plot(self, plot_func: Callable[[Data_Buffers], Iterable[float]], title: str, row: int, column: int):
            self.plot_funcs[row][column] = (title, lambda x: (self.data_buffers.time.data, plot_func(x))) # type: ignore
            self.axes[row][column].set_title(title)

        def draw(self, pause=0.001):
            for row_f, row_p in zip(self.plot_funcs, self.axes):
                for data, axis in zip(row_f, row_p):
                    if data is None:
                        continue
                    (title, func) = data
                    axis.clear()
                    axis.plot(*func(self.data_buffers))
            plt.pause(pause)

        @property
        def figure(self):
            return self.fig
else:
    class Matplotlib_Plotter:
        def __init__(self, data_buffers: Data_Buffers, plot_shape: Tuple[int, int]):
            print("Warning: Matplotlib is not installed. Matplotlib Plotter is disabled.")
        def add_time_plot(self, *args, **kwargs):
            pass
        def draw(self, *args, **kwargs):
            pass


# =====================================================================
# =====================================================================
# YOUR CUSTOM CODE (PID3 controller example)
# =====================================================================
from math import radians
from time import sleep

TR = None


# AHRS / Kalman
def setup_ahrs_kalman(TR):
    if KalmanFilter is None:
        raise ImportError("filterpy is not installed. Please install it using 'pip install filterpy'.")
    kf = KalmanFilter(dim_x=6, dim_z=4)
    kf.x = np.zeros(6)
    kf.F = np.eye(6)
    kf.H = np.array([
        [1, 0, 0, 0, 0, 0],
        [0, 1, 0, 0, 0, 0],
        [0, 0, 1, 0, 0, 0],
        [0, 0, 1, 0, 0, 0]
    ])
    kf.P *= 10.0
    kf.R = np.diag([0.1, 0.1, 10.0, 0.01])
    kf.Q = np.eye(6) * 0.01
    return kf


def normalize_angle(angle):
    return (angle + np.pi) % (2.0 * np.pi) - np.pi


def get_ahrs(TR, dt):
    acc = TR.imu.acceleration
    mag = TR.imu.magnetic
    enc1 = TR.encoder.encoder1

    z_roll = np.arctan2(acc[1], acc[2])
    z_pitch = np.arctan2(acc[0], acc[2])
    z_yaw_mag = np.arctan2(mag[1], mag[0])
    z_yaw_enc = normalize_angle((enc1 / 406.0) * (2.0 * np.pi))

    TR.kf.F[0, 3] = dt
    TR.kf.F[1, 4] = dt
    TR.kf.F[2, 5] = dt

    TR.kf.predict()

    z = np.array([z_roll, z_pitch, z_yaw_mag, z_yaw_enc])
    y = z - (TR.kf.H @ TR.kf.x)
    y[2:] = [normalize_angle(val) for val in y[2:]]

    S = TR.kf.H @ TR.kf.P @ TR.kf.H.T + TR.kf.R
    K = TR.kf.P @ TR.kf.H.T @ np.linalg.inv(S)

    TR.kf.x = TR.kf.x + K @ y
    TR.kf.P = (np.eye(6) - K @ TR.kf.H) @ TR.kf.P

    return TR.kf.x[0], TR.kf.x[1], TR.kf.x[2]   # roll, pitch, yaw


# Rigid-body helpers
def compute_R(theta, phi, degrees=False):
    if degrees:
        theta = np.deg2rad(theta)
        phi = np.deg2rad(phi)

    cth = np.cos(theta)
    sth = np.sin(theta)
    cph = np.cos(phi)
    sph = np.sin(phi)

    return np.array([
        [cth,      -cph * sth,   sph * sth],
        [sth,       cph * cth,  -sph * cth],
        [0.0,       sph,         cph]
    ])


def compute_K(I):
    I = np.asarray(I, dtype=float)

    if I.shape == (3,):
        I1, I2, I3 = I
    elif I.shape == (3, 3):
        if not np.allclose(I, np.diag(np.diag(I))):
            raise ValueError("I must be diagonal in the chosen principal axes.")
        I1, I2, I3 = np.diag(I)
    else:
        raise ValueError("I must be [I1, I2, I3] or a 3x3 diagonal matrix.")

    return np.diag([
        I2 + I3 - I1,
        I3 + I1 - I2,
        I1 + I2 - I3
    ])


def compute_Omega_from_samples(theta, phi, theta_prev, phi_prev, dt):
    dt = max(dt, 1e-4)

    theta_dot = normalize_angle(theta - theta_prev) / dt
    phi_dot = normalize_angle(phi - phi_prev) / dt

    Omega = np.array([
        phi_dot,
        theta_dot * np.sin(phi),
        theta_dot * np.cos(phi)
    ], dtype=float)

    return Omega


def compute_reference(t_now, yaw_ref_deg=-120.0, pitch_ref_deg=-45.0,
                      yaw_mode='fixed', pitch_mode='fixed'):
    if pitch_mode == 'fixed':
        ref_p = np.radians(pitch_ref_deg)
        ref_p_dot = 0.0
        ref_p_ddot = 0.0
    elif pitch_mode == 'sin':
        freq = 0.1
        w = 2.0 * np.pi * freq
        A = np.radians(10.0)
        offset = np.radians(pitch_ref_deg)
        ref_p = offset + A * np.sin(w * t_now)
        ref_p_dot = A * w * np.cos(w * t_now)
        ref_p_ddot = -A * (w**2) * np.sin(w * t_now)
    else:
        ref_p = np.radians(pitch_ref_deg)
        ref_p_dot = 0.0
        ref_p_ddot = 0.0

    if yaw_mode == 'fixed':
        ref_y = np.radians(yaw_ref_deg)
        ref_y_dot = 0.0
        ref_y_ddot = 0.0
    elif yaw_mode == 'ramp':
        ref_y_dot = np.radians(5.0)
        ref_y_ddot = 0.0
        ref_y = np.radians(yaw_ref_deg) + ref_y_dot * t_now
    else:
        ref_y = np.radians(yaw_ref_deg)
        ref_y_dot = 0.0
        ref_y_ddot = 0.0

    return ref_p, ref_p_dot, ref_p_ddot, ref_y, ref_y_dot, ref_y_ddot


def thrust_to_rpm(u_val):
    deadband = 0.05

    if abs(u_val) < deadband:
        linear_slope = 2828.0 * np.sqrt(deadband) / deadband
        return np.sign(u_val) * linear_slope * abs(u_val)
    else:
        return np.sign(u_val) * 2828.0 * np.sqrt(abs(u_val))


def apply_ramp(curr, tar, delta_t, max_slew_rate):
    step = max_slew_rate * delta_t
    return curr + np.clip(tar - curr, -step, step)


def main():
    global TR
    
    if KalmanFilter is None:
        print("Error: filterpy is not installed. Please run 'pip install filterpy' to use this controller.")
        sys.exit(1)
        
    if np is None:
        print("Error: numpy is not installed. Please install numpy to use this controller.")
        sys.exit(1)

    TR = Twin_Rotor()
    
    # Parameters
    dt_const = 0.01
    I1 = 0.07
    I2 = 0.01222
    I3 = 0.07
    I = np.diag([I1, I2, I3])
    Kmat = compute_K(I)

    Kp = np.diag([50, 0.0, 8.0])
    Kd = np.diag([40.0, 0.0, 5.0])
    Ki = np.diag([0.0, 0.0, 0.0])

    max_slew_rate = 5000.0
    current_m0 = 0.0
    current_m1 = 0.0

    TR.kf = setup_ahrs_kalman(TR)

    try:
        start_time = time.time()

        roll, pitch, yaw = get_ahrs(TR, dt_const)
        dt = TR.update_readings()

        theta_prev = yaw
        phi_prev = pitch
        eIR = np.zeros(3)

        while True:
            t0 = time.perf_counter()
            dt = TR.update_readings()
            t_now = time.time() - start_time

            roll, pitch, yaw = get_ahrs(TR, dt)

            # Reference generator
            ref_p, ref_p_dot, ref_p_ddot, ref_y, ref_y_dot, ref_y_ddot = compute_reference(
                t_now,
                yaw_ref_deg=-240.0,
                pitch_ref_deg=-25.0,
                yaw_mode='fixed',
                pitch_mode='fixed'
            )

            # measured states mapped to model coordinates
            theta_meas = yaw
            phi_meas = pitch

            # current attitude and angular velocity
            R = compute_R(theta_meas, phi_meas)
            Omega = compute_Omega_from_samples(
                theta_meas, phi_meas,
                theta_prev, phi_prev,
                dt
            )

            # reference attitude and reference angular terms
            Rr = compute_R(ref_y, ref_p)
            Omega_r = np.array([
                ref_p_dot,
                ref_y_dot * np.sin(ref_p),
                ref_y_dot * np.cos(ref_p)
            ])

            Pi_dot_r = I @ np.array([
                ref_p_ddot,
                ref_y_ddot * np.sin(ref_p),
                ref_y_ddot * np.cos(ref_p)
            ])

            # body-frame errors
            Re = Rr @ R.T
            Re_body = R.T @ Rr

            eR_hat = 0.5 * (Re_body @ Kmat - Kmat @ Re_body.T)
            eR = np.array([
                eR_hat[2, 1],
                eR_hat[0, 2],
                eR_hat[1, 0]
            ])

            Omega_r_body = Re_body @ Omega_r
            pi_e = (I @ Omega_r_body) - (I @ Omega)
            feedforward = (Re_body @ Pi_dot_r) + np.cross(Omega, I @ Omega_r_body)

            # anti-windup integral clamp
            eIR = np.clip(eIR + eR * dt, -5.0, 5.0)

            Tu = feedforward + (Kp @ eR) + (Kd @ pi_e) + (Ki @ eIR)

            # actuator allocation
            A_alloc = np.array([
                [1.0, -0.0],
                [0.0, -1.0]
            ])
            u, _, _, _ = np.linalg.lstsq(A_alloc, np.array([Tu[0], Tu[2]]), rcond=None)

            target_m0 = thrust_to_rpm(u[0])
            target_m1 = thrust_to_rpm(u[1])

            current_m0 = apply_ramp(current_m0, target_m0, dt, max_slew_rate)
            current_m1 = apply_ramp(current_m1, target_m1, dt, max_slew_rate)

            m0_speed = np.clip(current_m0, -3500, 3500)
            m1_speed = np.clip(current_m1, -3500, 3500)

            # hardware motor mapping
            TR.motors.set_speed_M1(m0_speed)

            theta_prev = theta_meas
            phi_prev = phi_meas

            error_pitch = np.degrees(normalize_angle(ref_p - pitch))
            error_yaw = np.degrees(normalize_angle(ref_y - yaw))

            print(
                f"roll={np.degrees(roll):.3f} deg, "
                f"pitch={np.degrees(pitch):.3f} deg, "
                f"yaw={np.degrees(yaw):.3f} deg, "
                f"ref_pitch={np.degrees(ref_p):.2f} deg, "
                f"ref_yaw={np.degrees(ref_y):.2f} deg, "
                f"M1={m0_speed:.2f}, M2={m1_speed:.2f}, "
                f"error_pitch={error_pitch:.2f} deg, "
                f"error_yaw={error_yaw:.2f} deg"
            )

            elapsed = time.perf_counter() - t0
            time.sleep(max(0.0, dt - elapsed))

    except KeyboardInterrupt:
        print("\nKeyboard interrupt received. Stopping motors...")

    finally:
        TR.motors.stop()
        print("Motors stopped safely.")


if __name__ == "__main__":
    main()


