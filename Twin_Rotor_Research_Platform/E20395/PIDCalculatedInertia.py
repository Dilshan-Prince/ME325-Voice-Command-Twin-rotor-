import numpy as np
import time
from filterpy.kalman import KalmanFilter
from Orise_Twin_Rotor import Twin_Rotor

TR = Twin_Rotor()

# ----------------------------
# 1. Physical Parameters (Synchronized with Code 2)
# ----------------------------
# These match the dimensions and masses of the Twin Rotor assembly
m_a, r_a, L_a = 0.15, 0.04, 0.30
m_r, r_r, L_r = 0.25, 0.22, 0.31

# Inertia Mapping: I1=Roll, I3=Pitch, I2=Yaw
I1_val = (1/3) * m_a * (L_a**2) + 2 * m_r * (L_r**2)
I2_val = (1/2) * m_a * (r_a**2) + m_r * (r_r**2)
I3_val = I1_val

# J is the diagonal inertia matrix
J = np.diag([I1_val, I3_val, I2_val])

# Kmat is used for the weighted geometric orientation error
def compute_K(I_mat):
    diag = np.diag(I_mat)
    i1, i2, i3 = diag[0], diag[1], diag[2]
    return np.diag([i2 + i3 - i1, i1 + i3 - i2, i1 + i2 - i3])

Kmat = compute_K(J)

# ----------------------------
# 2. AHRS / Kalman Functions
# ----------------------------
def setup_ahrs_kalman(TR):
    kf = KalmanFilter(dim_x=6, dim_z=4)
    kf.x = np.zeros(6)
    kf.F = np.eye(6)
    kf.H = np.array([
        [1, 0, 0, 0, 0, 0], [0, 1, 0, 0, 0, 0],
        [0, 0, 1, 0, 0, 0], [0, 0, 1, 0, 0, 0]
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

    TR.kf.F[0, 3] = TR.kf.F[1, 4] = TR.kf.F[2, 5] = dt
    TR.kf.predict()

    z = np.array([z_roll, z_pitch, z_yaw_mag, z_yaw_enc])
    y = z - (TR.kf.H @ TR.kf.x)
    y[2:] = [normalize_angle(val) for val in y[2:]]

    S = TR.kf.H @ TR.kf.P @ TR.kf.H.T + TR.kf.R
    K = TR.kf.P @ TR.kf.H.T @ np.linalg.inv(S)

    TR.kf.x += K @ y
    TR.kf.P = (np.eye(6) - K @ TR.kf.H) @ TR.kf.P
    return TR.kf.x[0], TR.kf.x[1], TR.kf.x[2]

# ----------------------------
# 3. Geometric & Reference Helpers
# ----------------------------
def compute_R(theta, phi):
    """Rotation Matrix from Spatial to Body frame."""
    return np.array([
        [np.cos(theta), -np.cos(phi)*np.sin(theta),  np.sin(phi)*np.sin(theta)],
        [np.sin(theta),  np.cos(phi)*np.cos(theta), -np.sin(phi)*np.cos(theta)],
        [0,              np.sin(phi),               np.cos(phi)]
    ])

def compute_reference(t):
    """Generates trajectory targets."""
    # Pitch: Sine oscillation around -25 degrees
    freq_p, A_p, offset_p = 0.1, np.radians(10.0), np.radians(-25.0)
    ref_p = A_p * np.sin(2*np.pi*freq_p * t) + offset_p
    ref_p_dot = A_p * (2*np.pi*freq_p) * np.cos(2*np.pi*freq_p * t)
    ref_p_ddot = -A_p * (2*np.pi*freq_p)**2 * np.sin(2*np.pi*freq_p * t)

    # Yaw: Constant rotation (ramp)
    ref_y_dot = np.radians(5.0)
    ref_y = ref_y_dot * t
    ref_y_ddot = 0.0

    return ref_p, ref_p_dot, ref_p_ddot, ref_y, ref_y_dot, ref_y_ddot

def thrust_to_rpm(u_val):
    """Aerodynamic mapping from control torque to motor RPM."""
    deadband = 0.05
    if abs(u_val) < deadband:
        return np.sign(u_val) * (2828.0 * np.sqrt(deadband) / deadband) * abs(u_val)
    return np.sign(u_val) * 2828.0 * np.sqrt(abs(u_val))

def apply_ramp(curr, tar, delta_t, max_slew_rate):
    """Limits how fast the motor speed can change (Slew Rate)."""
    step = max_slew_rate * delta_t
    return curr + np.clip(tar - curr, -step, step)

# ----------------------------
# 4. Controller State & Gains
# ----------------------------
Kp = np.diag([15.0, 0.0, 45.0])
Kd = np.diag([8.0, 0.0, 12.0])
Ki = np.diag([5.0, 0.0, 3.0])

max_slew_rate = 5000.0
current_m0 = 0.0
current_m1 = 0.0
eR_int = np.zeros(3)
prev_p, prev_y = 0.0, 0.0

TR.kf = setup_ahrs_kalman(TR)
start_time = time.time()

# ----------------------------
# 5. Main Control Loop
# ----------------------------
try:
    print("Code 1 Fully Updated with Ramp Function")
    while True:
        t_now = time.time() - start_time
        dt = TR.update_readings()
        if dt <= 0.0001: dt = 0.01

        # State Update
        r, p, y = get_ahrs(dt)
        d_p = normalize_angle(p - prev_p) / dt
        d_y = normalize_angle(y - prev_y) / dt
        Omega = np.array([d_p, d_y * np.sin(p), d_y * np.cos(p)])
        R = compute_R(y, p)

        # Target Reference
        rp, rp_d, rp_dd, ry, ry_d, ry_dd = compute_reference(t_now)
        Rr = compute_R(ry, rp)
        
        # Body-frame Projection of Reference
        Omega_r = np.array([rp_d, ry_d * np.sin(rp), ry_d * np.cos(rp)])
        Pi_dot_r = J @ np.array([rp_dd, ry_dd * np.sin(rp), ry_dd * np.cos(rp)])

        # Tracking Errors
        Re_body = R.T @ Rr
        eR_hat = 0.5 * (Re_body @ Kmat - Kmat @ Re_body.T)
        eR = np.array([eR_hat[2, 1], eR_hat[0, 2], eR_hat[1, 0]])
        
        Omega_r_body = Re_body @ Omega_r
        pi_e = (J @ Omega_r_body) - (J @ Omega)
        
        # Total Control Torque (Feedforward + PID)
        feedforward = (Re_body @ Pi_dot_r) + np.cross(Omega, J @ Omega_r_body)
        eR_int = np.clip(eR_int + eR * dt, -5.0, 5.0)
        
        Tu = feedforward + (Kp @ eR) + (Kd @ pi_e) + (Ki @ eR_int)

        # Motor Allocation
        target_m0 = thrust_to_rpm(-Tu[2]) # Yaw torque to M0
        target_m1 = thrust_to_rpm(Tu[0])  # Pitch torque to M1

        # Apply Slew Rate Limiters
        current_m0 = apply_ramp(current_m0, target_m0, dt, max_slew_rate)
        current_m1 = apply_ramp(current_m1, target_m1, dt, max_slew_rate)

        # Send Commands to Hardware
        TR.motors.set_speed_M0(np.clip(-current_m0, -2000, 2000)) #horizontal motor is M0 in hardware mapping (negative for correct direction)
        TR.motors.set_speed_M1(np.clip(current_m1, -2000, 2000))# vertical motor is M1 in hardware mapping

        prev_p, prev_y = p, y

        print(f"P_Err: {np.degrees(rp-p):.1f} | Y_Err: {np.degrees(ry-y):.1f} | M0: {np.clip(-current_m0, -2000, 2000):.0f} M1: {np.clip(current_m1, -2000, 2000):.0f}", end='\r')
        time.sleep(0.01)

except KeyboardInterrupt:
    print("\nStopping Controller...")
finally:
    TR.motors.stop()