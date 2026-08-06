import sys
import os
import asyncio
import json
import numpy as np

# Add the parent directory to Python path to import simulation_engine
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from simulation_engine import TwinRotorSimulation

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the MeshCat simulation model globally
try:
    sim_platform = TwinRotorSimulation()
except Exception as e:
    print(f"Failed to initialize MeshCat simulation: {e}")
    sim_platform = None

# Global state for simulation telemetry
current_state = {
    "pitch": 0.0,
    "yaw": 0.0,
    "pwm1": 1500,
    "pwm2": 1500,
    "psi": 0.0,
    "pi_telemetry_received": False
}

def update_pi_telemetry_feedback(data: dict):
    global current_state
    pitch = float(data.get("pitch", data.get("pitch_deg", 0.0)))
    yaw = float(data.get("yaw", data.get("yaw_deg", 0.0)))
    current_state["pitch"] = pitch
    current_state["yaw"] = yaw
    current_state["pi_telemetry_received"] = True

@app.post("/api/pi_telemetry")
async def receive_pi_telemetry(body: dict):
    update_pi_telemetry_feedback(body)
    return {"status": "success", "deduced_initial_pitch": current_state["pitch"]}

async def animate_to(target_pitch: float, target_yaw: float, duration: float):
    global current_state
    steps = int(duration * 200)  # 200 Hz integration step
    dt_step = 0.005
    
    if steps <= 0:
        steps = 1
    
    start_pitch = current_state["pitch"]
    start_yaw = current_state["yaw"]
    
    print(f"\n[DEDUCED INITIAL POSITION]: Simulation starting from Pi Feedback Pos -> Pitch: {start_pitch:.2f}°, Yaw: {start_yaw:.2f}°")
    print(f"[SIMULATION RUNNING - DYNAMIC MIMO MODEL]: Moving from ({start_pitch:.2f}°, {start_yaw:.2f}°) to Pitch: {target_pitch:.2f}°, Yaw: {target_yaw:.2f}°")
    
    # Initialize simulation platform states if available
    if sim_platform:
        sim_platform.current_pitch = start_pitch
        sim_platform.current_yaw = start_yaw
        sim_platform.pitch_rate = 0.0
        sim_platform.yaw_rate = 0.0
        sim_platform.motor0_rpm = 0.0
        sim_platform.motor1_rpm = 0.0
        sim_platform.sim_pwm1 = 1500
        sim_platform.sim_pwm2 = 1500
        sim_platform.sim_psi = 0.0

    steps_per_frame = 10  # update state and sleep every 0.05 seconds (20 Hz visual frame rate)
    frame_sleep = dt_step * steps_per_frame
    frames = steps // steps_per_frame
    
    for f in range(frames):
        if sim_platform:
            for _ in range(steps_per_frame):
                sim_platform.compute_step(target_pitch, target_yaw, dt_step)
            current_state["pitch"] = sim_platform.current_pitch
            current_state["yaw"] = sim_platform.current_yaw
            current_state["pwm1"] = sim_platform.sim_pwm1
            current_state["pwm2"] = sim_platform.sim_pwm2
            current_state["psi"] = sim_platform.sim_psi
        else:
            t = (f * steps_per_frame) / steps
            current_state["pitch"] = start_pitch + (target_pitch - start_pitch) * t
            current_state["yaw"] = start_yaw + (target_yaw - start_yaw) * t
            current_state["pwm1"] = 1500 + int((target_pitch - current_state["pitch"]) * 10)
            current_state["pwm2"] = 1500 + int((target_yaw - current_state["yaw"]) * 10)
            current_state["psi"] = abs(target_pitch - current_state["pitch"]) * 0.01
            
        await asyncio.sleep(frame_sleep)
        
    # Run any remaining steps
    remaining_steps = steps % steps_per_frame
    if remaining_steps > 0 and sim_platform:
        for _ in range(remaining_steps):
            sim_platform.compute_step(target_pitch, target_yaw, dt_step)
        current_state["pitch"] = sim_platform.current_pitch
        current_state["yaw"] = sim_platform.current_yaw
        current_state["pwm1"] = sim_platform.sim_pwm1
        current_state["pwm2"] = sim_platform.sim_pwm2
        current_state["psi"] = sim_platform.sim_psi
        
    print("[SIMULATION COMPLETED]")

def parse_intent_via_agent(command_text: str, current_pitch: float = 0.0, current_yaw: float = 0.0):
    """
    Parses natural language commands from voice input.
    Robust against common voice-recognition typos, word-based numbers, and negative signs.
    """
    import re

    # Lowercase and replace slashes with spaces for clean tokenization
    text = command_text.lower().replace("/", " ")
    
    # Replace hyphens with spaces only when they are between letters (e.g. "forty-five")
    # to preserve negative signs (e.g. "-45")
    text = re.sub(r'(?<=[a-z])-(?=[a-z])', ' ', text)

    # Normalize "minus"/"negative" to "-"
    text = re.sub(r"\b(minus|negative)\s*", "-", text)

    # Dictionary mapping word numbers to digits
    units = {
        "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
        "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
        "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19
    }
    tens = {
        "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
        "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90
    }
    scales = {
        "hundred": 100
    }

    # Helper function to convert text number words to numeric digits
    words = text.split()
    new_words = []
    i = 0
    while i < len(words):
        word = words[i].strip(",.-")
        has_number_word = False
        current_val = 0
        temp_i = i
        
        while temp_i < len(words):
            w = words[temp_i].strip(",.-")
            if w in units:
                current_val += units[w]
                temp_i += 1
                has_number_word = True
            elif w in tens:
                current_val += tens[w]
                temp_i += 1
                has_number_word = True
            elif w in scales:
                if current_val == 0:
                    current_val = 1
                current_val *= scales[w]
                temp_i += 1
                has_number_word = True
            elif w == "and" and temp_i > i and temp_i + 1 < len(words) and (words[temp_i+1].strip(",.-") in units or words[temp_i+1].strip(",.-") in tens):
                temp_i += 1
            else:
                break
                
        if has_number_word:
            new_words.append(str(current_val))
            i = temp_i
        else:
            new_words.append(words[i])
            i += 1

    text = " ".join(new_words)

    # Normalize pitch typos
    text = re.sub(r"\b(pitch|pitvh|pich|picth|ptch|pitching|peach|bitch|patch|pinch|picture|pot|put)\b", "pitch", text)

    # Normalize yaw typos
    text = re.sub(r"\b(yaw|yo|yow|ya|yew|yuw|yawing|yawn|young|yacht|yeah|you|your|yellow|all|y'all|here)\b", "yaw", text)

    # Extract numbers following pitch/yaw
    pitch_match = re.search(r"pitch\b.*?(-?\d+(?:\.\d+)?)", text)
    yaw_match = re.search(r"yaw\b.*?(-?\d+(?:\.\d+)?)", text)

    pitch = float(pitch_match.group(1)) if pitch_match else current_pitch
    yaw = float(yaw_match.group(1)) if yaw_match else current_yaw

    return {"pitch": pitch, "yaw": yaw}


class IntentRequest(BaseModel):
    text: str

@app.post("/parse_intent")
async def parse_intent(req: IntentRequest):
    # Route to simulated parser
    print(f"Parsing intent: '{req.text}'")
    parsed = parse_intent_via_agent(
        req.text,
        current_pitch=current_state.get("pitch", 0.0),
        current_yaw=current_state.get("yaw", 0.0)
    )
    pitch = parsed["pitch"]
    yaw = parsed["yaw"]
    
    return {
        "raw": req.text,
        "pitch": pitch,
        "yaw": yaw,
        "initial_pitch": current_state["pitch"],
        "duration": 4.0,
        "mode": "sweep" if "sweep" in req.text.lower() else "step",
        "sim": True,
        "chips": [f"pitch → {pitch}°", f"yaw → {yaw}°", f"mode: {'sweep' if 'sweep' in req.text.lower() else 'step'}"]
    }

@app.post("/gen_trajectory")
async def gen_trajectory(body: dict):
    pitch = body.get("pitch", 0.0)
    yaw = body.get("yaw", 0.0)
    duration = body.get("duration", 3.0)
    mode = body.get("mode", "geometric")
    print(f"Generating trajectory to Pitch: {pitch}°, Yaw: {yaw}° ({mode})")
    return {
        "cmd": "TRAJECTORY",
        "pitch": pitch,
        "yaw": yaw,
        "initial_pitch": current_state["pitch"],
        "duration": duration,
        "mode": mode,
        "waypoints": [],
        "ts": int(asyncio.get_event_loop().time() * 1000)
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Flutter app / Hardware Pi connected via WebSocket!")
    
    async def send_telemetry():
        try:
            while True:
                await websocket.send_text(json.dumps({
                    "type": "telemetry",
                    "pitch": current_state["pitch"],
                    "yaw": current_state["yaw"],
                    "pwm1": current_state["pwm1"],
                    "pwm2": current_state["pwm2"],
                    "psi": current_state["psi"]
                }))
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Telemetry sending error: {e}")

    telemetry_task = asyncio.create_task(send_telemetry())
    active_animation_task = None

    try:
        while True:
            data_str = await websocket.receive_text()
            try:
                data = json.loads(data_str)
                msg_type = data.get("type")
                if msg_type == "pi_telemetry":
                    update_pi_telemetry_feedback(data)
                    continue

                cmd = data.get("cmd")
                print(f"Received WS command: {data}")
                
                if cmd == "TRAJECTORY":
                    pitch = float(data.get("pitch", 0.0))
                    yaw = float(data.get("yaw", 0.0))
                    duration = float(data.get("duration", 3.0))
                    
                    if active_animation_task and not active_animation_task.done():
                        active_animation_task.cancel()
                    
                    active_animation_task = asyncio.create_task(
                        animate_to(pitch, yaw, duration)
                    )

                elif cmd == "ESTOP":
                    if active_animation_task and not active_animation_task.done():
                        active_animation_task.cancel()
                    current_state["pwm1"] = 0
                    current_state["pwm2"] = 0
                    print("EMERGENCY STOP executed!")
                elif cmd == "PAUSE":
                    if active_animation_task and not active_animation_task.done():
                        active_animation_task.cancel()
                    print("Animation paused.")
                elif cmd == "RESUME":
                    # Resume last animation (placeholder logic)
                    pass
            except Exception as json_err:
                print(f"Error parsing incoming WS message: {json_err}")
                
    except Exception as e:
        print(f"WebSocket client disconnected: {e}")
    finally:
        telemetry_task.cancel()
        if active_animation_task and not active_animation_task.done():
            active_animation_task.cancel()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
