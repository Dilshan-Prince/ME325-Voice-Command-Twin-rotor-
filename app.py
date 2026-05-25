from flask import Flask, request, jsonify
from simulation_engine import TwinRotorSimulation
import re

app = Flask(__name__)

# Initialize the MeshCat simulation model globally
sim_platform = TwinRotorSimulation()

# In-memory variable simulating the holding gate state
pending_trajectory = None

def parse_intent_via_agent(command_text):
    """
    Simulates the LangGraph routing agent processing natural language.
    Looks for pitch and yaw numbers inside your spoken command.
    """
    pitch_match = re.search(r"pitch\s*(-?\d+)", command_text, re.IGNORECASE)
    yaw_match = re.search(r"yaw\s*(-?\d+)", command_text, re.IGNORECASE)
    
    pitch = int(pitch_match.group(1)) if pitch_match else 0
    yaw = int(yaw_match.group(1)) if yaw_match else 0
    return {"pitch": pitch, "yaw": yaw}

@app.route('/api/command', methods=['POST'])
def handle_voice_command():
    global pending_trajectory
    data = request.get_json()
    voice_text = data.get("command", "")
    
    print(f"\n[Received Mobile Command]: '{voice_text}'")
    
    # 1. Parsing step
    target_angles = parse_intent_via_agent(voice_text)
    pending_trajectory = target_angles
    
    # 2. Trigger Simulation Step (Safety Preview)
    sim_platform.animate_trajectory(target_angles["pitch"], target_angles["yaw"])
    
    return jsonify({
        "status": "simulating",
        "message": "Trajectory generated in MeshCat. Human-in-the-Loop verification required.",
        "parsed_data": target_angles
    }), 200

@app.route('/api/authorize', methods=['POST'])
def authorize_movement():
    global pending_trajectory
    data = request.get_json()
    user_approval = data.get("approved", False)
    
    if user_approval and pending_trajectory:
        print(f"\n[SAFETY GATE RELEASED]: Deploying Pitch: {pending_trajectory['pitch']}, Yaw: {pending_trajectory['yaw']} to Raspberry Pi!")
        pending_trajectory = None
        return jsonify({"status": "executed", "message": "Dispatched to hardware controllers."}), 200
    else:
        print("\n[SAFETY GATE REJECTED]: Trajectory dumped safely.")
        pending_trajectory = None
        return jsonify({"status": "cancelled", "message": "Movement rejected by operator."}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)