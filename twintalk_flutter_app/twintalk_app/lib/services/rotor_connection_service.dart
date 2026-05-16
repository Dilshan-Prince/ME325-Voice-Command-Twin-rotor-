// lib/services/rotor_connection_service.dart
import 'dart:async';
import 'dart:convert';
import 'package:logger/logger.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../models/models.dart';

/// Manages the WebSocket connection to the Raspberry Pi control server.
/// The Pi runs a Python asyncio WebSocket server on port 8765 that:
///   - Accepts JSON trajectory/command messages
///   - Streams back telemetry JSON at ~20 Hz
class RotorConnectionService {
  final Logger _log = Logger();

  WebSocketChannel? _channel;
  final _telemetryController = StreamController<TelemetryData>.broadcast();
  final _connectionController = StreamController<ConnectionInfo>.broadcast();

  ConnectionInfo _info = const ConnectionInfo(status: ConnectionStatus.disconnected);

  // ── Public Streams ─────────────────────────────────────────────
  Stream<TelemetryData> get telemetryStream => _telemetryController.stream;
  Stream<ConnectionInfo> get connectionStream => _connectionController.stream;
  ConnectionInfo get connectionInfo => _info;

  // ── Connect ────────────────────────────────────────────────────
  Future<void> connect({String host = '192.168.1.42', int port = 8765}) async {
    _updateConnection(_info.copyWith(
      status: ConnectionStatus.connecting, host: host, port: port,
    ));

    try {
      final uri = Uri.parse('ws://$host:$port');
      _channel = WebSocketChannel.connect(uri);

      // Wait for the handshake to complete
      await _channel!.ready;

      _updateConnection(_info.copyWith(status: ConnectionStatus.connected));
      _log.i('Connected to Twin Rotor Pi @ $host:$port');

      _channel!.stream.listen(
        _onMessage,
        onError: _onError,
        onDone: _onDisconnect,
      );
    } catch (e) {
      _log.e('Connection failed: $e');
      _updateConnection(_info.copyWith(
        status: ConnectionStatus.error,
        errorMessage: e.toString(),
      ));
    }
  }

  // ── Send Commands ──────────────────────────────────────────────

  /// Send an approved trajectory to the Pi for execution.
  void sendTrajectory(TrajectoryCommand cmd) {
    _send(cmd.toJson());
    _log.i('Trajectory sent: pitch=${cmd.targetPitchDeg}° yaw=${cmd.targetYawDeg}°');
  }

  /// Immediately halt all rotor motion.
  void emergencyStop() {
    _send({'cmd': 'ESTOP'});
    _log.w('EMERGENCY STOP issued');
  }

  /// Pause current trajectory execution.
  void pause() => _send({'cmd': 'PAUSE'});

  /// Resume a paused trajectory.
  void resume() => _send({'cmd': 'RESUME'});

  /// Request a single telemetry poll (useful on reconnect).
  void requestTelemetry() => _send({'cmd': 'TELEMETRY_POLL'});

  // ── Disconnect ─────────────────────────────────────────────────
  Future<void> disconnect() async {
    await _channel?.sink.close();
    _updateConnection(_info.copyWith(status: ConnectionStatus.disconnected));
  }

  // ── Private Helpers ────────────────────────────────────────────
  void _send(Map<String, dynamic> payload) {
    if (_channel == null || _info.status != ConnectionStatus.connected) {
      _log.w('Cannot send — not connected');
      return;
    }
    _channel!.sink.add(jsonEncode(payload));
  }

  void _onMessage(dynamic raw) {
    try {
      final Map<String, dynamic> json = jsonDecode(raw as String);
      final type = json['type'] as String? ?? 'telemetry';
      if (type == 'telemetry') {
        _telemetryController.add(TelemetryData.fromJson(json));
      } else {
        _log.d('Received message type "$type": $json');
      }
    } catch (e) {
      _log.e('Failed to parse message: $raw\nError: $e');
    }
  }

  void _onError(Object error) {
    _log.e('WebSocket error: $error');
    _updateConnection(_info.copyWith(
      status: ConnectionStatus.error,
      errorMessage: error.toString(),
    ));
  }

  void _onDisconnect() {
    _log.i('WebSocket disconnected');
    _updateConnection(_info.copyWith(status: ConnectionStatus.disconnected));
  }

  void _updateConnection(ConnectionInfo info) {
    _info = info;
    _connectionController.add(info);
  }

  void dispose() {
    _telemetryController.close();
    _connectionController.close();
    _channel?.sink.close();
  }
}
