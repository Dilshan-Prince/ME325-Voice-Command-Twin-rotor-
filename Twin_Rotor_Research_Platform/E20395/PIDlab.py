import numpy as np
import csv
import time
from filterpy.kalman import KalmanFilter
from Orise_Twin_Rotor import Twin_Rotor
from time import sleep
TR = Twin_Rotor()
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

def get_ahrs(dt):
        acc = TR.imu.acceleration
        mag = TR.t.imu.magnetic
        enc1 = TR.t.encoder.encoder1
        
        z_roll = np.arctan2(acc[1], acc[2])
        z_pitch = np.arctan2(acc[0], acc[2])
        z_yaw_mag = np.arctan2(mag[1], mag[0])
        z_yaw_enc = TR.normalize_angle((enc1 / 406.0) * (2.0 * np.pi))
        
        TR.kf.F[0, 3] = TR.kf.F[1, 4] = TR.kf.F[2, 5] = dt
        TR.kf.predict()

        z = np.array([z_roll, z_pitch, z_yaw_mag, z_yaw_enc])
        y = z - np.dot(TR.kf.H, TR.kf.x)
        y[2:] = [TR.normalize_angle(val) for val in y[2:]]

        S = np.dot(TR.kf.H, np.dot(TR.kf.P, TR.kf.H.T)) + TR.kf.R
        K = np.dot(TR.kf.P, np.dot(TR.kf.H.T, np.linalg.inv(S)))
        
        TR.kf.x += np.dot(K, y)
        TR.kf.P = np.dot(np.eye(6) - np.dot(K, TR.kf.H), TR.kf.P)
        return TR.kf.x[0], TR.kf.x[1], TR.kf.x[2]

dt = 0.01
T = 10
t = np.arange(0, T, dt)

I1 = 0.025   # example
I2 = 0.004
I3 = 0.008

Kp = np.diag([15.0, 0.0, 45.0])
Kd = np.diag([10.0, 0.0, 12.0])
Ki = np.diag([5.0, 0.0, 3.0])

I = np.diag([I1, I2, I3])

phi=np.pi/4
theta=np.pi/4
import numpy as np

def compute_Re(Rr, R):
    Rr = np.asarray(Rr, dtype=float)
    R  = np.asarray(R, dtype=float)

    RT = R.T
    Re = Rr @ RT
    return Re

def compute_K(I):
    """
    Compute K from inertia input I.

    Accepted input:
    1. I = [I1, I2, I3]
    2. I = 3x3 diagonal inertia matrix

    Returns:
        K = 3x3 diagonal matrix
    """
    I = np.array(I, dtype=float)

    # Case 1: input as [I1, I2, I3]
    if I.shape == (3,):
        I1, I2, I3 = I

    # Case 2: input as 3x3 matrix
    elif I.shape == (3, 3):
        I1, I2, I3 = np.diag(I)

        # optional check: ensure matrix is diagonal
        if not np.allclose(I, np.diag(np.diag(I))):
            raise ValueError("Input inertia matrix must be diagonal in principal axes form.")
    else:
        raise ValueError("Input must be either [I1, I2, I3] or a 3x3 diagonal matrix.")

    K = np.diag([
        I2 + I3 - I1,
        I3 + I1 - I2,
        I1 + I2 - I3
    ])

    return K


def compute_R(theta, phi, degrees=False):
    """
    Compute rotation matrix R from theta and phi.

    Parameters
    ----------
    theta : float
        Angle theta
    phi : float
        Angle phi
    degrees : bool
        If True, theta and phi are given in degrees

    Returns
    -------
    R : (3,3) ndarray
        Rotation matrix
    """
    if degrees:
        theta = np.deg2rad(theta)
        phi = np.deg2rad(phi)

    cth = np.cos(theta)
    sth = np.sin(theta)
    cph = np.cos(phi)
    sph = np.sin(phi)

    R = np.array([
        [cth,      -cph * sth,   sph * sth],
        [sth,       cph * cth,  -sph * cth],
        [0.0,       sph,         cph      ]
    ])

    return R



def compute_Omega(theta_array, phi_array, dt):
    theta_array = np.asarray(theta_array, dtype=float)
    phi_array   = np.asarray(phi_array, dtype=float)

    theta_dot = np.gradient(theta_array, dt)
    phi_dot   = np.gradient(phi_array, dt)

    Omega = np.column_stack((
        phi_dot,
        theta_dot * np.sin(phi_array),
        theta_dot * np.cos(phi_array)
    ))

    return Omega
def compute_Pi(I, Omega):
    I = np.asarray(I, dtype=float)
    Omega = np.asarray(Omega, dtype=float)
    return I @ Omega

def compute_eR_vector(K, Re):
    K = np.asarray(K, dtype=float)
    Re = np.asarray(Re, dtype=float)

    eR_hat = 0.5 * (Re @ K - K @ Re.T)

    return np.array([
        eR_hat[2, 1],
        eR_hat[0, 2],
        eR_hat[1, 0]
    ])

def compute_u1_u2(Tu, alpha=0.0, beta=-np.pi/2, degrees=False):
    """
    Compute u1 and u2 from
        Tu = [u1*cos(alpha) - u2*cos(beta), 0, u1*sin(alpha) - u2*sin(beta)]

    Parameters
    ----------
    Tu : array-like
        Torque vector [Tx, Ty, Tz] or [Tx, Tz]
    alpha : float
        Angle alpha, default 0
    beta : float
        Angle beta, default -pi/2
    degrees : bool
        If True, alpha and beta are given in degrees

    Returns
    -------
    u1, u2 : float
    """
    Tu = np.asarray(Tu, dtype=float).flatten()

    if degrees:
        alpha = np.deg2rad(alpha)
        beta = np.deg2rad(beta)

    if Tu.size == 3:
        Tx = Tu[0]
        Ty = Tu[1]
        Tz = Tu[2]

        if not np.isclose(Ty, 0.0):
            raise ValueError("This model requires Tu[1] = 0.")
    elif Tu.size == 2:
        Tx, Tz = Tu
    else:
        raise ValueError("Tu must be [Tx, Ty, Tz] or [Tx, Tz].")

    den = np.sin(alpha - beta)

    if np.isclose(den, 0.0):
        raise ValueError("No unique solution because sin(alpha - beta) = 0.")

    u1 = (-Tx * np.sin(beta) + Tz * np.cos(beta)) / den
    u2 = (-Tx * np.sin(alpha) + Tz * np.cos(alpha)) / den

    return u1, u2
import numpy as np

def integrate(eR, dt):
    """
    Cumulative integral of eR over time.

    Parameters
    ----------
    eR : array_like
        Error vector over time.
        Shape can be:
        - (N,)   for scalar signal
        - (N,3)  for vector signal
    dt : float
        Constant time step

    Returns
    -------
    eIR : ndarray
        Time integral of eR with the same shape as eR
    """
    eR = np.asarray(eR, dtype=float)
    eIR = np.cumsum(eR, axis=0) * dt
    return eIR

import numpy as np

def controll_law(Pir_dot, Omega, Pir, kp, kd, ki, R, I, er, eir):
    """
    Compute control torque Tu from

    Tu = (Pir_dot + Omega x Pir)
         + kp * R^T * er
         + kd * (Pir - I*Omega)
         + ki * R^T * eir

    Parameters
    ----------
    Pir_dot : array_like, shape (3,)
        Time derivative of reference momentum
    Omega : array_like, shape (3,)
        Angular velocity vector
    Pir : array_like, shape (3,)
        Reference momentum vector
    kp, kd, ki : float
        Control gains
    R : array_like, shape (3,3)
        Rotation matrix
    I : array_like, shape (3,3)
        Inertia matrix
    er : array_like, shape (3,)
        Attitude error vector
    eir : array_like, shape (3,)
        Integral attitude error vector

    Returns
    -------
    Tu : ndarray, shape (3,)
        Control input torque vector
    """
    Pir_dot = np.asarray(Pir_dot, dtype=float)
    Omega   = np.asarray(Omega, dtype=float)
    Pir     = np.asarray(Pir, dtype=float)
    R       = np.asarray(R, dtype=float)
    I       = np.asarray(I, dtype=float)
    er      = np.asarray(er, dtype=float)
    eir     = np.asarray(eir, dtype=float)

    Tu = (
        Pir_dot
        + np.cross(Omega, Pir)
        + kp * (R.T @ er)
        + kd * (Pir - I @ Omega)
        + ki * (R.T @ eir)
    )

    return Tu



while true:
    roll, pitch, yaw = get_ahrs(dt)

    print(roll,pitch,yaw)

    Rr=compute_R(theta, phi)
    Omegar=compute_Omega(theta, phi, dt)
    Omega=compute_Omega(yaw,pitch,dt)
    Pir=compute_Pi(I, Omegar)
    Pir_dot=np.gradient(Pir, dt, axis=0) 
    R= compute_R(yaw,pitch)
    Re= compute_Re(Rr,R)
    eR=compute_eR_vector(compute_K(I), Rr)
    eIR=integrate(eR, dt)
    Tu=controll_law(Pir_dot, Omega, Pir, Kp, Kd, Ki, R, I, eR, eIR)
    u1,u2 = compute_u1_u2(Tu)


    #before give u1 and u2 to the motores give for limit <5000
    TR.motors.set_speed_M0(u1)
    TR.motors.set_speed_M1(u2)

