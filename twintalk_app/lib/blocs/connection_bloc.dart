// lib/blocs/connection/connection_bloc.dart
import 'dart:async';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:equatable/equatable.dart';
import '../../models/models.dart';
import '../../services/rotor_connection_service.dart';

// ── Events ─────────────────────────────────────────────────────
abstract class ConnectionEvent extends Equatable {
  @override List<Object?> get props => [];
}

class ConnectionConnectRequested extends ConnectionEvent {
  final String host;
  final int port;
  ConnectionConnectRequested({required this.host, required this.port});
  @override List<Object?> get props => [host, port];
}

class ConnectionDisconnectRequested extends ConnectionEvent {}

class _ConnectionStatusChanged extends ConnectionEvent {
  final ConnectionInfo info;
  _ConnectionStatusChanged(this.info);
  @override List<Object?> get props => [info];
}

// ── States ─────────────────────────────────────────────────────
abstract class ConnectionState extends Equatable {
  @override List<Object?> get props => [];
}

class ConnectionInitial extends ConnectionState {}

class ConnectionInProgress extends ConnectionState {}

class ConnectionConnected extends ConnectionState {
  final ConnectionInfo info;
  ConnectionConnected(this.info);
  @override List<Object?> get props => [info];
}

class ConnectionDisconnected extends ConnectionState {}

class ConnectionFailure extends ConnectionState {
  final String message;
  ConnectionFailure(this.message);
  @override List<Object?> get props => [message];
}

// ── BLoC ───────────────────────────────────────────────────────
class ConnectionBloc extends Bloc<ConnectionEvent, ConnectionState> {
  final RotorConnectionService _service;
  StreamSubscription<ConnectionInfo>? _sub;

  ConnectionBloc(this._service) : super(ConnectionInitial()) {
    on<ConnectionConnectRequested>(_onConnect);
    on<ConnectionDisconnectRequested>(_onDisconnect);
    on<_ConnectionStatusChanged>(_onStatusChanged);
  }

  Future<void> _onConnect(
      ConnectionConnectRequested event, Emitter<ConnectionState> emit) async {
    emit(ConnectionInProgress());

    _sub?.cancel();
    _sub = _service.connectionStream.listen(
      (info) => add(_ConnectionStatusChanged(info)),
    );

    await _service.connect(host: event.host, port: event.port);
  }

  Future<void> _onDisconnect(
      ConnectionDisconnectRequested event, Emitter<ConnectionState> emit) async {
    await _service.disconnect();
    emit(ConnectionDisconnected());
  }

  void _onStatusChanged(
      _ConnectionStatusChanged event, Emitter<ConnectionState> emit) {
    switch (event.info.status) {
      case ConnectionStatus.connected:
        emit(ConnectionConnected(event.info));
        break;
      case ConnectionStatus.disconnected:
        emit(ConnectionDisconnected());
        break;
      case ConnectionStatus.error:
        emit(ConnectionFailure(event.info.errorMessage ?? 'Unknown error'));
        break;
      default:
        break;
    }
  }

  @override
  Future<void> close() {
    _sub?.cancel();
    return super.close();
  }
}
