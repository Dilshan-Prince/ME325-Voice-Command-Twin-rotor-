from Orise_Twin_Rotor import Twin_Rotor
from time import sleep
from Orise_Twin_Rotor import Data_Buffers
from Orise_Twin_Rotor import Create_Gui, READING_NAMES
from Orise_Twin_Rotor import CSV_Logger
import numpy as np
import math
from time import time

import sys
from time import perf_counter
import os
import json
import urllib.request
import threading

try:
    import websocket as _ws_lib
except ImportError:
    _ws_lib = None

TR = None


class ControlState:
    def __init__(self):
        self.active = False
        self.target_pitch_deg = 0.0
        self.target_yaw_deg = 0.0
        self.pitch_deg = 0.0
        self.yaw_deg = 0.0
        self.encoder1 = 0


class HardwarePipelineClient:
    """
    Pipeline 2 Client: Runs on the Raspberry Pi.
    Connects to the Laptop server's WebSocket endpoint.
    1. Sends live IMU telemetry to the Laptop so it can relay to the Mobile App.
    2. Listens for hardware_command dispatches (sent when user approves a trajectory).
    """
    def __init__(self, state: ControlState, host: str = "192.168.0.110", port: int = 8000):
        self.state = state
        self.host = host
        self.port = port
        self._running = True
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()
        print(f"[Pi Client]: Connecting to Laptop server at ws://{self.host}:{self.port}/ws")

    def stop(self):
        self._running = False

    def _run(self):
        import websocket  # websocket-client library (pip install websocket-client)

        url = f"ws://{self.host}:{self.port}/ws"
        while self._running:
            try:
                ws = websocket.WebSocket()
                ws.connect(url)
                print(f"[Pi Client]: Connected to Laptop server at {url}")

                # Set a short timeout so recv doesn't block telemetry sends forever
                ws.settimeout(0.04)

                while self._running:
                    # 1. Send telemetry to laptop
                    telemetry = json.dumps({
                        "type": "pi_telemetry",
                        "pitch": self.state.pitch_deg,
                        "yaw": self.state.yaw_deg,
                        "encoder1": self.state.encoder1,
                        "pwm1": 1500,
                        "pwm2": 1500,
                        "timestamp": time()
                    })
                    try:
                        ws.send(telemetry)
                    except Exception:
                        break

                    # 2. Check for incoming commands from laptop
                    try:
                        data = ws.recv()
                        if data:
                            payload = json.loads(data)
                            msg_type = payload.get("type", "")
                            cmd = payload.get("cmd", "")

                            if msg_type == "hardware_command" and cmd == "EXECUTE":
                                pitch = float(payload.get("pitch", 0.0))
                                yaw = float(payload.get("yaw", 0.0))
                                print(f"\n=======================================================")
                                print(f"[Pi Client]: Hardware command received from Laptop!")
                                print(f"[Pi Client]: Target Pitch = {pitch} deg, Target Yaw = {yaw} deg")
                                print(f"[Pi Client]: Actuating Twin Rotor hardware motors...")
                                print(f"=======================================================\n")
                                self.state.target_pitch_deg = pitch
                                self.state.target_yaw_deg = yaw
                                self.state.active = True
                    except websocket.WebSocketTimeoutException:
                        pass  # No message available, continue loop
                    except Exception:
                        break

                    sleep(0.05)  # ~20 Hz loop

            except Exception as e:
                print(f"[Pi Client]: Connection failed ({e}). Retrying in 3s...")
                sleep(3)
            finally:
                try:
                    ws.close()
                except Exception:
                    pass



def normalize_angle(angle):
    return (angle + np.pi) % (2.0 * np.pi) - np.pi


def get_ahrs(TR, dt):
    acc = TR.imu.acceleration
    enc1 = TR.encoder.encoder1

    # Roll is physically locked on the 2-DOF platform
    roll = 0.0
    
    # Pitch is obtained directly from gravity vector
    pitch = np.arctan2(acc[0], acc[2])
    
    # Yaw is obtained directly from optical encoder
    yaw = normalize_angle((enc1 / 406.0) * (2.0 * np.pi))

    return roll, pitch, yaw


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

    state = ControlState()

    try:
        start_time = time()

        roll, pitch, yaw = get_ahrs(TR, dt_const)
        dt = TR.update_readings()

        theta_prev = yaw
        phi_prev = pitch
        eIR = np.zeros(3)

        # Set initial target angles to current orientation in degrees
        state.target_pitch_deg = float(np.degrees(pitch))
        state.target_yaw_deg = float(np.degrees(yaw))
        state.pitch_deg = float(np.degrees(pitch))
        state.yaw_deg = float(np.degrees(yaw))
        state.encoder1 = int(TR.encoder.encoder1)

        # Start Pipeline 2 client to connect to Laptop server
        pipeline_client = HardwarePipelineClient(state)
        pipeline_client.start()

        while True:
            t0 = perf_counter()
            dt = TR.update_readings()
            t_now = time() - start_time

            roll, pitch, yaw = get_ahrs(TR, dt)

            # Update telemetry state for sending to laptop server
            state.pitch_deg = float(np.degrees(pitch))
            state.yaw_deg = float(np.degrees(yaw))
            state.encoder1 = int(TR.encoder.encoder1)

            # Reference generator
            ref_p, ref_p_dot, ref_p_ddot, ref_y, ref_y_dot, ref_y_ddot = compute_reference(
                t_now,
                yaw_ref_deg=state.target_yaw_deg,
                pitch_ref_deg=state.target_pitch_deg,
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
            if not state.active:
                TR.motors.stop()
            else:
                TR.motors.set_speed_M1(m0_speed)
                # TR.motors.set_speed_M0(m1_speed)

            theta_prev = theta_meas
            phi_prev = phi_meas

            error_pitch = np.degrees(normalize_angle(ref_p - pitch))
            error_yaw = np.degrees(normalize_angle(ref_y - yaw))

            # print(
            #     f"roll={np.degrees(roll):.3f} deg, "
            #     f"pitch={np.degrees(pitch):.3f} deg, "
            #     f"yaw={np.degrees(yaw):.3f} deg, "
            #     f"ref_pitch={np.degrees(ref_p):.2f} deg, "
            #     f"ref_yaw={np.degrees(ref_y):.2f} deg, "
            #     f"M1={m0_speed:.2f}, M2={m1_speed:.2f}, "
            #     f"error_pitch={error_pitch:.2f} deg, "
            #     f"error_yaw={error_yaw:.2f} deg"
            # )

            elapsed = perf_counter() - t0
            sleep(max(0.0, dt - elapsed))

    except KeyboardInterrupt:
        print("\nKeyboard interrupt received. Stopping motors...")

    finally:
        if 'pipeline_client' in locals():
            pipeline_client.stop()
        TR.motors.stop()
        print("Motors stopped safely.")


if __name__ == "__main__":
    main()
