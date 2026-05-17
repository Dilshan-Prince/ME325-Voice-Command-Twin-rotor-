// lib/services/agent_orchestrator.dart
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:logger/logger.dart';
import '../models/models.dart';

/// Communicates with the LangGraph multi-agent backend running on the
/// operator's laptop (Python FastAPI server wrapping LangGraph).
///
/// The backend exposes two endpoints:
///   POST /parse_intent   — NLP parsing of Whisper transcript
///   POST /gen_trajectory — Full trajectory generation from ParsedIntent
///
/// To run the backend: see /backend/README.md in the project repo.
class AgentOrchestrator {
  final Logger _log = Logger();

  /// IP of the laptop running LangGraph. Change to match your network.
  static const String _backendHost = '192.168.1.100';
  static const int _backendPort = 8000;
  static String get _base => 'http://$_backendHost:$_backendPort';

  // ── Parse Natural Language Intent ─────────────────────────────
  /// Sends the Whisper transcript to the LangGraph supervisor agent,
  /// which returns a ParsedIntent with pitch, yaw, duration, etc.
  Future<ParsedIntent> parseIntent(String transcript) async {
    _log.i('Parsing intent: "$transcript"');

    try {
      final resp = await http
          .post(
            Uri.parse('$_base/parse_intent'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'text': transcript}),
          )
          .timeout(const Duration(seconds: 10));

      if (resp.statusCode == 200) {
        final json = jsonDecode(resp.body) as Map<String, dynamic>;
        final intent = ParsedIntent.fromJson(json);
        _log.i('Intent parsed: pitch=${intent.pitchDeg}° yaw=${intent.yawDeg}°');
        return intent;
      } else {
        _log.e('Agent error ${resp.statusCode}: ${resp.body}');
        throw Exception('Agent error: ${resp.statusCode}');
      }
    } on Exception catch (e) {
      _log.w('Using mock intent (backend unreachable): $e');
      // Return a mock so the UI still works without the backend running
      return _mockIntent(transcript);
    }
  }

  // ── Generate Full Trajectory ───────────────────────────────────
  /// Takes a ParsedIntent and asks the trajectory-generation agent
  /// to build waypoints, select controller mode, and estimate duration.
  Future<TrajectoryCommand> generateTrajectory(ParsedIntent intent) async {
    _log.i('Generating trajectory...');

    try {
      final resp = await http
          .post(
            Uri.parse('$_base/gen_trajectory'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'pitch': intent.pitchDeg,
              'yaw': intent.yawDeg,
              'mode': intent.mode,
              'duration': intent.durationSec,
              'raw': intent.rawText,
            }),
          )
          .timeout(const Duration(seconds: 15));

      if (resp.statusCode == 200) {
        final json = jsonDecode(resp.body) as Map<String, dynamic>;
        return TrajectoryCommand.fromJson(json);
      } else {
        throw Exception('Trajectory generation error: ${resp.statusCode}');
      }
    } on Exception catch (e) {
      _log.w('Using mock trajectory (backend unreachable): $e');
      return intent.toTrajectoryCommand();
    }
  }

  // ── Mock helpers (for offline UI testing) ─────────────────────
  ParsedIntent _mockIntent(String text) {
    // Very simple heuristic extraction for demo without backend
    final pitchMatch = RegExp(r'pitch\s+(?:to\s+)?(\d+)').firstMatch(text.toLowerCase());
    final yawMatch = RegExp(r'yaw\s+(?:to\s+)?(\d+)').firstMatch(text.toLowerCase());
    final pitch = pitchMatch != null ? double.tryParse(pitchMatch.group(1)!) : 30.0;
    final yaw = yawMatch != null ? double.tryParse(yawMatch.group(1)!) : 45.0;

    return ParsedIntent(
      rawText: text,
      pitchDeg: pitch,
      yawDeg: yaw,
      durationSec: 4.0,
      mode: text.toLowerCase().contains('sweep') ? 'sweep' : 'step',
      requiresSimulation: true,
      chips: [
        if (pitch != null) 'pitch → ${pitch.toStringAsFixed(0)}°',
        if (yaw != null) 'yaw → ${yaw.toStringAsFixed(0)}°',
        'mode: ${text.toLowerCase().contains('sweep') ? 'sweep' : 'step'}',
      ],
    );
  }
}
