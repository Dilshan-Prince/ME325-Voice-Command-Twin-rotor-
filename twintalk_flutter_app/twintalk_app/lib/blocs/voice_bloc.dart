// lib/blocs/voice_bloc.dart
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:equatable/equatable.dart';
import '../models/models.dart';
import '../services/whisper_service.dart';
import '../services/agent_orchestrator.dart';

// ── Events ─────────────────────────────────────────────────────
abstract class VoiceEvent extends Equatable {
  @override List<Object?> get props => [];
}

class VoiceRecordStarted extends VoiceEvent {}
class VoiceRecordStopped extends VoiceEvent {}
class VoiceRecordCancelled extends VoiceEvent {}
class VoiceRetryRequested extends VoiceEvent {}
class VoiceSendToAgentRequested extends VoiceEvent {}

// ── States ─────────────────────────────────────────────────────
abstract class VoiceState extends Equatable {
  @override List<Object?> get props => [];
}

class VoiceIdle extends VoiceState {}

class VoiceListening extends VoiceState {}

class VoiceTranscribing extends VoiceState {}

class VoiceTranscribed extends VoiceState {
  final String transcript;
  VoiceTranscribed(this.transcript);
  @override List<Object?> get props => [transcript];
}

class VoiceParsing extends VoiceState {
  final String transcript;
  VoiceParsing(this.transcript);
  @override List<Object?> get props => [transcript];
}

class VoiceParsed extends VoiceState {
  final String transcript;
  final ParsedIntent intent;
  VoiceParsed({required this.transcript, required this.intent});
  @override List<Object?> get props => [transcript, intent];
}

class VoiceGeneratingTrajectory extends VoiceState {
  final ParsedIntent intent;
  VoiceGeneratingTrajectory(this.intent);
  @override List<Object?> get props => [intent];
}

class VoiceTrajectoryReady extends VoiceState {
  final TrajectoryCommand trajectory;
  VoiceTrajectoryReady(this.trajectory);
  @override List<Object?> get props => [trajectory];
}

class VoiceError extends VoiceState {
  final String message;
  VoiceError(this.message);
  @override List<Object?> get props => [message];
}

// ── BLoC ───────────────────────────────────────────────────────
class VoiceBloc extends Bloc<VoiceEvent, VoiceState> {
  final WhisperService _whisper;
  final AgentOrchestrator _agent;

  VoiceBloc(this._whisper, this._agent) : super(VoiceIdle()) {
    on<VoiceRecordStarted>(_onStart);
    on<VoiceRecordStopped>(_onStop);
    on<VoiceRecordCancelled>(_onCancel);
    on<VoiceRetryRequested>(_onRetry);
    on<VoiceSendToAgentRequested>(_onSend);
  }

  Future<void> _onStart(VoiceRecordStarted event, Emitter<VoiceState> emit) async {
    try {
      await _whisper.startRecording();
      emit(VoiceListening());
    } catch (e) {
      emit(VoiceError(e.toString()));
    }
  }

  Future<void> _onStop(VoiceRecordStopped event, Emitter<VoiceState> emit) async {
    emit(VoiceTranscribing());
    try {
      final transcript = await _whisper.stopAndTranscribe();
      emit(VoiceTranscribed(transcript));

      emit(VoiceParsing(transcript));
      final intent = await _agent.parseIntent(transcript);
      emit(VoiceParsed(transcript: transcript, intent: intent));
    } catch (e) {
      emit(VoiceError(e.toString()));
    }
  }

  Future<void> _onCancel(VoiceRecordCancelled event, Emitter<VoiceState> emit) async {
    await _whisper.cancelRecording();
    emit(VoiceIdle());
  }

  Future<void> _onRetry(VoiceRetryRequested event, Emitter<VoiceState> emit) async {
    emit(VoiceIdle());
  }

  Future<void> _onSend(VoiceSendToAgentRequested event, Emitter<VoiceState> emit) async {
    final current = state;
    if (current is! VoiceParsed) return;

    emit(VoiceGeneratingTrajectory(current.intent));
    try {
      final traj = await _agent.generateTrajectory(current.intent);
      emit(VoiceTrajectoryReady(traj));
    } catch (e) {
      emit(VoiceError(e.toString()));
    }
  }

  @override
  Future<void> close() {
    _whisper.dispose();
    return super.close();
  }
}
