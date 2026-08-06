from fastapi import FastAPI, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from simulation_engine import TwinRotorSimulation
import asyncio
import json
import re
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the MeshCat simulation model globally
sim_platform = TwinRotorSimulation()

class IntentRequest(BaseModel):
    text: str

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

    # Clamp pitch to the rig's physical limits of [-80.0, 80.0] degrees
    pitch = max(-80.0, min(80.0, pitch))

    return {"pitch": pitch, "yaw": yaw}

@app.post("/parse_intent")
async def parse_intent(req: IntentRequest):
    parsed = parse_intent_via_agent(
        req.text,
        current_pitch=pi_telemetry_state.get("pitch", 0.0),
        current_yaw=pi_telemetry_state.get("yaw", 0.0)
    )
    p = parsed["pitch"]
    y = parsed["yaw"]
    return {
        "raw": req.text,
        "pitch": float(p),
        "yaw": float(y),
        "duration": 3.0,
        "mode": "step",
        "sim": True,
        "chips": [f"pitch → {p}°", f"yaw → {y}°", "mode: step"]
    }

@app.post("/gen_trajectory")
async def gen_trajectory(body: dict):
    return {
        "cmd": "TRAJECTORY",
        "pitch": body.get("pitch", 0.0),
        "yaw": body.get("yaw", 0.0),
        "duration": body.get("duration", 3.0),
        "mode": body.get("mode", "geometric"),
        "waypoints": [],
        "ts": int(time.time() * 1000)
    }

# Active WebSocket connections, command cache & Pi feedback telemetry state
active_connections: set = set()
latest_hardware_command = {"pitch": 0.0, "yaw": 0.0, "timestamp": 0.0, "cmd": "IDLE"}
latest_target_command = {"pitch": 0.0, "yaw": 0.0}
pi_telemetry_state = {"pitch": 0.0, "yaw": 0.0, "encoder1": 0, "pwm1": 1500, "pwm2": 1500, "timestamp": 0.0, "received": False}

async def broadcast_hardware_dispatch(pitch: float, yaw: float):
    global latest_hardware_command
    latest_hardware_command = {
        "type": "hardware_command",
        "cmd": "EXECUTE",
        "pitch": float(pitch),
        "yaw": float(yaw),
        "timestamp": time.time()
    }
    msg = json.dumps(latest_hardware_command)
    print(f"\n[PIPELINE 2 DISPATCH]: Transmitting hardware command -> Pitch: {pitch}°, Yaw: {yaw}° to {len(active_connections)} connection(s)")
    disconnected = set()
    for ws in list(active_connections):
        try:
            await ws.send_text(msg)
        except Exception as e:
            print(f"[WebSocket Dispatch Error]: {e}")
            disconnected.add(ws)
    active_connections.difference_update(disconnected)

def update_pi_telemetry_data(data: dict):
    global pi_telemetry_state
    pitch = float(data.get("pitch", data.get("pitch_deg", 0.0)))
    yaw = float(data.get("yaw", data.get("yaw_deg", 0.0)))
    encoder1 = int(data.get("encoder1", 0))
    pwm1 = int(data.get("pwm1", 1500))
    pwm2 = int(data.get("pwm2", 1500))
    ts = float(data.get("timestamp", time.time()))
    
    pi_telemetry_state = {
        "pitch": pitch,
        "yaw": yaw,
        "encoder1": encoder1,
        "pwm1": pwm1,
        "pwm2": pwm2,
        "timestamp": ts,
        "received": True
    }
    # Live telemetry visualizer sync disabled to keep the angle as the commanded input data
    # if (hasattr(sim_platform, "current_pitch") 
    #         and not getattr(sim_platform, "is_animating", False) 
    #         and not getattr(sim_platform, "awaiting_authorization", False)):
    #     sim_platform.current_pitch = pitch
    #     sim_platform.current_yaw = yaw

@app.post("/api/pi_telemetry")
async def receive_pi_telemetry(body: dict):
    update_pi_telemetry_data(body)
    return {"status": "success", "deduced_initial_pitch": pi_telemetry_state["pitch"]}

@app.get("/api/pi_telemetry")
async def get_pi_telemetry():
    return pi_telemetry_state

@app.get("/api/hardware_command")
async def get_hardware_command():
    return latest_hardware_command

@app.post("/api/command")
async def handle_voice_command(body: dict):
    voice_text = body.get("command", "")
    print(f"\n[Received Mobile Command]: '{voice_text}'")
    parsed = parse_intent_via_agent(
        voice_text,
        current_pitch=pi_telemetry_state.get("pitch", 0.0),
        current_yaw=pi_telemetry_state.get("yaw", 0.0)
    )
    
    global latest_target_command
    latest_target_command = {"pitch": float(parsed["pitch"]), "yaw": float(parsed["yaw"])}
    
    # Hold simulation position at target during authorization phase
    sim_platform.awaiting_authorization = True
    
    # Wait for the simulation animation to complete (starting from deduced Pi initial position)
    await run_simulation_async(parsed["pitch"], parsed["yaw"], 3.0)
    
    return {
        "status": "completed",
        "message": "Simulation completed. Awaiting operator authorization.",
        "parsed_data": {
            "pitch": float(parsed["pitch"]),
            "yaw": float(parsed["yaw"]),
            "initial_pitch": pi_telemetry_state["pitch"],
            "final_pitch": sim_platform.current_pitch,
            "final_yaw": sim_platform.current_yaw
        }
    }
 
@app.post("/api/authorize")
async def authorize_movement(body: dict):
    user_approval = body.get("approved", False)
    # Release simulation target position hold
    sim_platform.awaiting_authorization = False
    if user_approval:
        print("\n[SAFETY GATE RELEASED]: Deploying to hardware controllers.")
        await broadcast_hardware_dispatch(latest_target_command["pitch"], latest_target_command["yaw"])
        return {"status": "executed", "message": "Dispatched to hardware controllers."}
    else:
        print("\n[SAFETY GATE REJECTED]: Trajectory dumped safely.")
        return {"status": "cancelled", "message": "Movement rejected by operator."}

async def telemetry_sender(websocket: WebSocket):
    try:
        while True:
            if pi_telemetry_state["received"]:
                await websocket.send_text(json.dumps({
                    "type": "telemetry",
                    "pitch": pi_telemetry_state["pitch"],
                    "yaw": pi_telemetry_state["yaw"],
                    "pwm1": pi_telemetry_state["pwm1"],
                    "pwm2": pi_telemetry_state["pwm2"],
                    "psi": 0.0
                }))
            else:
                await websocket.send_text(json.dumps({
                    "type": "telemetry",
                    "pitch": sim_platform.current_pitch,
                    "yaw": sim_platform.current_yaw,
                    "pwm1": sim_platform.sim_pwm1,
                    "pwm2": sim_platform.sim_pwm2,
                    "psi": sim_platform.sim_psi
                }))
            await asyncio.sleep(0.05)
    except asyncio.CancelledError:
        pass

async def run_simulation_async(pitch, yaw, duration):
    start_p = pi_telemetry_state["pitch"] if pi_telemetry_state["received"] else sim_platform.current_pitch
    start_y = pi_telemetry_state["yaw"] if pi_telemetry_state["received"] else sim_platform.current_yaw
    
    # Normalize starting angles to [-180, 180] degrees to avoid crazy spinning in MeshCat
    start_p = (start_p + 180) % 360 - 180
    start_y = (start_y + 180) % 360 - 180
    
    print(f"\n[DEDUCED INITIAL ROTOR POSITION]: Start Pitch={start_p:.2f}°, Start Yaw={start_y:.2f}° (from Pi feedback)")
    print(f"[Simulation Background]: Actuating model from ({start_p:.2f}°, {start_y:.2f}°) to pitch={pitch:.2f}°, yaw={yaw:.2f}°")
    await asyncio.to_thread(sim_platform.animate_trajectory, pitch, yaw, duration, start_pitch=start_p, start_yaw=start_y)

async def message_receiver(websocket: WebSocket):
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")
            
            if msg_type == "pi_telemetry":
                update_pi_telemetry_data(message)
                continue

            cmd = message.get("cmd")
            if cmd == "TRAJECTORY":
                p = message.get("pitch", 0.0)
                y = message.get("yaw", 0.0)
                d = message.get("duration", 3.0)
                # Clamp target pitch to physical limits of [-80.0, 80.0] degrees
                p = max(-80.0, min(80.0, float(p)))
                
                global latest_target_command
                latest_target_command = {"pitch": float(p), "yaw": float(y)}
                
                sim_platform.awaiting_authorization = False
                # Also schedule dispatch after simulation completes
                async def run_and_dispatch():
                    await run_simulation_async(p, y, d)
                asyncio.create_task(run_and_dispatch())
            elif cmd == "ESTOP":
                # Emergency Stop
                sim_platform.awaiting_authorization = False
                asyncio.create_task(run_simulation_async(0.0, 0.0, 1.0))
                await broadcast_hardware_dispatch(0.0, 0.0)
    except Exception as e:
        print(f"Message receiver exception: {e}")


@app.websocket("/ws")
@app.websocket("/")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.add(websocket)
    print("Client connected via WebSocket (Added to Pipeline 2 subscribers)!")
    sender_task = asyncio.create_task(telemetry_sender(websocket))
    receiver_task = asyncio.create_task(message_receiver(websocket))
    try:
        await asyncio.gather(sender_task, receiver_task)
    except Exception as e:
        print(f"WebSocket session closed/error: {e}")
    finally:
        active_connections.discard(websocket)
        sender_task.cancel()
        receiver_task.cancel()
        print("WebSocket session cleaned up.")

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)