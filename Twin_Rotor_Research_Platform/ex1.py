from Orise_Twin_Rotor import Twin_Rotor
from time import sleep
twin_rotor = Twin_Rotor()

while True:
    time_delta = twin_rotor.update_readings()
    encoder_value = twin_rotor.encoder.encoder1
    mag_x, mag_y, mag_z = twin_rotor.imu.magnetic
    gyro_z,gyro_y,gyro_x = twin_rotor.imu.gyro
    acc_x, acc_y, acc_z = twin_rotor.imu.acceleration
