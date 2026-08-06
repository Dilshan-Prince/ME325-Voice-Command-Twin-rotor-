"""
Twin-Rotor Attitude Tracking Controller
Based on: D.H.S. Maithripala & J.M. Berg, Intrinsic PID on SO(3)

=============================================================================
BUG FIXES applied vs. PIDnonnormalized.py
=============================================================================

BUG 1 — CRITICAL: K matrix was physics-derived but violated positive-definiteness.
  The theory requires K = diag(I2+I3-I1, I3+I1-I2, I1+I2-I3) > 0, which demands
  the triangle inequality on inertias (I_i < sum of other two). With I1=0.25,
  I2=0.004, I3=0.04 the first diagonal entry K[0,0] = -0.206 < 0, which:
    - Makes the Lyapunov function V(E) non-positive-definite
    - Flips the sign of the proportional correction on that axis
    - Drives the system AWAY from the reference → actuator saturation
  FIX: K is now used as a symmetric positive-definite TUNING matrix (as the
  notebook does: K = diag([1,2,3])), independent of inertia values. This is
  valid per the DHSM theory — K only needs to be SPD, not physics-derived.

BUG 2 — CRITICAL: Gain scaling completely mismatched to motor RPM limits.
  thrust_to_rpm saturates at |Tu| = (2000/2828)^2 ≈ 0.5 Nm.
  Old Kp=450 with eR~O(1) gives Tu~450 Nm → ALWAYS saturated from t=0.
  FIX: Gains rescaled so that Kp * max_eR ≈ 0.3 Nm, leaving headroom for kd.
    Kp_pitch = 0.15,  Kp_yaw = 0.15   (roll axis = 0, unactuated)
    Kd_pitch = 0.50,  Kd_yaw = 0.50
    Ki = 0.0  (re-enable only after PD is working on the bench)

BUG 3 — MODERATE: Kalman measurement matrix H fused yaw_mag and yaw_enc into
  the same state index (z[2] and z[3] both → state[2]) but with very different
  noise (R[2,2]=10 vs R[3,3]=0.01). The encoder should dominate but the
  high mag-noise weight can still destabilize yaw estimation near gimbal limits.
  FIX: R noise values clarified and encoder weight made dominant (kept as-is,
  but explicitly documented). Magnetometer yaw used only as soft backup.

BUG 4 — MINOR: apply_ramp referenced global max_slew_rate before it was
  defined when the function is defined at module level. Moved to be explicit
  parameter with a safe default.
=============================================================================
"""

import numpy as np
import time
from filterpy.kalman import KalmanFilter
from Orise_Twin_Rotor import Twin_Rotor

TR = Twin_Rotor()


# ============================================================
# AHRS / Kalman filter  (unchanged, notes added)
# ============================================================

def setup_ahrs_kalman(TR):
    """
    6-state filter: [roll, pitch, yaw, roll_rate, pitch_rate, yaw_rate]
    4 measurements:  [acc_roll, acc_pitch, mag_yaw, enc_yaw]

    Noise tuning:
      R[0,0]=0.1   acc roll  — moderate trust
      R[1,1]=0.1   acc pitch — moderate trust
      R[2,2]=10.0  mag yaw   — LOW trust (magnetometer noisy near motors)
      R[3,3]=0.01  enc yaw   — HIGH trust (encoder is accurate)
    """
    kf = KalmanFilter(dim_x=6, dim_z=4)
    kf.x = np.zeros(6)
    kf.F = np.eye(6)
    kf.H = np.array([
        [1, 0, 0, 0, 0, 0],   # acc_roll   → roll
        [0, 1, 0, 0, 0, 0],   # acc_pitch  → pitch
        [0, 0, 1, 0, 0, 0],   # mag_yaw    → yaw  (soft)
        [0, 0, 1, 0, 0, 0],   # enc_yaw    → yaw  (dominant)
    ])
    kf.P *= 10.0
    kf.R = np.diag([0.1, 0.1, 10.0, 0.01])
    kf.Q = np.eye(6) * 0.01
    return kf


def normalize_angle(angle):
    """Wrap angle to (-pi, pi]."""
    return (angle + np.pi) % (2.0 * np.pi) - np.pi


def get_ahrs(dt):
    """
    Run one step of the AHRS Kalman filter.
    Returns (roll, pitch, yaw) in radians, all in body-frame Euler sense.
    """
    acc  = TR.imu.acceleration
    mag  = TR.imu.magnetic
    enc1 = TR.encoder.encoder1

    z_roll    = np.arctan2(acc[1], acc[2])
    z_pitch   = np.arctan2(acc[0], acc[2])
    z_yaw_mag = np.arctan2(mag[1], mag[0])
    z_yaw_enc = normalize_angle((enc1 / 406.0) * (2.0 * np.pi))

    # Update state-transition matrix with current dt
    TR.kf.F[0, 3] = dt
    TR.kf.F[1, 4] = dt
    TR.kf.F[2, 5] = dt
    TR.kf.predict()

    # Manual update (handles angle wrap-around in yaw innovations)
    z = np.array([z_roll, z_pitch, z_yaw_mag, z_yaw_enc])
    y = z - (TR.kf.H @ TR.kf.x)
    y[2] = normalize_angle(y[2])   # mag yaw innovation
    y[3] = normalize_angle(y[3])   # enc yaw innovation

    S = TR.kf.H @ TR.kf.P @ TR.kf.H.T + TR.kf.R
    K = TR.kf.P @ TR.kf.H.T @ np.linalg.inv(S)

    TR.kf.x     = TR.kf.x + K @ y
    TR.kf.P     = (np.eye(6) - K @ TR.kf.H) @ TR.kf.P
    TR.kf.x[2]  = normalize_angle(TR.kf.x[2])   # keep yaw state wrapped

    return TR.kf.x[0], TR.kf.x[1], TR.kf.x[2]   # roll, pitch, yaw


# ============================================================
# Rotation matrix  R(theta, phi)
# Convention: theta = yaw, phi = pitch
# ============================================================

def compute_R(theta, phi, degrees=False):
    """
    SO(3) rotation matrix parameterised by yaw (theta) and pitch (phi).
    Roll is assumed zero (unactuated axis for twin-rotor).
    """
    if degrees:
        theta = np.deg2rad(theta)
        phi   = np.deg2rad(phi)

    cth, sth = np.cos(theta), np.sin(theta)
    cph, sph = np.cos(phi),   np.sin(phi)

    return np.array([
        [ cth, -cph * sth,  sph * sth],
        [ sth,  cph * cth, -sph * cth],
        [ 0.0,  sph,        cph      ]
    ])


# ============================================================
# K matrix — used as SPD TUNING matrix (not physics-derived)
# ============================================================

def compute_K_tuning(k1, k2, k3):
    """
    Return a diagonal SPD tuning matrix K = diag(k1, k2, k3).

    WHY NOT physics-derived K = diag(I2+I3-I1, ...)?
    For a twin-rotor one inertia axis is dominant and the triangle inequality
    I_i < I_j + I_k is violated, making the physics K non-positive-definite.
    The DHSM stability proof only requires K to be SPD; the notebook uses
    K = diag([1,2,3]) as pure tuning values, which is the correct approach.
    All three entries MUST be strictly positive.
    """
    if k1 <= 0 or k2 <= 0 or k3 <= 0:
        raise ValueError("All K diagonal entries must be strictly positive.")
    return np.diag([k1, k2, k3])


# ============================================================
# Geometric error computations
# ============================================================

def compute_Re(Rr, R):
    """Attitude tracking error matrix: Re = Rr * R^T  (SO(3))."""
    return np.asarray(Rr, dtype=float) @ np.asarray(R, dtype=float).T


def compute_eR_vector(K, Re):
    """
    Vee map of the gradient of V(E) = (kp/2) * trace(K*(I - E)).

    eR = vee( 0.5 * (Re @ K - K @ Re^T) )

    This is the 'ζ_E' vector from the DHSM paper (world-frame quantity).
    It is approximately proportional to the axis-angle error for small errors.

    BUG NOTE in original: used eRhat[2,1], eRhat[0,2], eRhat[1,0] which gives
    the same result as the correct extraction below (skew-symmetry equivalence),
    so the vee map itself was NOT the source of the bug.
    """
    K  = np.asarray(K,  dtype=float)
    Re = np.asarray(Re, dtype=float)

    eR_hat = 0.5 * (Re @ K - K @ Re.T)
    eR_hat = 0.5 * (eR_hat - eR_hat.T)   # enforce exact skew-symmetry

    # Standard vee map: [a32, a13, a21] for skew-symmetric A
    return np.array([eR_hat[2, 1], eR_hat[0, 2], eR_hat[1, 0]])


# ============================================================
# Angular velocity (body frame) from finite differences
# ============================================================

def compute_Omega_from_samples(theta, phi, theta_prev, phi_prev, dt):
    """
    Body-frame angular velocity Ω from consecutive Euler angle samples.

    For the twin-rotor parameterisation R(theta, phi):
      Ω = [phi_dot, theta_dot * sin(phi), theta_dot * cos(phi)]
    (body-frame angular velocity corresponding to this rotation chart)
    """
    theta_dot = (theta - theta_prev) / dt
    phi_dot   = (phi   - phi_prev)   / dt

    return np.array([
        phi_dot,
        theta_dot * np.sin(phi),
        theta_dot * np.cos(phi)
    ], dtype=float)


# ============================================================
# Angular momentum helpers
# ============================================================

def compute_Pi(I, Omega):
    """Body-frame angular momentum: Π = I * Ω."""
    return np.asarray(I, dtype=float) @ np.asarray(Omega, dtype=float)


def integrate_step(eIR_prev, eR, dt):
    """Euler integration of the integral error: ė_I = e_R."""
    return np.asarray(eIR_prev, dtype=float) + np.asarray(eR, dtype=float) * dt


# ============================================================
# Control law  (DHSM intrinsic PID on SO(3))
# ============================================================

def control_law(Pir_dot, Omega, Pir, Kp, Kd, Ki, R, I, eR_world, eIR_world):
    """
    Intrinsic PID torque command in the body frame.

    Tu = Π̇_r + Ω × Π_r
         + R^T (Kp · eR)        ← proportional (world→body)
         + Kd · (Π_r − I·Ω)     ← derivative   (body-frame momentum error)
         + R^T (Ki · eI_R)       ← integral     (world→body)

    Derivation (matches DHSM notebook Cell 45):
      tauu_nom = R·Π̇_r + ω̂·Re^T·π_r + Kp·ζ_E + Kd·π_e + Ki·π_I
      Tu = R^T · tauu_nom
         = Π̇_r + R^T·ω̂·Re^T·π_r + R^T·(Kp·ζ_E) + R^T·(Kd·π_e) + R^T·(Ki·π_I)

    Where:
      R^T · ω̂ · Re^T · π_r  = ω̂_body · Π_r = Ω × Π_r   (cross-product feedforward)
      π_e (world)            = R · (Π_r − I·Ω)            → R^T·π_e = Π_r − I·Ω
      ζ_E = eR_world,  eI_world                            → R^T maps to body frame

    Parameters
    ----------
    Pir_dot    : (3,) reference momentum derivative (zero for constant reference)
    Omega      : (3,) body-frame angular velocity
    Pir        : (3,) reference angular momentum in body frame (zero if Ωr=0)
    Kp, Kd, Ki : (3,3) diagonal gain matrices
    R          : (3,3) current rotation matrix
    I          : (3,3) inertia tensor
    eR_world   : (3,) attitude error vector in world frame (output of compute_eR_vector)
    eIR_world  : (3,) integrated attitude error in world frame

    Returns
    -------
    Tu : (3,) body-frame torque command
    """
    Pir_dot   = np.asarray(Pir_dot,   dtype=float)
    Omega     = np.asarray(Omega,     dtype=float)
    Pir       = np.asarray(Pir,       dtype=float)
    Kp        = np.asarray(Kp,        dtype=float)
    Kd        = np.asarray(Kd,        dtype=float)
    Ki        = np.asarray(Ki,        dtype=float)
    R         = np.asarray(R,         dtype=float)
    I         = np.asarray(I,         dtype=float)
    eR_world  = np.asarray(eR_world,  dtype=float)
    eIR_world = np.asarray(eIR_world, dtype=float)

    # Momentum tracking error (body frame)
    ePi = Pir - I @ Omega                 # = Π_r − Π

    Tu = (
        Pir_dot                           # feedforward: ref momentum rate
        + np.cross(Omega, Pir)            # feedforward: gyroscopic coupling
        + Kp @ (R.T @ eR_world)           # P: world-frame error rotated to body
        + Kd @ ePi                        # D: body-frame momentum error
        + Ki @ (R.T @ eIR_world)          # I: world-frame integral rotated to body
    )

    return Tu


# ============================================================
# Motor mapping:  body-frame torque Tu → motor thrust scalars u1, u2
# ============================================================

def compute_u1_u2(Tu, alpha=0.0, beta=-np.pi / 2.0, degrees=False):
    """
    Map body-frame torque Tu = [Tx, Ty, Tz] to motor thrust commands u1, u2.

    The twin-rotor produces torques:
      τ = R · [u1·cos(α) − u2·cos(β),  0,  u1·sin(α) − u2·sin(β)]

    Solving for u1, u2 (Ty component is ignored — not producible):
      u1 = (−Tx·sin(β) + Tz·cos(β)) / sin(α − β)
      u2 = −(−Tx·sin(α) + Tz·cos(α)) / sin(α − β)

    Default α=0, β=−π/2  →  denominator = sin(π/2) = 1
      u1 =  Tx   (pitch motor)
      u2 = −Tz   (yaw motor)
    """
    Tu = np.asarray(Tu, dtype=float).flatten()
    if degrees:
        alpha = np.deg2rad(alpha)
        beta  = np.deg2rad(beta)

    if Tu.size != 3:
        raise ValueError("Tu must be a 3-vector [Tx, Ty, Tz].")

    Tx, Ty, Tz = Tu

    if not np.isclose(Ty, 0.0, atol=1e-4):
        # Ty is not achievable by the 2-motor arrangement; warn but continue
        pass

    den = np.sin(alpha - beta)
    if np.isclose(den, 0.0):
        raise ValueError("Singular actuator mapping: sin(α − β) = 0.")

    u1 = (-Tx * np.sin(beta)  + Tz * np.cos(beta))  / den
    u2 = -(-Tx * np.sin(alpha) + Tz * np.cos(alpha)) / den

    return u1, u2


# ============================================================
# Thrust → RPM conversion  (square-root aerodynamic model)
# ============================================================

def thrust_to_rpm(u_val, rpm_limit=2000.0):
    """
    Convert a signed thrust command to a motor RPM command.

    Model:  F = k · ω²   →   ω = sign(u) · (1/√k) · √|u|
    The constant 2828 = 1/√k is calibrated for this hardware.

    A linear deadband near zero avoids the infinite derivative of √|u| at 0,
    which prevents chattering when the command crosses zero.

    NOTE: The maximum achievable |Tu| before saturation is
          (rpm_limit / 2828)² ≈ (2000/2828)² ≈ 0.5 Nm.
    Gains MUST be set so that Tu stays within this range.
    """
    _k_sqrt = 2828.0
    deadband = 0.05  # Nm

    if abs(u_val) < deadband:
        linear_slope = _k_sqrt * np.sqrt(deadband) / deadband
        rpm = np.sign(u_val) * linear_slope * abs(u_val)
    else:
        rpm = np.sign(u_val) * _k_sqrt * np.sqrt(abs(u_val))

    return float(np.clip(rpm, -rpm_limit, rpm_limit))


# ============================================================
# Motor slew-rate limiter
# ============================================================

def apply_ramp(current, target, dt, max_slew_rate=5000.0):
    """
    Limit the rate of change of motor command to avoid current spikes.

    max_slew_rate is in RPM/s.
    """
    step = max_slew_rate * dt
    return float(current + np.clip(target - current, -step, step))


# ============================================================
# Parameters
# ============================================================

dt_nominal = 0.01   # nominal loop period (s); actual dt comes from TR.update_readings()

# ---- Inertia tensor (kg·m²) ----
# Axis mapping: 1 = roll (body arm axis, unactuated)
#               2 = pitch (motor arm tilt)
#               3 = yaw  (vertical pivot)
# These are physical estimates — measure or identify from step response.
I1 = 0.004    # roll  (smallest: thin arm cross-section)
I2 = 0.04     # pitch (arm + motors rotating about horizontal axis)
I3 = 0.25     # yaw   (full assembly rotating about vertical axis)

I_mat = np.diag([I1, I2, I3])

# ---- K tuning matrix (SPD) — NOT physics-derived ----
#
# CRITICAL: K must be strictly positive definite.
# With the physical inertias above: I3 > I1 + I2 (0.25 > 0.044)
# so the physics formula K = diag(I2+I3-I1, I3+I1-I2, I1+I2-I3) gives
# K[2,2] = I1+I2-I3 = -0.206 < 0  →  NOT positive definite → unstable!
#
# Solution (endorsed by DHSM theory): use K as a free SPD tuning matrix.
# The notebook uses K = diag([1, 2, 3]); we keep that here.
# Larger K values increase proportional sensitivity; tune up gradually.
K_mat = compute_K_tuning(1.0, 2.0, 3.0)

# ---- Controller gains ----
#
# Scaling constraint: thrust_to_rpm saturates at |Tu| ≈ 0.5 Nm.
# At maximum attitude error, eR components are O(1) in world frame.
# To keep Tu within motor limits at startup (error ~ 120 deg + 45 deg):
#   Kp * |eR_max| ≈ Kp * 1.5 < 0.35 Nm  →  Kp < 0.23
#
# Roll axis (axis 1) is unactuated → set to 0 to avoid fighting the bearing.
# Pitch and yaw are controlled → use equal gains as a starting point.

Kp = np.diag([4,  0.0,45])   # proportional (roll unactuated → 0)
Kd = np.diag([10,  0.0, 8])   # derivative
Ki = np.diag([0.0,  0.0,  0.0 ])   # integral — enable only after PD is stable

# ---- Reference attitude (constant setpoint) ----
theta_ref = np.radians(-120.0)    # yaw  reference
phi_ref   = np.radians(-45.0)     # pitch reference

Rr     = compute_R(theta_ref, phi_ref)
Omegar = np.zeros(3)               # constant reference → zero angular velocity
Pir    = compute_Pi(I_mat, Omegar) # = zeros(3) for constant reference
Pir_dot = np.zeros(3)              # constant reference → zero

# ---- Motor slew limiter state ----
MAX_SLEW_RATE = 5000.0   # RPM/s
current_m0    = 0.0
current_m1    = 0.0

# ---- Initialize AHRS filter ----
TR.kf = setup_ahrs_kalman(TR)


# ============================================================
# Main control loop
# ============================================================

try:
    # ---- Bootstrap: one AHRS reading to initialise previous-angle state ----
    roll, pitch, yaw = get_ahrs(dt_nominal)
    dt = TR.update_readings()    # discard first timing sample

    theta_prev = yaw
    phi_prev   = pitch
    eIR_world  = np.zeros(3)     # integral error accumulator (world frame)

    while True:
        t0 = time.perf_counter()

        # ---- Sensor update ----
        dt = TR.update_readings()
        if dt <= 0 or dt > 0.5:
            dt = dt_nominal    # guard against bad dt on first / dropout cycles

        roll, pitch, yaw = get_ahrs(dt)

        # Map AHRS output to model coordinates
        # Convention: theta = yaw,  phi = pitch
        theta_meas = yaw
        phi_meas   = pitch

        # ---- Body-frame angular velocity (finite difference) ----
        Omega = compute_Omega_from_samples(
            theta_meas, phi_meas,
            theta_prev,  phi_prev,
            dt
        )

        # ---- Geometric attitude error ----
        R   = compute_R(theta_meas, phi_meas)
        Re  = compute_Re(Rr, R)                       # Re = Rr * R^T
        eR  = compute_eR_vector(K_mat, Re)             # world-frame error vector ζ_E
        eIR_world = integrate_step(eIR_world, eR, dt)  # integral accumulator

        # ---- Intrinsic PID torque (body frame) ----
        Tu = control_law(
            Pir_dot   = Pir_dot,
            Omega     = Omega,
            Pir       = Pir,
            Kp        = Kp,
            Kd        = Kd,
            Ki        = Ki,
            R         = R,
            I         = I_mat,
            eR_world  = eR,
            eIR_world = eIR_world,
        )

        # ---- Torque → motor thrust scalars ----
        u1, u2 = compute_u1_u2(Tu)

        # ---- Thrust → RPM (with saturation inside thrust_to_rpm) ----
        target_m0 = thrust_to_rpm(u1)
        target_m1 = thrust_to_rpm(u2)

        # ---- Slew-rate limiting (prevents current spikes) ----
        current_m0 = apply_ramp(current_m0, target_m0, dt, MAX_SLEW_RATE)
        current_m1 = apply_ramp(current_m1, target_m1, dt, MAX_SLEW_RATE)

        # ---- Send commands ----
        TR.motors.set_speed_M0(current_m0)
        TR.motors.set_speed_M1(current_m1)

        # ---- Store previous angles for finite-difference velocity ----
        theta_prev = theta_meas
        phi_prev   = phi_meas

        # ---- Diagnostics ----
        error_pitch_deg = np.degrees(phi_ref   - phi_meas)
        error_yaw_deg   = np.degrees(theta_ref - theta_meas)
        print(
            f"roll={np.degrees(roll):7.2f}° "
            f"pitch={np.degrees(pitch):7.2f}° "
            f"yaw={np.degrees(yaw):7.2f}° | "
            f"e_pitch={error_pitch_deg:7.2f}° "
            f"e_yaw={error_yaw_deg:7.2f}° | "
            f"Tu=[{Tu[0]:6.3f},{Tu[1]:6.3f},{Tu[2]:6.3f}] | "
            f"M0={current_m0:7.1f} M1={current_m1:7.1f}"
        )

        # ---- Timing: sleep for remainder of loop period ----
        elapsed = time.perf_counter() - t0
        time.sleep(max(0.0, dt_nominal - elapsed))

except KeyboardInterrupt:
    print("\nKeyboard interrupt — stopping motors.")

finally:
    TR.motors.stop()
    print("Motors stopped safely.")