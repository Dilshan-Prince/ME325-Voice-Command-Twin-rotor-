// lib/screens/voice_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../blocs/voice_bloc.dart';
import '../theme/app_theme.dart';
import '../widgets/tt_widgets.dart';
import 'trajectory_approval_screen.dart';

class VoiceScreen extends StatelessWidget {
  const VoiceScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return BlocListener<VoiceBloc, VoiceState>(
      listener: (context, state) {
        // Navigate to HiL approval when trajectory is ready
        if (state is VoiceTrajectoryReady) {
          Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) =>
                  TrajectoryApprovalScreen(trajectory: state.trajectory),
            ),
          );
        } else if (state is VoiceError) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(state.message),
              backgroundColor: AppTheme.danger,
            ),
          );
        }
      },
      child: SafeArea(
        child: Column(
          children: [
            // App bar
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 14, 16, 10),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text('Voice Command', style: AppTheme.titleMedium),
                  Row(
                    children: [
                      const Icon(Icons.psychology_outlined,
                          size: 14, color: AppTheme.onSurfaceMid),
                      const SizedBox(width: 4),
                      Text('Whisper ASR',
                          style: AppTheme.labelSmall
                              .copyWith(color: AppTheme.onSurfaceMid, fontSize: 11)),
                    ],
                  ),
                ],
              ),
            ),
            const Divider(),

            Expanded(
              child: BlocBuilder<VoiceBloc, VoiceState>(
                builder: (context, state) {
                  return Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        // ── Mic button ───────────────────────────
                        _MicButton(state: state),
                        const SizedBox(height: 16),

                        // ── State label ──────────────────────────
                        Text(
                          _stateLabel(state),
                          style: AppTheme.bodyMedium.copyWith(fontSize: 13),
                        ),
                        const SizedBox(height: 24),

                        // ── Transcript box ───────────────────────
                        _TranscriptBox(state: state),
                        const SizedBox(height: 16),

                        // ── Intent chips ─────────────────────────
                        if (state is VoiceParsed) ...[
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: [
                              TTBadge(
                                label: 'intent: trajectory',
                                color: const Color(0xFF90CAF9),
                                bgColor: const Color(0x1490CAF9),
                              ),
                              ...state.intent.chips.map(
                                (c) => TTBadge(
                                  label: c,
                                  color: const Color(0xFFA5D6A7),
                                  bgColor: const Color(0x14A5D6A7),
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 24),
                        ],

                        // ── Action buttons ───────────────────────
                        _ActionButtons(state: state),
                      ],
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _stateLabel(VoiceState state) => switch (state) {
        VoiceIdle()               => 'Tap the mic to start speaking',
        VoiceListening()          => 'Listening — speak your command…',
        VoiceTranscribing()       => 'Transcribing with Whisper…',
        VoiceTranscribed()        => 'Transcript received',
        VoiceParsing()            => 'AI agent parsing intent…',
        VoiceParsed()             => 'Intent parsed — review and send',
        VoiceGeneratingTrajectory() => 'Generating trajectory…',
        VoiceTrajectoryReady()    => 'Trajectory ready',
        VoiceError()              => 'Error — try again',
        _                         => '',
      };
}

// ── Mic Button ─────────────────────────────────────────────────
class _MicButton extends StatelessWidget {
  final VoiceState state;
  const _MicButton({required this.state});

  bool get _isListening => state is VoiceListening;
  bool get _isBusy =>
      state is VoiceTranscribing ||
      state is VoiceParsing ||
      state is VoiceGeneratingTrajectory;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: _isBusy
          ? null
          : () {
              if (_isListening) {
                context.read<VoiceBloc>().add(VoiceRecordStopped());
              } else {
                context.read<VoiceBloc>().add(VoiceRecordStarted());
              }
            },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 300),
        width: 110,
        height: 110,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: _isListening
              ? AppTheme.primaryLight.withValues(alpha: 0.2)
              : AppTheme.primary.withValues(alpha: 0.12),
          border: Border.all(
            color: _isListening
                ? AppTheme.primaryLight
                : AppTheme.primary.withValues(alpha: 0.5),
            width: _isListening ? 2 : 1,
          ),
        ),
        child: Center(
          child: Container(
            width: 72,
            height: 72,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: _isBusy ? AppTheme.surfaceElevated : AppTheme.primary,
            ),
            child: _isBusy
                ? const Center(
                    child: SizedBox(
                      width: 24,
                      height: 24,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: AppTheme.primaryLight),
                    ),
                  )
                : Icon(
                    _isListening ? Icons.stop : Icons.mic,
                    size: 32,
                    color: Colors.white,
                  ),
          ),
        ),
      ),
    );
  }
}

// ── Transcript Box ─────────────────────────────────────────────
class _TranscriptBox extends StatelessWidget {
  final VoiceState state;
  const _TranscriptBox({required this.state});

  String get _text => switch (state) {
        VoiceTranscribed(transcript: final t) => t,
        VoiceParsing(transcript: final t)     => t,
        VoiceParsed(transcript: final t)      => t,
        _                                     => '',
      };

  @override
  Widget build(BuildContext context) => TTCard(
        child: SizedBox(
          width: double.infinity,
          child: _text.isEmpty
              ? Text(
                  'Your transcribed command will appear here…',
                  style: AppTheme.bodyMedium.copyWith(
                    fontStyle: FontStyle.italic,
                    color: AppTheme.onSurfaceLow,
                  ),
                )
              : Text(_text,
                  style: AppTheme.bodyMedium.copyWith(
                    color: AppTheme.onSurface,
                    fontSize: 14,
                  )),
        ),
      );
}

// ── Action Buttons ─────────────────────────────────────────────
class _ActionButtons extends StatelessWidget {
  final VoiceState state;
  const _ActionButtons({required this.state});

  @override
  Widget build(BuildContext context) {
    if (state is! VoiceParsed) return const SizedBox.shrink();

    return Row(
      children: [
        Expanded(
          child: OutlinedButton.icon(
            onPressed: () =>
                context.read<VoiceBloc>().add(VoiceRetryRequested()),
            icon: const Icon(Icons.refresh, size: 16),
            label: const Text('Retry'),
            style: OutlinedButton.styleFrom(
              foregroundColor: AppTheme.onSurfaceMid,
              side: const BorderSide(color: AppTheme.borderFaint, width: 0.5),
              padding: const EdgeInsets.symmetric(vertical: 13),
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12)),
            ),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          flex: 2,
          child: ElevatedButton.icon(
            onPressed: () =>
                context.read<VoiceBloc>().add(VoiceSendToAgentRequested()),
            icon: const Icon(Icons.send, size: 16),
            label: const Text('Send to Agent'),
            style: ElevatedButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 13),
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12)),
            ),
          ),
        ),
      ],
    );
  }
}
