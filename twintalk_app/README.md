# TwinTalk — Flutter Mobile App

> **ME 325 Engineering Design Project 2026**  
> Voice-Actuated Tracking System for Twin Rotor V1.0  
> E/21/338 Riswan · E/21/205 Shathurshiga · E/21/100 Dilshan

---

## Project File Structure

```
twintalk_app/
├── lib/
│   ├── main.dart                          ← App entry point & DI wiring
│   ├── theme/
│   │   └── app_theme.dart                 ← Colours, text styles, ThemeData
│   ├── models/
│   │   └── models.dart                    ← TrajectoryCommand, TelemetryData,
│   │                                          ParsedIntent, ConnectionInfo
│   ├── services/
│   │   ├── rotor_connection_service.dart  ← WebSocket client → Raspberry Pi
│   │   ├── whisper_service.dart           ← OpenAI Whisper ASR
│   │   └── agent_orchestrator.dart        ← LangGraph HTTP client
│   ├── blocs/
│   │   ├── connection_bloc.dart           ← BLoC: Pi connection state
│   │   ├── voice_bloc.dart                ← BLoC: record → transcribe → parse
│   │   └── telemetry_bloc.dart            ← BLoC: live telemetry stream
│   ├── widgets/
│   │   └── tt_widgets.dart                ← Reusable cards, badges, gauges
│   └── screens/
│       ├── home_screen.dart               ← Screen 1: splash + connect form
│       ├── status_screen.dart             ← Screen 2: dashboard + nav shell
│       ├── voice_screen.dart              ← Screen 3: voice command
│       ├── trajectory_approval_screen.dart ← Screen 4: HiL gate
│       └── telemetry_screen.dart          ← Screen 5: live telemetry + chart
├── android/
│   └── AndroidManifest.xml               ← Permissions (mic, network, BT)
├── assets/
│   ├── audio/                             ← (place UI sound files here)
│   └── images/                            ← (place logo/splash images here)
└── pubspec.yaml                           ← Dependencies
```

---

## 1 — Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Flutter SDK | ≥ 3.0.0 | https://flutter.dev/docs/get-started/install |
| Dart SDK | ≥ 3.0.0 | Bundled with Flutter |
| Android Studio | ≥ Giraffe | or VS Code + Flutter extension |
| Android device / emulator | API ≥ 24 | |
| Python 3.11+ (laptop) | — | For the LangGraph backend |

---

## 2 — Step-by-Step Setup

### Step 1 — Clone and navigate

```bash
git clone https://github.com/Dilshan-Prince/ME325-Voice-Command-Twin-rotor
cd ME325-Voice-Command-Twin-rotor/mobile_app
```

If you are starting from the files provided in this handout, place the
`twintalk_app/` folder anywhere on your machine, then:

```bash
cd twintalk_app
```

### Step 2 — Install Flutter dependencies

```bash
flutter pub get
```

### Step 3 — Add your OpenAI API key

Create the file `lib/services/api_keys.dart` (this file is git-ignored):

```dart
// lib/services/api_keys.dart
// NEVER commit this file — add it to .gitignore
const String openAiApiKey = 'sk-YOUR_KEY_HERE';
```

Then in `lib/services/whisper_service.dart`, replace the `_apiKey` constant:

```dart
import 'api_keys.dart';
// Change:
static const String _apiKey = String.fromEnvironment(...);
// To:
static const String _apiKey = openAiApiKey;
```

### Step 4 — Set the Raspberry Pi IP address

Open `lib/services/rotor_connection_service.dart`.  
The default host is `192.168.1.42`. You can also change it at runtime
from the Home screen connection form.

Open `lib/services/agent_orchestrator.dart`.  
Set `_backendHost` to the IP of the laptop running LangGraph:

```dart
static const String _backendHost = '192.168.1.100'; // ← your laptop IP
```

### Step 5 — Connect an Android device

Enable **Developer Options → USB Debugging** on your phone.
Plug it in and verify:

```bash
flutter devices
```

### Step 6 — Run the app

```bash
flutter run
```

To build a release APK:

```bash
flutter build apk --release
# Output: build/app/outputs/flutter-apk/app-release.apk
```

Install on device without USB:

```bash
adb install build/app/outputs/flutter-apk/app-release.apk
```

---

## 3 — Running Without Hardware (Demo Mode)

Tap **"Continue in Demo Mode"** on the Home screen.  
All screens are functional with mock telemetry data.  
The VoiceScreen will call Whisper (needs internet + API key) but the  
AI orchestrator falls back to a simple regex parser if the LangGraph  
backend is not reachable.

---

## 4 — Raspberry Pi WebSocket Server

The Pi must run a Python WebSocket server on port **8765**.  
Minimal example (`pi_server.py`):

```python
import asyncio, json
import websockets

async def handler(ws):
    print(f"Client connected: {ws.remote_address}")
    async for message in ws:
        data = json.loads(message)
        cmd = data.get("cmd", "")

        if cmd == "TRAJECTORY":
            print(f"Executing: pitch={data['pitch']}° yaw={data['yaw']}°")
            # TODO: Call your PID / geometric controller here
            # Send PWM to rotors via RPi.GPIO or pigpio
        elif cmd == "ESTOP":
            print("EMERGENCY STOP")
            # TODO: Zero all PWM signals immediately

        # Stream mock telemetry back at 20 Hz
        for _ in range(100):
            await ws.send(json.dumps({
                "type": "telemetry",
                "pitch": 12.4,
                "yaw": -5.1,
                "pwm1": 1480,
                "pwm2": 1520,
                "psi": 0.23
            }))
            await asyncio.sleep(0.05)

async def main():
    async with websockets.serve(handler, "0.0.0.0", 8765):
        print("TwinTalk Pi server running on ws://0.0.0.0:8765")
        await asyncio.Future()

asyncio.run(main())
```

Run on the Pi:

```bash
pip install websockets
python pi_server.py
```

---

## 5 — LangGraph Backend (Laptop)

The AI orchestrator expects two REST endpoints on `http://<laptop>:8000`:

| Endpoint | Method | Body | Response |
|----------|--------|------|----------|
| `/parse_intent` | POST | `{"text": "..."}` | `ParsedIntent` JSON |
| `/gen_trajectory` | POST | `ParsedIntent` fields | `TrajectoryCommand` JSON |

Minimal FastAPI wrapper (`backend/main.py`):

```python
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

app = FastAPI()

class IntentRequest(BaseModel):
    text: str

@app.post("/parse_intent")
async def parse_intent(req: IntentRequest):
    # TODO: Route to your LangGraph supervisor agent
    return {
        "raw": req.text,
        "pitch": 30.0,
        "yaw": 45.0,
        "duration": 4.0,
        "mode": "sweep",
        "sim": True,
        "chips": ["pitch → 30°", "yaw → 45°", "mode: sweep"]
    }

@app.post("/gen_trajectory")
async def gen_trajectory(body: dict):
    # TODO: Run trajectory generation agent
    return {
        "cmd": "TRAJECTORY",
        "pitch": body.get("pitch", 0),
        "yaw": body.get("yaw", 0),
        "duration": body.get("duration", 3.0),
        "mode": body.get("mode", "geometric"),
        "waypoints": [],
        "ts": 0
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

```bash
pip install fastapi uvicorn langgraph langchain-openai
python backend/main.py
```

---

## 6 — Screen Navigation Flow

```
HomeScreen
    │  (on connect / demo mode)
    ▼
StatusScreen  ◄──────────────────────┐
    │                                │
    │  (bottom nav: Voice tab)       │
    ▼                                │
VoiceScreen                          │
    │  (after parse + send to agent) │
    ▼                                │
TrajectoryApprovalScreen (HiL Gate)  │
    │  (on Approve)                  │
    ▼                                │
TelemetryScreen ─────────────────────┘
    (bottom nav: Home tab returns to StatusScreen)
```

---

## 7 — Key Dependencies

| Package | Purpose |
|---------|---------|
| `flutter_bloc` | State management (BLoC pattern) |
| `web_socket_channel` | WebSocket to Raspberry Pi |
| `http` | REST calls to Whisper API + LangGraph backend |
| `record` | Microphone capture for Whisper |
| `fl_chart` | Live pitch/yaw telemetry chart |
| `google_fonts` | Inter font family |
| `permission_handler` | Runtime mic permission request |
| `path_provider` | Temp directory for audio files |
| `logger` | Structured logging |

---

## 8 — Troubleshooting

| Problem | Fix |
|---------|-----|
| `MicrophonePermissionDenied` | Go to Android Settings → Apps → TwinTalk → Permissions → Microphone → Allow |
| `WebSocket connection refused` | Check Pi IP address, ensure `pi_server.py` is running, both devices on same Wi-Fi |
| `Whisper 401 Unauthorized` | Check your OpenAI API key in `api_keys.dart` |
| `Whisper 429 Rate Limited` | Your OpenAI account is rate-limited; wait or upgrade plan |
| `LangGraph backend not reachable` | App falls back to regex parser — check laptop IP and that `backend/main.py` is running |
| `fl_chart render error` | Ensure telemetry history has ≥ 2 points before chart renders (guarded in code) |
| `usesCleartextTraffic` error on Android 9+ | Already set in `AndroidManifest.xml` — ensure you're using the file provided |

---

*ME 325 · University of Peradeniya · Engineering Design Project 2026*
