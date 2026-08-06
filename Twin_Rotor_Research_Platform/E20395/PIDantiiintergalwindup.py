import numpy as np
import time
import csv
from filterpy.kalman import KalmanFilter
from Orise_Twin_Rotor import Twin_Rotor

TR = Twin_Rotor()


# ----------------------------
# AHRS / Kalman
# ----------------------------
def setup_ahrs_kalman(TR):
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


def get_ahrs(dt):
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


# ----------------------------
# Rigid-body helpers
# ----------------------------
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
        freq = 0.01
        w = 2.0 * np.pi * freq
        A = np.radians(25.0)
        offset = 0.0

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
    deadband = 0.5

    if abs(u_val) < deadband:
        linear_slope = 2828.0 * np.sqrt(deadband) / deadband
        return np.sign(u_val) * linear_slope * abs(u_val)
    else:
        return np.sign(u_val) * 2828.0 * np.sqrt(abs(u_val))


def apply_ramp(curr, tar, delta_t, max_slew_rate):
    step = max_slew_rate * delta_t
    return curr + np.clip(tar - curr, -step, step)


# ----------------------------
# Parameters
# ----------------------------
dt = 0.01

I1 = 0.06
I2 = 0.0001222
I3 = 0.06

I = np.diag([I1, I2, I3])
Kmat = compute_K(I)

# Kp = np.diag([20.0, 0.0, 20.0])
# Kd = np.diag([20.0, 0.0, 20.0])
# Ki = np.diag([8.0, 0.0, 8.0])


# Kp = np.diag([10.0, 0.0, 0.0])
# Kd = np.diag([5.0, 0.0, 0.0])
# Ki = np.diag([3, 0.0, 0.0])
Kp = np.diag([13.53, 0.0, 0.0])
Kd = np.diag([12, 0.0, 0.0])
Ki = np.diag([0.001, 0.0, 0.0])

# ----------------------------
# Derivative filter + anti-integral-windup parameters
# ----------------------------
D_FILTER_ALPHA = 0.90      # 0.85 to 0.95. Higher value = smoother derivative, slower response
EI_LIMIT_VEC = np.array([0.35, 0.0, 0.0])   # Integral clamp for [pitch_axis, yaw_axis, roll_axis]
ANTI_WINDUP_LEAK = 0.9998   # Slowly discharges integral when actuator is saturated

MOTOR_MAX_RPM = 2500.0
MOTOR_MIN_RPM = 0.0        # keep u1 and u2 positive
U_MIN = 0.0
U_MAX = (MOTOR_MAX_RPM / 2828.0) ** 2   # input value that approximately maps to 2500 rpm

max_slew_rate = 5000.0
current_m0 = 0.0
current_m1 = 0.0

TR.kf = setup_ahrs_kalman(TR)

# ----------------------------
# CSV Logging setup
# ----------------------------
log_file = open("rotor_log.csv", "w", newline="")
csv_writer = csv.writer(log_file)

csv_writer.writerow([
    "time_s",
    "roll_deg",
    "pitch_deg",
    "yaw_deg",
    "ref_pitch_deg",
    "ref_yaw_deg",
    "M1",
    "M2",
    "U1",
    "U2",
    "error_pitch_deg",
    "error_yaw_deg",
    "input_saturated"
])


# ----------------------------
# Main control loop
# ----------------------------
try:
    start_time = time.time()

    roll, pitch, yaw = get_ahrs(dt)
    dt = TR.update_readings()

    theta_prev = yaw
    phi_prev = pitch
    eIR = np.zeros(3)

    # Filter state for derivative/momentum-error term
    pi_e_filt = np.zeros(3)
    first_derivative_sample = True

    while True:
        t0 = time.perf_counter()
        dt = TR.update_readings()
        t_now = time.time() - start_time

        roll, pitch, yaw = get_ahrs(dt)

        ref_p, ref_p_dot, ref_p_ddot, ref_y, ref_y_dot, ref_y_ddot = compute_reference(
            t_now,
            yaw_ref_deg=yaw,
            pitch_ref_deg=25.0,
            yaw_mode='fixed',
            pitch_mode='sin'
        )

        theta_meas = yaw
        phi_meas = pitch

        R = compute_R(theta_meas, phi_meas)
        Omega = compute_Omega_from_samples(
            theta_meas, phi_meas,
            theta_prev, phi_prev,
            dt
        )

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

        Re = Rr @ R.T
        Re_body = R.T @ Rr

        eR_hat = 0.5 * (Re_body @ Kmat - Kmat @ Re_body.T)
        eR = np.array([
            eR_hat[2, 1],
            eR_hat[0, 2],
            eR_hat[1, 0]
        ])

        Omega_r_body = Re_body @ Omega_r

        # ----------------------------
        # Derivative filter
        # ----------------------------
        # This is the D-term signal. It is filtered to reduce sensor-noise spikes
        # and sudden derivative kick. Use body-frame reference angular velocity.
        pi_e_raw = (I @ Omega_r_body) - (I @ Omega)

        if first_derivative_sample:
            pi_e_filt = pi_e_raw.copy()
            first_derivative_sample = False
        else:
            pi_e_filt = (D_FILTER_ALPHA * pi_e_filt
                         + (1.0 - D_FILTER_ALPHA) * pi_e_raw)

        feedforward = Pi_dot_r + np.cross(Omega, I @ Omega_r_body)

        # Keep P, D, and I in the same body-frame direction.
        eR_body = R.T @ eR

        # ----------------------------
        # Anti-integral windup
        # ----------------------------
        # First try a candidate integral update. Then check whether the control
        # input would saturate. If saturated, do not allow the integral to grow.
        eIR_candidate = np.clip(eIR + eR_body * dt, -EI_LIMIT_VEC, EI_LIMIT_VEC)

        Tu_candidate = (feedforward
                        + (Kp @ eR_body)
                        + (Kd @ pi_e_filt)
                        + (Ki @ eIR_candidate))

        Reffernce_U = 0.5
        U_diff_candidate = Tu_candidate[0]
        u1_unsat = Reffernce_U + 0.5 * U_diff_candidate
        u2_unsat = Reffernce_U - 0.5 * U_diff_candidate

        u1_sat = np.clip(u1_unsat, U_MIN, U_MAX)
        u2_sat = np.clip(u2_unsat, U_MIN, U_MAX)

        input_saturated = (abs(u1_sat - u1_unsat) > 1e-9 or
                           abs(u2_sat - u2_unsat) > 1e-9)

        # Accept integral only when not saturated, or when the candidate update
        # is reducing the stored integral. Otherwise leak it slowly toward zero.
        if (not input_saturated) or (np.linalg.norm(eIR_candidate) < np.linalg.norm(eIR)):
            eIR = eIR_candidate
        else:
            eIR = np.clip(ANTI_WINDUP_LEAK * eIR, -EI_LIMIT_VEC, EI_LIMIT_VEC)

        # Recalculate final controller output using the accepted integral value.
        Tu = (feedforward
              + (Kp @ eR_body)
              + (Kd @ pi_e_filt)
              + (Ki @ eIR))

        #A_alloc = np.array([
        #   [1.0, -1.0],
        #  [0.0, 0.0]
        #])
        #u, _, _, _ = np.linalg.lstsq(A_alloc, np.array([Tu[0], Tu[2]]), rcond=None)

        U_diff = Tu[0]
        u1_unsat = Reffernce_U + 0.5 * U_diff
        u2_unsat = Reffernce_U - 0.5 * U_diff

        # Keep u1 and u2 positive and inside the approximate motor capability.
        u1 = np.clip(u1_unsat, U_MIN, U_MAX)
        u2 = np.clip(u2_unsat, U_MIN, U_MAX)

        target_m0 = thrust_to_rpm(u2)
        target_m1 = thrust_to_rpm(u1)

        current_m0 = apply_ramp(current_m0, target_m0, dt, max_slew_rate)
        current_m1 = apply_ramp(current_m1, target_m1, dt, max_slew_rate)

        # Motor commands are now positive speed magnitudes. Direction is handled
        # by the minus sign in set_speed_M0 / set_speed_M1 below.
        m0_speed = np.clip(current_m0, MOTOR_MIN_RPM, MOTOR_MAX_RPM)
        m1_speed = np.clip(current_m1, MOTOR_MIN_RPM, MOTOR_MAX_RPM)

        TR.motors.set_speed_M0(-m1_speed)
        TR.motors.set_speed_M1(-m0_speed)

        theta_prev = theta_meas
        phi_prev = phi_meas

        error_pitch = np.degrees(normalize_angle(ref_p - pitch))
        error_yaw = np.degrees(normalize_angle(ref_y - yaw))

        # Save one row for each loop iteration
        csv_writer.writerow([
            round(t_now, 3),
            round(np.degrees(roll), 3),
            round(np.degrees(pitch), 3),
            round(np.degrees(yaw), 3),
            round(np.degrees(ref_p), 2),
            round(np.degrees(ref_y), 2),
            round(m0_speed, 2),
            round(m1_speed, 2),
            round(u1, 3),
            round(u2, 3),
            round(error_pitch, 2),
            round(error_yaw, 2),
            int(input_saturated)
        ])
        log_file.flush()

        print(
            f"roll={np.degrees(roll):.3f} deg, "
            f"pitch={np.degrees(pitch):.3f} deg, "
            f"yaw={np.degrees(yaw):.3f} deg, "
            f"ref_pitch={np.degrees(ref_p):.2f} deg, "
            f"ref_yaw={np.degrees(ref_y):.2f} deg, "
            f"M1={m0_speed:.2f}, M2={m1_speed:.2f}, "
            f"u1={u1:.3f}, u2={u2:.3f}, "
            f"sat={int(input_saturated)}, "
            f"error_pitch={error_pitch:.2f} deg, "
            f"error_yaw={error_yaw:.2f} deg"
        )

        elapsed = time.perf_counter() - t0
        time.sleep(max(0.0, dt - elapsed))

except KeyboardInterrupt:
    print("\nKeyboard interrupt received. Stopping motors...")

finally:
    TR.motors.stop()
    log_file.close()
    print("Motors stopped safely.")