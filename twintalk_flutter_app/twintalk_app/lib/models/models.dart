// lib/models/trajectory_command.dart
import 'dart:convert';

/// Controller algorithm used on the Raspberry Pi.
enum ControllerMode { pid, lqr, geometric }

/// A single angular waypoint in pitch-yaw space.
class Waypoint {
  final double pitchDeg;
  final double yawDeg;
  final double atTimeSec;

  const Waypoint({
    required this.pitchDeg,
    required this.yawDeg,
    required this.atTimeSec,
  });

  Map<String, dynamic> toJson() => {
        'pitch': pitchDeg,
        'yaw': yawDeg,
        'time': atTimeSec,
      };

  factory Waypoint.fromJson(Map<String, dynamic> j) => Waypoint(
        pitchDeg: (j['pitch'] as num).toDouble(),
        yawDeg: (j['yaw'] as num).toDouble(),
        atTimeSec: (j['time'] as num).toDouble(),
      );
}

/// Full trajectory command sent to the AI orchestrator and eventually
/// to the Raspberry Pi after HiL approval.
class TrajectoryCommand {
  final double targetPitchDeg;
  final double targetYawDeg;
  final double durationSec;
  final ControllerMode mode;
  final List<Waypoint> waypoints;
  final String rawVoiceText;
  final DateTime createdAt;

  const TrajectoryCommand({
    required this.targetPitchDeg,
    required this.targetYawDeg,
    required this.durationSec,
    this.mode = ControllerMode.geometric,
    this.waypoints = const [],
    this.rawVoiceText = '',
    required this.createdAt,
  });

  Map<String, dynamic> toJson() => {
        'cmd': 'TRAJECTORY',
        'pitch': targetPitchDeg,
        'yaw': targetYawDeg,
        'duration': durationSec,
        'mode': mode.name,
        'waypoints': waypoints.map((w) => w.toJson()).toList(),
        'ts': createdAt.millisecondsSinceEpoch,
      };

  String toJsonString() => jsonEncode(toJson());

  factory TrajectoryCommand.fromJson(Map<String, dynamic> j) => TrajectoryCommand(
        targetPitchDeg: (j['pitch'] as num).toDouble(),
        targetYawDeg: (j['yaw'] as num).toDouble(),
        durationSec: (j['duration'] as num).toDouble(),
        mode: ControllerMode.values.firstWhere((m) => m.name == j['mode'],
            orElse: () => ControllerMode.geometric),
        waypoints: (j['waypoints'] as List? ?? [])
            .map((w) => Waypoint.fromJson(w as Map<String, dynamic>))
            .toList(),
        rawVoiceText: j['raw'] as String? ?? '',
        createdAt: DateTime.fromMillisecondsSinceEpoch(j['ts'] as int? ?? 0),
      );
}

// ─────────────────────────────────────────────────────────────────
// lib/models/telemetry_data.dart
/// Real-time telemetry frame streamed from the Raspberry Pi.
class TelemetryData {
  final double pitchDeg;
  final double yawDeg;
  final int pwm1Us;     // Main rotor PWM (µs)
  final int pwm2Us;     // Tail rotor PWM (µs)
  final double psiError; // Geometric attitude error Ψ ∈ [0, 2]
  final DateTime timestamp;

  const TelemetryData({
    required this.pitchDeg,
    required this.yawDeg,
    required this.pwm1Us,
    required this.pwm2Us,
    required this.psiError,
    required this.timestamp,
  });

  factory TelemetryData.fromJson(Map<String, dynamic> j) => TelemetryData(
        pitchDeg: (j['pitch'] as num).toDouble(),
        yawDeg: (j['yaw'] as num).toDouble(),
        pwm1Us: (j['pwm1'] as num).toInt(),
        pwm2Us: (j['pwm2'] as num).toInt(),
        psiError: (j['psi'] as num? ?? 0).toDouble(),
        timestamp: DateTime.now(),
      );

  /// Returns a mock frame useful for UI testing without hardware.
  factory TelemetryData.mock() => TelemetryData(
        pitchDeg: 12.4,
        yawDeg: -5.1,
        pwm1Us: 1480,
        pwm2Us: 1520,
        psiError: 0.23,
        timestamp: DateTime.now(),
      );
}

// ─────────────────────────────────────────────────────────────────
// lib/models/parsed_intent.dart
/// Result returned by the LangGraph AI orchestrator after parsing
/// the Whisper transcript.
class ParsedIntent {
  final String rawText;
  final double? pitchDeg;
  final double? yawDeg;
  final double? durationSec;
  final String mode; // 'sweep', 'step', 'hover', etc.
  final bool requiresSimulation;
  final List<String> chips; // human-readable parsed tokens for UI

  const ParsedIntent({
    required this.rawText,
    this.pitchDeg,
    this.yawDeg,
    this.durationSec,
    this.mode = 'step',
    this.requiresSimulation = true,
    this.chips = const [],
  });

  bool get isComplete => pitchDeg != null && yawDeg != null;

  TrajectoryCommand toTrajectoryCommand() => TrajectoryCommand(
        targetPitchDeg: pitchDeg ?? 0,
        targetYawDeg: yawDeg ?? 0,
        durationSec: durationSec ?? 3.0,
        mode: ControllerMode.geometric,
        rawVoiceText: rawText,
        createdAt: DateTime.now(),
      );

  factory ParsedIntent.fromJson(Map<String, dynamic> j) => ParsedIntent(
        rawText: j['raw'] as String? ?? '',
        pitchDeg: (j['pitch'] as num?)?.toDouble(),
        yawDeg: (j['yaw'] as num?)?.toDouble(),
        durationSec: (j['duration'] as num?)?.toDouble(),
        mode: j['mode'] as String? ?? 'step',
        requiresSimulation: j['sim'] as bool? ?? true,
        chips: List<String>.from(j['chips'] as List? ?? []),
      );
}

// ─────────────────────────────────────────────────────────────────
// lib/models/connection_state.dart
enum ConnectionStatus { disconnected, connecting, connected, error }

class ConnectionInfo {
  final ConnectionStatus status;
  final String host;
  final int port;
  final String? errorMessage;

  const ConnectionInfo({
    required this.status,
    this.host = '192.168.1.42',
    this.port = 8765,
    this.errorMessage,
  });

  bool get isConnected => status == ConnectionStatus.connected;

  ConnectionInfo copyWith({
    ConnectionStatus? status,
    String? host,
    int? port,
    String? errorMessage,
  }) =>
      ConnectionInfo(
        status: status ?? this.status,
        host: host ?? this.host,
        port: port ?? this.port,
        errorMessage: errorMessage ?? this.errorMessage,
      );
}
