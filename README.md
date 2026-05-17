# TwinTalk: Voice-Actuated Tracking System for Twin Rotor

TwinTalk is a modular, voice-actuated control system designed for the **Twin Rotor V1.0** platform that enables hands-free trajectory tracking. By integrating Natural Language Processing (NLP) with traditional PID and Advanced Geometric Control algorithms, the system establishes a professional bridge between human interaction and complex aerospace hardware. 

The core feature of TwinTalk is its **Human-in-the-Loop (HiL) Safety Gate**, which mandates a real-time 3D kinematic simulation and explicit operator voice approval before transmitting any physical movement commands to the hardware.

---

## 🚀 Core Architecture & Workflow

The system follows a strict stateful pipeline to ensure absolute hardware safety:

1. **Voice Input:** The operator issues a natural language trajectory command through a custom mobile application.
2. **Intent Parsing:** The mobile app streams the audio to a central laptop, where **OpenAI Whisper** translates the speech, and a multi-agent **LangGraph** system parses the operator's intent.
3. **Safety Evaluation:** The AI Orchestrator evaluates the command. If the trajectory is complex or high-risk, it routes the command to an offline **MeshCat** 3D simulation environment.
4. **Human Verification:** The 3D simulation results are mirrored back to the mobile interface. The physical hardware remains locked.
5. **Execution:** Only when the user provides explicit voice verification ("Authorize" / "Execute") does the laptop command the **Raspberry Pi 4 Model B** to output precise hardware PWM signals to the rotors.

---

## 🛠️ Tech Stack

### Software
- **Mobile Interface:** Android Native (Kotlin) / React Native
- **Speech Processing:** OpenAI Whisper (Offline/API integration)
- **AI Orchestration:** Python, LangGraph (Multi-agent routing)
- **Simulation & Math:** MeshCat (3D Kinematic Preview), NumPy, SciPy, PyTorch
- **Control & Validation:** MATLAB / Simulink, Raspberry Pi OS (Python-driven)

### Hardware Components
- **Twin Rotor MIMO System (TRMS):** Dual-rotor body (R1 / R2) on a pivot base.
- **Compute Unit:** Raspberry Pi 4 Model B (handling real-time hardware PWM generation).
- **Communication Module:** High-speed local Bluetooth / Wi-Fi connection.

---

## 📈 14-Week Development Timeline
