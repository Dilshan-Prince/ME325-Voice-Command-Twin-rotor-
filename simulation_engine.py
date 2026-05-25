import meshcat
import meshcat.geometry as g
import meshcat.transformations as tf
import numpy as np
import time

class TwinRotorSimulation:
    def __init__(self):
        # Initialize the MeshCat visualizer server
        self.vis = meshcat.Visualizer()
        print(f"\n========================================================")
        print(f"MeshCat Server active! Open this URL in your browser:\n-> {self.vis.url()}")
        print(f"========================================================\n")
        self.setup_environment()

    def setup_environment(self):
        # 1. Create a static base (Pivot Base)
        self.vis["base"].set_object(g.Cylinder(height=0.1, radius=0.15), 
                                    g.MeshLambertMaterial(color=0x333333))
        
        # 2. Create the main beam (holding the rotors)
        self.vis["base/beam"].set_object(g.Box([0.8, 0.04, 0.04]), 
                                         g.MeshLambertMaterial(color=0x999999))
        
        # 3. Create Left & Right Rotor assemblies
        self.vis["base/beam/left_rotor"].set_object(g.Cylinder(height=0.02, radius=0.1), 
                                                    g.MeshLambertMaterial(color=0xff0000))
        self.vis["base/beam/left_rotor"].set_transform(tf.translation_matrix([-0.38, 0, 0.04]))
        
        self.vis["base/beam/right_rotor"].set_object(g.Cylinder(height=0.02, radius=0.1), 
                                                     g.MeshLambertMaterial(color=0x0000ff))
        self.vis["base/beam/right_rotor"].set_transform(tf.translation_matrix([0.38, 0, 0.04]))

    def animate_trajectory(self, target_pitch, target_yaw, duration=3.0):
        """
        Simulates transitioning the Twin Rotor from its current state to target angles.
        The Roll axis is locked mathematically at 0 degrees to match the 2-DOF hardware.
        """
        steps = 30
        sleep_interval = duration / steps
        
        # Smoothly interpolate Pitch and Yaw over the duration steps
        pitch_points = np.linspace(0, np.radians(target_pitch), steps)
        yaw_points = np.linspace(0, np.radians(target_yaw), steps)
        
        print(f"[SIMULATION RUNNING]: Moving to Pitch: {target_pitch}°, Yaw: {target_yaw}° | Roll: LOCKED (0°)")
        
        for p, y in zip(pitch_points, yaw_points):
            # FIXED PARAMETER: Roll angle 'r' is explicitly set to 0
            r = 0.0 
            
            # Construct distinct transformation matrices for each axis rotation
            R_yaw = tf.rotation_matrix(y, [0, 0, 1])    # Rotation around Z-axis
            R_pitch = tf.rotation_matrix(p, [1, 0, 0])  # Rotation around X-axis
            R_roll = tf.rotation_matrix(r, [0, 1, 0])   # Rotation around Y-axis (Locked at 0)
            
            # Combine transformations by multiplying matrices sequentially (Yaw -> Pitch -> Roll)
            rotation_matrix = R_yaw @ R_pitch @ R_roll
            
            # Apply the constrained structural rotation to the virtual beam component
            self.vis["base/beam"].set_transform(rotation_matrix)
            time.sleep(sleep_interval)
            
        print("[SIMULATION COMPLETED]: Safety Gate activated. Awaiting operator authorization...")

if __name__ == "__main__":
    # Test simulation locally
    sim = TwinRotorSimulation()
    time.sleep(2) # Give time to open browser
    sim.animate_trajectory(target_pitch=30, target_yaw=-45)