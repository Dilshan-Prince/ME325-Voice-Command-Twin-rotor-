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
                      Text('Gemini ASR',
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
        VoiceIdle()               => 'Press and hold the mic to speak',
        VoiceListening()          => 'Listening — release to process…',
        VoiceTranscribing()       => 'Transcribing with Gemini…',
        VoiceTranscribed()        => 'Transcript received',
        VoiceParsing()            => 'AI agent parsing intent…',
        VoiceParsed()             => 'Intent parsed — review and send',
        VoiceGeneratingTrajectory() => 'Generating trajectory…',
        VoiceTrajectoryReady()    => 'Trajectory ready',
        VoiceError()              => 'Error — try again',
        _                         => '',
      };
}

// ── Mic Button (Siri-like Animated Hold-to-Speak) ───────────────
class _MicButton extends StatefulWidget {
  final VoiceState state;
  const _MicButton({required this.state});

  @override
  State<_MicButton> createState() => _MicButtonState();
}

class _MicButtonState extends State<_MicButton> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _pulseAnimation;
  bool _isHolding = false;

  bool get _isListening => widget.state is VoiceListening;
  bool get _isBusy =>
      widget.state is VoiceTranscribing ||
      widget.state is VoiceParsing ||
      widget.state is VoiceGeneratingTrajectory;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    );
    _pulseAnimation = Tween<double>(begin: 1.0, end: 1.22).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );
  }

  @override
  void didUpdateWidget(covariant _MicButton oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (_isListening) {
      _controller.repeat(reverse: true);

      // Async Startup Guard: If user has already released the hold before
      // the async recording start completed, stop it immediately.
      if (!_isHolding) {
        final voiceBloc = context.read<VoiceBloc>();
        Future.delayed(const Duration(milliseconds: 100), () {
          if (mounted && widget.state is VoiceListening) {
            voiceBloc.add(VoiceRecordStopped());
          }
        });
      }
    } else {
      _controller.stop();
      _controller.reset();
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTapDown: _isBusy
          ? null
          : (_) {
              _isHolding = true;
              if (!_isListening) {
                context.read<VoiceBloc>().add(VoiceRecordStarted());
              }
            },
      onTapUp: _isBusy
          ? null
          : (_) {
              _isHolding = false;
              if (_isListening) {
                final voiceBloc = context.read<VoiceBloc>();
                // Short guard to allow the recorder to initialize properly
                Future.delayed(const Duration(milliseconds: 150), () {
                  if (mounted && widget.state is VoiceListening) {
                    voiceBloc.add(VoiceRecordStopped());
                  }
                });
              }
            },
      onTapCancel: _isBusy
          ? null
          : () {
              _isHolding = false;
              if (_isListening) {
                context.read<VoiceBloc>().add(VoiceRecordStopped());
              }
            },
      child: AnimatedBuilder(
        animation: _pulseAnimation,
        builder: (context, child) {
          final scale = _isListening ? _pulseAnimation.value : 1.0;
          return Container(
            width: 120 * scale,
            height: 120 * scale,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              boxShadow: _isListening
                  ? [
                      BoxShadow(
                        color: AppTheme.primaryLight.withValues(alpha: 0.3 * (2.0 - scale)),
                        blurRadius: 15 * scale,
                        spreadRadius: 5 * scale,
                      )
                    ]
                  : [],
              color: _isListening
                  ? AppTheme.primaryLight.withValues(alpha: 0.15)
                  : AppTheme.primary.withValues(alpha: 0.08),
              border: Border.all(
                color: _isListening
                    ? AppTheme.primaryLight
                    : AppTheme.primary.withValues(alpha: 0.4),
                width: _isListening ? 2 : 1.5,
              ),
            ),
            child: Center(
              child: Container(
                width: 76,
                height: 76,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: _isListening
                      ? const LinearGradient(
                          colors: [AppTheme.primaryLight, Color(0xFF64B5F6)],
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                        )
                      : const LinearGradient(
                          colors: [AppTheme.primary, Color(0xFF1E88E5)],
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                        ),
                  boxShadow: [
                    BoxShadow(
                      color: (_isListening ? AppTheme.primaryLight : AppTheme.primary)
                          .withValues(alpha: 0.4),
                      blurRadius: 10,
                      offset: const Offset(0, 4),
                    )
                  ],
                ),
                child: _isBusy
                    ? const Center(
                        child: SizedBox(
                          width: 24,
                          height: 24,
                          child: CircularProgressIndicator(
                            strokeWidth: 2.5,
                            color: Colors.white,
                          ),
                        ),
                      )
                    : Icon(
                        _isListening ? Icons.mic : Icons.mic_none_outlined,
                        size: 34,
                        color: Colors.white,
                      ),
              ),
            ),
          );
        },
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
