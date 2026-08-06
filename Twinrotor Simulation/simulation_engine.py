import meshcat
import meshcat.geometry as g
import meshcat.transformations as tf
import meshcat_shapes
import numpy as np
import time
import webbrowser
import threading

class TwinRotorSimulation:
    def __init__(self):
        # Initialize the MeshCat visualizer server
        self.vis = meshcat.Visualizer()
        url = self.vis.url()
        print(f"\n========================================================")
        print(f"MeshCat Server active! Open this URL in your browser:\n-> {url}")
        print(f"========================================================\n")
        
        # Auto-open the visualizer in the default browser
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f"[Warning] Failed to auto-open browser: {e}")
            
        self.lock = threading.RLock()
        self.is_animating = False
        self.awaiting_authorization = False
        self._current_pitch = 0.0
        self._current_yaw = 0.0

        # Physical/State variables for dynamic simulation
        self.pitch_rate = 0.0
        self.yaw_rate = 0.0
        self.motor0_rpm = 0.0
        self.motor1_rpm = 0.0
        
        self.sim_pwm1 = 1500
        self.sim_pwm2 = 1500
        self.sim_psi = 0.0

        # Propeller rotation angles
        self.left_prop_angle = 0.0
        self.right_prop_angle = 0.0

        # Text overlay visualizer node (positioned above left base)
        self.text_handle = self.vis["text_overlay"]
        self.text_handle.set_transform(tf.translation_matrix([-0.5, 0.4, 0.45]))

        self.setup_environment()
        self.current_pitch = 0.0
        self.current_yaw = 0.0

    @property
    def current_pitch(self):
        return self._current_pitch

    @current_pitch.setter
    def current_pitch(self, val):
        with self.lock:
            self._current_pitch = val
            self.update_beam_transform()
            p = np.radians(val)
            R_base = tf.rotation_matrix(-np.pi/2, [0, 0, 1])
            self.vis["pitch_indicator/arrow"].set_transform(
                tf.translation_matrix([0, 0.1, 0]) @ tf.rotation_matrix(p, [0, 1, 0]) @ R_base
            )
            self.update_text_overlay()

    @property
    def current_yaw(self):
        return self._current_yaw

    @current_yaw.setter
    def current_yaw(self, val):
        with self.lock:
            self._current_yaw = val
            self.update_beam_transform()
            y = np.radians(val)
            R_base = tf.rotation_matrix(-np.pi/2, [0, 0, 1])
            self.vis["yaw_indicator/arrow"].set_transform(
                tf.translation_matrix([0, 0, -0.08]) @ tf.rotation_matrix(y, [0, 0, 1]) @ R_base
            )
            self.update_text_overlay()

    def update_text_overlay(self):
        text_str = f"Pitch: {self._current_pitch:.1f}°\nYaw: {self._current_yaw:.1f}°"
        meshcat_shapes.textarea(self.text_handle, text_str, width=0.45, height=0.25, font_size=36)

    def update_beam_transform(self):
        with self.lock:
            p = np.radians(self._current_pitch)
            y = np.radians(self._current_yaw)
            r = 0.0
            R_yaw = tf.rotation_matrix(y, [0, 0, 1])
            R_pitch = tf.rotation_matrix(p, [0, 1, 0])
            R_roll = tf.rotation_matrix(r, [1, 0, 0])
            self.vis["base/beam"].set_transform(R_yaw @ R_pitch @ R_roll)

    def setup_arrow(self, path, length=0.2, color=0xffff00):
        head_length = length * 0.25
        shaft_length = length - head_length
        shaft_radius = length * 0.04
        head_radius = length * 0.1
        
        # Shaft: Cylinder along Y axis
        self.vis[path + "/shaft"].set_object(
            g.Cylinder(height=shaft_length, radius=shaft_radius),
            g.MeshLambertMaterial(color=color)
        )
        self.vis[path + "/shaft"].set_transform(tf.translation_matrix([0, shaft_length / 2, 0]))
        
        # Head: Cone along Y axis (using Cylinder with radiusTop=0.0)
        self.vis[path + "/head"].set_object(
            g.Cylinder(height=head_length, radiusBottom=head_radius, radiusTop=0.0),
            g.MeshLambertMaterial(color=color)
        )
        self.vis[path + "/head"].set_transform(tf.translation_matrix([0, shaft_length + head_length / 2, 0]))

    def setup_environment(self):
        # 1. Create a static base (Beige rectangular box)
        self.vis["base_box"].set_object(g.Box([0.5, 0.5, 0.15]), 
                                        g.MeshLambertMaterial(color=0xe5e5e0))
        self.vis["base_box"].set_transform(tf.translation_matrix([0, 0, -0.4]))
        
        # 2. Vertical Tower Column (Dark gray cylinder)
        self.vis["tower"].set_object(g.Cylinder(height=0.5, radius=0.03), 
                                     g.MeshLambertMaterial(color=0x222222))
        self.vis["tower"].set_transform(tf.translation_matrix([0, 0, -0.15]) @ tf.rotation_matrix(np.pi/2, [1, 0, 0]))

        # 3. Pivot Joint (at the top of the tower)
        self.vis["base"].set_object(g.Cylinder(height=0.08, radius=0.04), 
                                    g.MeshLambertMaterial(color=0x555555))
        
        # 4. Main Beam assembly (Silver cylinder rod rotated along X-axis)
        self.vis["base/beam/rod"].set_object(g.Cylinder(height=0.8, radius=0.01), 
                                             g.MeshLambertMaterial(color=0xdddddd))
        self.vis["base/beam/rod"].set_transform(tf.rotation_matrix(np.pi/2, [0, 0, 1]))
        
        # 5. Counterweight assembly
        self.vis["base/beam/counterweight_rod"].set_object(g.Cylinder(height=0.25, radius=0.005), 
                                                           g.MeshLambertMaterial(color=0xcccccc))
        self.vis["base/beam/counterweight_rod"].set_transform(tf.translation_matrix([0, 0, -0.125]) @ tf.rotation_matrix(np.pi/2, [1, 0, 0]))
        
        self.vis["base/beam/counterweight_mass"].set_object(g.Cylinder(height=0.05, radius=0.02), 
                                                            g.MeshLambertMaterial(color=0x888888))
        self.vis["base/beam/counterweight_mass"].set_transform(tf.translation_matrix([0, 0, -0.23]) @ tf.rotation_matrix(np.pi/2, [1, 0, 0]))

        # 6. Left Rotor Shroud & Spokes (Tail Rotor)
        for i in range(12):
            angle = i * (2.0 * np.pi / 12.0)
            x_local = -0.38 + 0.11 * np.cos(angle)
            y_local = 0.0
            z_local = 0.11 * np.sin(angle)
            R_seg = tf.rotation_matrix(angle + np.pi/2, [0, 1, 0])
            self.vis[f"base/beam/left_shroud_seg_{i}"].set_object(
                g.Box([0.06, 0.03, 0.005]),
                g.MeshLambertMaterial(color=0xcccccc)
            )
            self.vis[f"base/beam/left_shroud_seg_{i}"].set_transform(
                tf.translation_matrix([x_local, y_local, z_local]) @ R_seg
            )
        
        self.vis["base/beam/left_spoke_v"].set_object(g.Box([0.004, 0.01, 0.22]), g.MeshLambertMaterial(color=0x888888))
        self.vis["base/beam/left_spoke_v"].set_transform(tf.translation_matrix([-0.38, 0, 0]))
        self.vis["base/beam/left_spoke_h"].set_object(g.Box([0.22, 0.01, 0.004]), g.MeshLambertMaterial(color=0x888888))
        self.vis["base/beam/left_spoke_h"].set_transform(tf.translation_matrix([-0.38, 0, 0]))

        self.vis["base/beam/left_hub"].set_object(g.Cylinder(height=0.03, radius=0.025), g.MeshLambertMaterial(color=0x888888))
        self.vis["base/beam/left_hub"].set_transform(tf.translation_matrix([-0.38, 0, 0]) @ tf.rotation_matrix(np.pi/2, [1, 0, 0]))

        self.vis["base/beam/left_prop/blade"].set_object(
            g.Box([0.18, 0.012, 0.003]),
            g.MeshLambertMaterial(color=0xff1111)
        )

        # 7. Right Rotor Shroud & Spokes (Main Rotor)
        for i in range(12):
            angle = i * (2.0 * np.pi / 12.0)
            x_local = 0.38 + 0.14 * np.cos(angle)
            y_local = 0.14 * np.sin(angle)
            z_local = 0.0
            R_seg = tf.rotation_matrix(angle + np.pi/2, [0, 0, 1])
            self.vis[f"base/beam/right_shroud_seg_{i}"].set_object(
                g.Box([0.075, 0.005, 0.04]),
                g.MeshLambertMaterial(color=0x222222)
            )
            self.vis[f"base/beam/right_shroud_seg_{i}"].set_transform(
                tf.translation_matrix([x_local, y_local, z_local]) @ R_seg
            )
            
        self.vis["base/beam/right_spoke_x"].set_object(g.Box([0.28, 0.004, 0.004]), g.MeshLambertMaterial(color=0xcccccc))
        self.vis["base/beam/right_spoke_x"].set_transform(tf.translation_matrix([0.38, 0, 0]))
        self.vis["base/beam/right_spoke_y"].set_object(g.Box([0.004, 0.28, 0.004]), g.MeshLambertMaterial(color=0xcccccc))
        self.vis["base/beam/right_spoke_y"].set_transform(tf.translation_matrix([0.38, 0, 0]))

        self.vis["base/beam/right_hub"].set_object(g.Cylinder(height=0.04, radius=0.03), g.MeshLambertMaterial(color=0x222222))
        self.vis["base/beam/right_hub"].set_transform(tf.translation_matrix([0.38, 0, -0.01]))

        self.vis["base/beam/right_prop/blade"].set_object(
            g.Box([0.24, 0.015, 0.003]),
            g.MeshLambertMaterial(color=0xff1111)
        )

        # 8. Create Pitch & Yaw Indicators (dials and arrows)
        theta = np.linspace(0, 2 * np.pi, 100)
        
        # Pitch Dial (Circle in X-Z plane, Y is normal)
        pitch_dial_points = 0.2 * np.vstack([np.cos(theta), np.zeros_like(theta), np.sin(theta)])
        self.vis["pitch_indicator/dial"].set_object(
            g.LineLoop(g.PointsGeometry(pitch_dial_points), g.LineBasicMaterial(color=0x888888))
        )
        self.vis["pitch_indicator/dial"].set_transform(tf.translation_matrix([0, 0.1, 0]))
        
        # Static Pitch Reference Arrow (0 degrees, pointing along +X)
        self.setup_arrow("pitch_indicator/ref_arrow", length=0.2, color=0x555555)
        R_base = tf.rotation_matrix(-np.pi/2, [0, 0, 1])
        self.vis["pitch_indicator/ref_arrow"].set_transform(tf.translation_matrix([0, 0.1, 0]) @ R_base)
        
        # Rotating Pitch Arrow
        self.setup_arrow("pitch_indicator/arrow", length=0.2, color=0xffff00)
        self.vis["pitch_indicator/arrow"].set_transform(tf.translation_matrix([0, 0.1, 0]) @ R_base)
        
        # Yaw Dial (Circle in X-Y plane, Z is normal)
        yaw_dial_points = 0.3 * np.vstack([np.cos(theta), np.sin(theta), np.zeros_like(theta)])
        self.vis["yaw_indicator/dial"].set_object(
            g.LineLoop(g.PointsGeometry(yaw_dial_points), g.LineBasicMaterial(color=0x888888))
        )
        self.vis["yaw_indicator/dial"].set_transform(tf.translation_matrix([0, 0, -0.08]))
        
        # Static Yaw Reference Arrow (0 degrees, pointing along +X)
        self.setup_arrow("yaw_indicator/ref_arrow", length=0.3, color=0x555555)
        self.vis["yaw_indicator/ref_arrow"].set_transform(tf.translation_matrix([0, 0, -0.08]) @ R_base)
        
        # Rotating Yaw Arrow
        self.setup_arrow("yaw_indicator/arrow", length=0.3, color=0x00ff00)
        self.vis["yaw_indicator/arrow"].set_transform(tf.translation_matrix([0, 0, -0.08]) @ R_base)

    @staticmethod
    def compute_R(theta, phi):
        cth = np.cos(theta)
        sth = np.sin(theta)
        cph = np.cos(phi)
        sph = np.sin(phi)
        return np.array([
            [cth,      -cph * sth,   sph * sth],
            [sth,       cph * cth,  -sph * cth],
            [0.0,       sph,         cph]
        ])

    @staticmethod
    def compute_K(I):
        I1, I2, I3 = np.diag(I)
        return np.diag([
            I2 + I3 - I1,
            I3 + I1 - I2,
            I1 + I2 - I3
        ])

    @staticmethod
    def thrust_to_rpm(u_val):
        deadband = 0.05
        if abs(u_val) < deadband:
            linear_slope = 2828.0 * np.sqrt(deadband) / deadband
            return np.sign(u_val) * linear_slope * abs(u_val)
        else:
            return np.sign(u_val) * 2828.0 * np.sqrt(abs(u_val))

    @staticmethod
    def apply_ramp(curr, tar, delta_t, max_slew_rate):
        step = max_slew_rate * delta_t
        return curr + np.clip(tar - curr, -step, step)

    def compute_step(self, target_pitch_deg, target_yaw_deg, dt):
        """
        Integrates the system state for a time step dt using 2-DOF MIMO rigid-body dynamics
        and the tracking controller.
        """
        # Convert target and current angles to radians for calculation
        phi = np.radians(self.current_pitch)
        theta = np.radians(self.current_yaw)
        
        target_pitch_rad = np.radians(target_pitch_deg)
        target_yaw_rad = np.radians(target_yaw_deg)
        
        # Parameters from e21100.py
        I1 = 0.07
        I2 = 0.01222
        I3 = 0.07
        I = np.diag([I1, I2, I3])
        Kmat = self.compute_K(I)

        Kp = np.diag([50.0, 0.0, 8.0])
        Kd = np.diag([40.0, 0.0, 5.0])
        
        # 1. Tracking controller
        R = self.compute_R(theta, phi)
        Omega = np.array([self.pitch_rate, self.yaw_rate * np.sin(phi), self.yaw_rate * np.cos(phi)])
        
        Rr = self.compute_R(target_yaw_rad, target_pitch_rad)
        
        Re_body = R.T @ Rr
        
        # Compute geometric attitude error Psi ∈ [0, 2]
        self.sim_psi = float(0.5 * (3.0 - np.trace(Re_body)))
        
        eR_hat = 0.5 * (Re_body @ Kmat - Kmat @ Re_body.T)
        eR = np.array([
            eR_hat[2, 1],
            eR_hat[0, 2],
            eR_hat[1, 0]
        ])
        
        pi_e = - (I @ Omega) # Omega_r is zero for setpoint tracking
        feedforward = np.array([0.0, 0.0, 0.0])
        
        Tu = feedforward + (Kp @ eR) + (Kd @ pi_e)
        
        # Actuator allocation
        u0 = Tu[0]
        u1 = -Tu[2]
        
        # Clip to motor limits (equivalent to 3500 RPM max/min)
        u0 = np.clip(u0, -1.53, 1.53)
        u1 = np.clip(u1, -1.53, 1.53)
        
        target_rpm0 = self.thrust_to_rpm(u0)
        target_rpm1 = self.thrust_to_rpm(u1)
        
        # Motor dynamics (slew rate limit)
        self.motor0_rpm = self.apply_ramp(self.motor0_rpm, target_rpm0, dt, 5000.0)
        self.motor1_rpm = self.apply_ramp(self.motor1_rpm, target_rpm1, dt, 5000.0)
        
        # Update simulated PWMs
        self.sim_pwm1 = int(1500 + (self.motor0_rpm / 3500.0) * 500)
        self.sim_pwm2 = int(1500 + (-self.motor1_rpm / 3500.0) * 500)
        
        # Re-convert actual RPM to aerodynamic thrust/torque
        u_sim_0 = np.sign(self.motor0_rpm) * (self.motor0_rpm / 2828.0) ** 2
        u_sim_1 = np.sign(self.motor1_rpm) * (self.motor1_rpm / 2828.0) ** 2
        
        T1 = u_sim_0
        T3 = -u_sim_1
        
        # 2. Physics Equations
        # Damping terms
        B_p = 0.08
        B_y = 0.12
        
        # Angular accelerations
        term_pitch = (I3 - I2) * (self.yaw_rate ** 2) * np.sin(phi) * np.cos(phi)
        dd_pitch = (T1 - term_pitch - B_p * self.pitch_rate) / I1
        
        term_yaw = (I2 - I1 - I3) * self.pitch_rate * self.yaw_rate * np.sin(phi)
        dd_yaw = (T3 - term_yaw - B_y * self.yaw_rate) / (I3 * np.cos(phi))
        
        # Integrate states using Euler method
        self.pitch_rate += dd_pitch * dt
        self.yaw_rate += dd_yaw * dt
        
        new_phi = phi + self.pitch_rate * dt
        new_theta = theta + self.yaw_rate * dt
        
        # Update angles (converting back to degrees)
        self.current_pitch = float(np.degrees(new_phi))
        self.current_yaw = float(np.degrees(new_theta))

        # Update propeller angles (speed in rad/s is RPM * 2*pi / 60)
        self.left_prop_angle += (self.motor1_rpm * (2.0 * np.pi / 60.0)) * dt
        self.right_prop_angle += (self.motor0_rpm * (2.0 * np.pi / 60.0)) * dt

        # Apply transforms to rotate left propeller (Y-rotation) and right propeller (Z-rotation)
        R_prop_left = tf.rotation_matrix(self.left_prop_angle, [0, 1, 0])
        self.vis["base/beam/left_prop"].set_transform(
            tf.translation_matrix([-0.38, 0, 0]) @ R_prop_left
        )

        R_prop_right = tf.rotation_matrix(self.right_prop_angle, [0, 0, 1])
        self.vis["base/beam/right_prop"].set_transform(
            tf.translation_matrix([0.38, 0, 0]) @ R_prop_right
        )

    def animate_trajectory(self, target_pitch, target_yaw, duration=3.0, start_pitch=None, start_yaw=None):
        """
        Simulates transitioning the Twin Rotor from its deduced initial physical state (or current state) to target angles.
        Uses a realistic 2-DOF MIMO rigid-body dynamical simulation model and closed-loop tracking controller.
        """
        self.is_animating = True
        try:
            if start_pitch is None:
                start_pitch = self.current_pitch
            if start_yaw is None:
                start_yaw = self.current_yaw

            # Initialize states
            self.current_pitch = start_pitch
            self.current_yaw = start_yaw
            self.pitch_rate = 0.0
            self.yaw_rate = 0.0
            self.motor0_rpm = 0.0
            self.motor1_rpm = 0.0
            self.sim_pwm1 = 1500
            self.sim_pwm2 = 1500
            self.sim_psi = 0.0

            total_steps = int(duration * 200) # 200 Hz integration step
            dt_step = 0.005
            
            # Update visualization at ~40 Hz (every 5 steps of 0.005s)
            steps_per_frame = 5
            frame_sleep = dt_step * steps_per_frame
            frames = total_steps // steps_per_frame
            
            print(f"[SIMULATION RUNNING - DYNAMIC MIMO MODEL]: Initial Pos -> Pitch: {start_pitch:.2f}°, Yaw: {start_yaw:.2f}° | Moving to -> Pitch: {target_pitch:.2f}°, Yaw: {target_yaw:.2f}° | Roll: LOCKED (0°)")
            
            for f in range(frames):
                for _ in range(steps_per_frame):
                    self.compute_step(target_pitch, target_yaw, dt_step)
                time.sleep(frame_sleep)
                
            # Remaining steps if any
            remaining_steps = total_steps % steps_per_frame
            for _ in range(remaining_steps):
                self.compute_step(target_pitch, target_yaw, dt_step)

            print("[SIMULATION COMPLETED]: Safety Gate activated. Awaiting operator authorization...")
        finally:
            self.is_animating = False


if __name__ == "__main__":
    # Test simulation locally
    sim = TwinRotorSimulation()
    time.sleep(2) # Give time to open browser
    sim.animate_trajectory(target_pitch=30, target_yaw=-45)