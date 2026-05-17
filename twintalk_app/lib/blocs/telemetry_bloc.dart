// lib/blocs/telemetry_bloc.dart
import 'dart:async';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:equatable/equatable.dart';
import '../models/models.dart';
import '../services/rotor_connection_service.dart';

// ── Events ─────────────────────────────────────────────────────
abstract class TelemetryEvent extends Equatable {
  @override List<Object?> get props => [];
}

class TelemetrySubscriptionStarted extends TelemetryEvent {}
class TelemetrySubscriptionStopped extends TelemetryEvent {}

class _TelemetryReceived extends TelemetryEvent {
  final TelemetryData data;
  _TelemetryReceived(this.data);
  @override List<Object?> get props => [data];
}

// ── States ─────────────────────────────────────────────────────
abstract class TelemetryState extends Equatable {
  @override List<Object?> get props => [];
}

class TelemetryInitial extends TelemetryState {}

class TelemetryLoaded extends TelemetryState {
  final TelemetryData current;
  /// Ring buffer of the last 100 frames for the live chart.
  final List<TelemetryData> history;

  TelemetryLoaded({required this.current, required this.history});

  TelemetryLoaded copyWith({TelemetryData? current, List<TelemetryData>? history}) =>
      TelemetryLoaded(
        current: current ?? this.current,
        history: history ?? this.history,
      );

  @override List<Object?> get props => [current, history];
}

// ── BLoC ───────────────────────────────────────────────────────
class TelemetryBloc extends Bloc<TelemetryEvent, TelemetryState> {
  final RotorConnectionService _service;
  StreamSubscription<TelemetryData>? _sub;

  static const int _historyLimit = 100;

  TelemetryBloc(this._service) : super(TelemetryInitial()) {
    on<TelemetrySubscriptionStarted>(_onStart);
    on<TelemetrySubscriptionStopped>(_onStop);
    on<_TelemetryReceived>(_onReceived);
  }

  void _onStart(TelemetrySubscriptionStarted event, Emitter<TelemetryState> emit) {
    _sub?.cancel();
    _sub = _service.telemetryStream.listen(
      (data) => add(_TelemetryReceived(data)),
    );
  }

  void _onStop(TelemetrySubscriptionStopped event, Emitter<TelemetryState> emit) {
    _sub?.cancel();
    emit(TelemetryInitial());
  }

  void _onReceived(_TelemetryReceived event, Emitter<TelemetryState> emit) {
    final current = state;
    final history = current is TelemetryLoaded
        ? [...current.history, event.data]
        : [event.data];

    // Keep ring buffer bounded
    final trimmed =
        history.length > _historyLimit ? history.sublist(history.length - _historyLimit) : history;

    emit(TelemetryLoaded(current: event.data, history: trimmed));
  }

  @override
  Future<void> close() {
    _sub?.cancel();
    return super.close();
  }
}
