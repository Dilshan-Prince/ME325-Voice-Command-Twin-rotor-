# TwinTalk — Voice-Actuated Twin Rotor Control System

> **ME 325 Engineering Design Project · University of Peradeniya**
> E/21/100 Dilshan · E/21/338 Riswan · E/21/205 Shathurshiga
> Supervised by Dr. Maithiripala

TwinTalk lets an operator control a twin-rotor testbed with natural-language
voice commands. Speech is transcribed and parsed into an intent, an AI agent
turns that intent into a trajectory, a human approves it in the loop, and the
trajectory is executed on the physical rig via a geometric (SO(3)) PID
controller running on a Raspberry Pi — with live telemetry streamed back to
the operator's phone.

```
 Voice ──▶ Whisper ASR ──▶ LangGraph Agent ──▶ Trajectory ──▶ HiL Approval ──▶ Raspberry Pi
(Flutter)                  (Laptop, FastAPI)   Command        (Flutter)        (SO(3) PID + PWM)
                                                                                      │
                                                                                      ▼
                                                                     Live telemetry (WebSocket, 20 Hz)
                                                                                      │
                                                                                      ▼
                                                                              Flutter dashboard
```

## Repository Structure

| Folder | What it is |
|---|---|
| [`twintalk_app/`](twintalk_app) | Flutter mobile app — the operator's interface. Handles voice capture, Whisper transcription, agent orchestration, human-in-the-loop trajectory approval, and live telemetry display. |
| [`Twinrotor Simulation/`](Twinrotor%20Simulation) | 3D kinematic simulation and safety-gate orchestration layer. Runs the LangGraph intent-parsing/trajectory-generation backend and a MeshCat 3D visualizer for testing without hardware. |
| [`Twin_Rotor_Research_Platform/`](Twin_Rotor_Research_Platform) | Python library and example scripts that run **on the Raspberry Pi**: motor driving (CAN bus), encoder/IMU sensor fusion, PID/geometric controllers, data logging, and live plotting. |
| [`TwinTalk_Proposal_Report.pdf`](TwinTalk_Proposal_Report.pdf) | Project proposal report. |
| [`TwinTalk_MidTerm_Presentation .pdf`](TwinTalk_MidTerm_Presentation%20.pdf) | Mid-term presentation slides. |
| [`END TERM EVALUATION A3 SIZE POSTER.pdf`](END%20TERM%20EVALUATION%20A3%20SIZE%20POSTER.pdf) | Final evaluation poster. |

## System Overview

1. **Voice input (`twintalk_app`)** — The user records a command in the app. Audio is sent to OpenAI Whisper for transcription.
2. **Intent parsing & trajectory generation (`Twinrotor Simulation/backend`)** — A FastAPI service backed by LangGraph exposes `/parse_intent` and `/gen_trajectory`, turning the transcript into a structured trajectory (pitch, yaw, duration, mode, waypoints).
3. **Human-in-the-loop approval (`twintalk_app`)** — The generated trajectory is shown to the operator before it is sent to hardware, as a safety gate.
4. **Execution (`Twin_Rotor_Research_Platform`)** — The Raspberry Pi runs a WebSocket server that receives the trajectory command and drives the twin-rotor motors using a geometric SO(3) PID controller, with an emergency-stop (`ESTOP`) command always available.
5. **Telemetry** — The Pi streams live pitch/yaw/PWM telemetry back over the same WebSocket connection at ~20 Hz, rendered as a live chart in the app.
6. **Offline testing (`Twinrotor Simulation`)** — The same intent → trajectory pipeline can be exercised against a 3D kinematic simulation (MeshCat) instead of the physical rig, so the app and agent logic can be developed without hardware.

## Getting Started

Each component is set up independently — see the linked README for full instructions.

### 1. Raspberry Pi (hardware side)
```bash
cd Twin_Rotor_Research_Platform
pip install -r requirements.txt   # numpy, pyqtgraph, scipy, etc. — see Readme.md
python3 pid_fixed_set_point_example.py   # sanity-check the rig
```
Full setup (SSH access, credentials, wiring notes): [`Twin_Rotor_Research_Platform/Readme.md`](Twin_Rotor_Research_Platform/Readme.md) and [`docs/User_Guide.md`](Twin_Rotor_Research_Platform/docs/User_Guide.md).

### 2. Simulation & AI backend (laptop side)
```bash
cd "Twinrotor Simulation"
pip install -r requirement.txt    # flask, langgraph, langchain-openai, meshcat, fastapi, uvicorn...
python app.py                     # simulation + MeshCat visualizer
python backend/main.py            # FastAPI /parse_intent + /gen_trajectory endpoints
```
Open the MeshCat link printed in the terminal (`http://127.0.0.1:7000/static/`) to view the 3D simulation.

### 3. Mobile app (operator side)
```bash
cd twintalk_app
flutter pub get
flutter run
```
Requires an OpenAI API key (for Whisper) in `lib/services/api_keys.dart`, and the Raspberry Pi / laptop IP addresses set in `lib/services/rotor_connection_service.dart` and `lib/services/agent_orchestrator.dart`. A **Demo Mode** is available that runs entirely on mock telemetry, no hardware required. Full setup: [`twintalk_app/README.md`](twintalk_app/README.md).

## Hardware Requirements

- Raspberry Pi (running the twin-rotor control library, hostname `OriseTRS`)
- Twin-rotor testbed with CAN-bus motor drivers, rotary encoders, and IMU
- Android device (API ≥ 24) or emulator for the Flutter app
- Laptop for the LangGraph/FastAPI backend and simulation

## Key Technologies

`Flutter` · `Dart` (BLoC pattern) · `Python` · `FastAPI` · `LangGraph` / `LangChain` · `OpenAI Whisper` · `WebSockets` · `MeshCat` · `NumPy` / `SciPy` · `PyQtGraph` · `CAN bus`

## Project Docs

- [Proposal Report](TwinTalk_Proposal_Report.pdf)
- [Mid-Term Presentation](TwinTalk_MidTerm_Presentation%20.pdf)
- [Final Evaluation Poster](END%20TERM%20EVALUATION%20A3%20SIZE%20POSTER.pdf)

---
*ME 325 · University of Peradeniya · Engineering Design Project 2026*
