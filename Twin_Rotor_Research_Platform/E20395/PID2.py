import numpy as np
import time
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
    return (angle + np.pi) % (2 * np.pi) - np.pi

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
    TR.kf.x[2] = normalize_angle(TR.kf.x[2])
    return TR.kf.x[0], TR.kf.x[1], TR.kf.x[2]   # roll, pitch, yaw


# ----------------------------
# Rigid-body helpers
# ----------------------------
def compute_Re(Rr, R):
    Rr = np.asarray(Rr, dtype=float)
    R = np.asarray(R, dtype=float)
    return Rr @ R.T


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


def compute_Omega_from_samples(theta, phi, theta_prev, phi_prev, dt):
    dt = max(dt, 1e-4)

    theta_dot = normalize_angle(theta - theta_prev) / dt
    phi_dot   = (phi - phi_prev) / dt

    Omega = np.array([
        phi_dot,
        theta_dot * np.sin(phi),
        theta_dot * np.cos(phi)
    ], dtype=float)

    return Omega


def compute_Pi(I, Omega):
    I = np.asarray(I, dtype=float)
    Omega = np.asarray(Omega, dtype=float)
    return I @ Omega


def compute_eR_vector(K, Re):
    K = np.asarray(K, dtype=float)
    Re = np.asarray(Re, dtype=float)

    eR_hat = 0.5 * (Re @ K - K @ Re.T)
    eR_hat = 0.5 * (eR_hat - eR_hat.T)  # enforce skew symmetry

    return np.array([
        eR_hat[2, 1],
        eR_hat[0, 2],
        eR_hat[1, 0]
    ])


def integrate_step(eIR_prev, eR, dt):
    eIR_prev = np.asarray(eIR_prev, dtype=float)
    eR = np.asarray(eR, dtype=float)
    return eIR_prev + eR * dt


def controll_law(Pir_dot, Omega, Pir, kp, kd, ki, R, I, er, eir):
    Pir_dot = np.asarray(Pir_dot, dtype=float)
    Omega = np.asarray(Omega, dtype=float)
    Pir = np.asarray(Pir, dtype=float)
    kp = np.asarray(kp, dtype=float)
    kd = np.asarray(kd, dtype=float)
    ki = np.asarray(ki, dtype=float)
    R = np.asarray(R, dtype=float)
    I = np.asarray(I, dtype=float)
    er = np.asarray(er, dtype=float)
    eir = np.asarray(eir, dtype=float)

    Tu = (
        Pir_dot
        + np.cross(Omega, Pir)
        + kp @ (R.T @ er)
        + kd @ (Pir - I @ Omega)
        + ki @ (R.T @ eir)
    )

    return Tu


def compute_u1_u2(Tu, alpha=0.0, beta=-np.pi/2, degrees=False):
    Tu = np.asarray(Tu, dtype=float).flatten()

    if degrees:
        alpha = np.deg2rad(alpha)
        beta = np.deg2rad(beta)

    if Tu.size != 3:
        raise ValueError("Tu must be a 3-vector [Tx, Ty, Tz].")

    Tx, Ty, Tz = Tu

    if not np.isclose(Ty, 0.0, atol=1e-6):
        print(f"Warning: Tu[1] = {Ty:.6f} is not zero. Ignoring it in u1/u2 mapping.")

    den = np.sin(alpha - beta)
    if np.isclose(den, 0.0):
        raise ValueError("No unique solution because sin(alpha - beta) = 0.")

    u1 = (-Tx * np.sin(beta) + Tz * np.cos(beta)) / den
    u2 = -(-Tx * np.sin(alpha) + Tz * np.cos(alpha)) / den

    return u1, u2


def saturate_motor(u, limit=5000.0, nonnegative=False):
    if nonnegative:
        return float(np.clip(u, 0.0, limit))
    return float(np.clip(u, -limit, limit))
#------------------------------------
# MOTOR MAP
#--------------------------------


# def exponential_motor_map(u, limit=5000.0, expo=5.0):
#     """
#     Exponential mapping of control input to motor command.

#     Parameters
#     ----------
#     u : float
#         Raw controller output
#     limit : float
#         Maximum absolute motor command
#     expo : float
#         Exponential shaping strength
#         expo = 0  -> linear map
#         larger expo -> stronger exponential shape

#     Returns
#     -------
#     cmd : float
#         Mapped motor command in [-limit, limit]
#     """
#     u = float(np.clip(u, -limit, limit))

#     if np.isclose(expo, 0.0):
#         return u

#     s = np.sign(u)
#     x = abs(u) / limit   # normalize to [0, 1]

#     y = (np.exp(expo * x) - 1.0) / (np.exp(expo) - 1.0)

#     return s * limit * y

# def exponential_motor_map_positive(u, limit=5000.0, expo=3.0):
#     u = float(np.clip(u, 0.0, limit))

#     if np.isclose(expo, 0.0):
#         return u

#     x = u / limit
#     y = (np.exp(expo * x) - 1.0) / (np.exp(expo) - 1.0)

#     return limit * y


def motor_speed_map(u, u_max_in=5000.0, cmd_min=1200.0, cmd_max=5000.0, k=4.0):
    """
    Map controller output u to motor speed command.

    x-axis : u   (controller output)
    y-axis : cmd (motor speed)

    Parameters
    ----------
    u : float
        Raw controller output
    u_max_in : float
        Maximum expected raw input
    cmd_min : float
        Minimum motor speed that can actually spin the motor
    cmd_max : float
        Maximum motor speed
    k : float
        Shape factor. Larger k => rises faster near zero

    Returns
    -------
    cmd : float
        Motor speed command
    """
    u = float(np.clip(u, 0.0, u_max_in))

    if u <= 0.0:
        return cmd_min

    x = u / u_max_in
    y = (1.0 - np.exp(-k * x)) / (1.0 - np.exp(-k))

    cmd = cmd_min + (cmd_max - cmd_min) * y
    return float(np.clip(cmd, 0.0, cmd_max))


def thrust_to_rpm(u_val):
    # The threshold where we switch from Square Root to Linear mapping
    deadband = 0.05 
    
    if abs(u_val) < deadband:
        # Linear mapping near zero: prevents infinite gain/chattering
        linear_slope = 2828.0 * np.sqrt(deadband) / deadband
        return np.sign(u_val) * linear_slope * abs(u_val)
    else:
        # Standard quadratic aerodynamic mapping
        return np.sign(u_val) * 2828.0 * np.sqrt(abs(u_val))
    


# Slew
def apply_ramp(curr, tar, delta_t):
    step = max_slew_rate * delta_t
    return curr + np.clip(tar - curr, -step, step)




# ----------------------------
# Parameters
# ----------------------------
dt = 0.01

I1 = 0.025
I2 = 0.004
#I3 = 0.008
I3 = 0.04

I = np.diag([I1, I2, I3])

# Kp = np.diag([150.0, 0.0, 450.0])
# Kd = np.diag([40.0, 0.0, 60.0])
# Ki = np.diag([5.0, 0.0, 1.0])
Kp = np.diag([5, 0.0, 0])
Kd = np.diag([20.0, 0.0, 0.0])
Ki = np.diag([0.0, 0.0, 0.0])

Kmat = compute_K(I)

# Motor slew limiters
max_slew_rate = 5000.0
current_m0 = 0.0
current_m1 = 0.0

# constant reference

theta_ref = -np.pi/2


Omegar = np.zeros(3)       # constant reference => zero angular velocity
Pir = compute_Pi(I, Omegar)
Pir_dot = np.zeros(3)      # constant reference => zero momentum derivative

# initialize filter
TR.kf = setup_ahrs_kalman(TR)


# ----------------------------
# Main control loop
# ----------------------------
try:
    # first reading for derivative initialization
    roll, pitch, yaw = get_ahrs(dt)

    phi_ref = pitch
    Rr = compute_R(theta_ref, phi_ref)

    


    # Assumption:
    # theta = yaw, phi = pitch
    # Change this mapping if your twin-rotor axes are different.
    dt = TR.update_readings()

    theta_prev = yaw
    phi_prev = pitch

    eIR = np.zeros(3)

    while True:
        t0 = time.perf_counter()
        dt = TR.update_readings()


        roll, pitch, yaw = get_ahrs(dt)
        #yaw, pitch, yaw = get_ahrs(dt)


        # map measured angles to model coordinates
        theta_meas = yaw
        phi_meas = pitch

        Omega = compute_Omega_from_samples(
            theta_meas, phi_meas,
            theta_prev, phi_prev,
            dt
        )

        R = compute_R(theta_meas, phi_meas)
        Re = compute_Re(Rr, R)
        eR = compute_eR_vector(Kmat, Re)
        eIR = integrate_step(eIR, eR, dt)

        Tu = controll_law(
            Pir_dot=Pir_dot,
            Omega=Omega,
            Pir=Pir,
            kp=Kp,
            kd=Kd,
            ki=Ki,
            R=R,
            I=I,
            er=eR,
            eir=eIR
        )

        u1, u2 = compute_u1_u2(Tu)

        # limit motor commands before sending
        # u1_cmd = exponential_motor_map_positive(u1, limit=5000.0, expo=3.0)
        # u2_cmd = exponential_motor_map_positive(u2, limit=5000.0, expo=3.0)

        # TR.motors.set_speed_M0(u1_cmd)
        # TR.motors.set_speed_M1(u2_cmd)

        # u1 = max(0.0, u1)
        # u2 = max(0.0, u2)

        # u1_cmd = motor_speed_map(u1, u_max_in=3000.0, cmd_min=1700.0, cmd_max=3000.0, k=16.0)
        # u2_cmd = motor_speed_map(u2, u_max_in=3000.0, cmd_min=2200.0, cmd_max=3000.0, k=16.0)
        target_m0 = thrust_to_rpm(u1)
        target_m1 = thrust_to_rpm(u2)

        current_m0 = apply_ramp(current_m0, target_m0, dt)
        current_m1 = apply_ramp(current_m1, target_m1, dt)

        m0_speed = np.clip(current_m0, -2000, 2000)
        m1_speed = np.clip(current_m1, -2000, 2000)


        TR.motors.set_speed_M0(m0_speed)
        # TR.motors.set_speed_M1(m1_speed)


        theta_prev = theta_meas
        phi_prev = phi_meas

        print(
            f"roll={np.degrees(roll):.3f} deg, "
            f"pitch={np.degrees(pitch):.3f} deg, "
            f"yaw={np.degrees(yaw):.3f} deg, "
            f"u1={m0_speed:.2f}, u2={m1_speed:.2f}, "
            f"error_pitch={np.degrees(normalize_angle(phi_ref - pitch)):.2f} deg, "
            f"error_yaw={np.degrees(normalize_angle(theta_ref - yaw)):.2f} deg"
        )

        elapsed = time.perf_counter() - t0
        time.sleep(max(0.0, dt - elapsed))

except KeyboardInterrupt:
    print("\nKeyboard interrupt received. Stopping motors...")

finally:
    TR.motors.stop()
    print("Motors stopped safely.")