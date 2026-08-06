// lib/screens/status_screen.dart
import 'package:flutter/material.dart' hide ConnectionState;
import 'package:flutter_bloc/flutter_bloc.dart';
import '../blocs/connection_bloc.dart';
import '../blocs/telemetry_bloc.dart';
import '../models/models.dart';
import '../services/rotor_connection_service.dart';
import '../theme/app_theme.dart';
import '../widgets/tt_widgets.dart';
import 'voice_screen.dart';
import 'telemetry_screen.dart';

/// Main shell screen with BottomNavigationBar.
/// Index 0 = Status, 1 = Voice, 2 = Telemetry
class StatusScreen extends StatefulWidget {
  const StatusScreen({super.key});

  @override
  State<StatusScreen> createState() => _StatusScreenState();
}

class _StatusScreenState extends State<StatusScreen> {
  int _index = 0;

  late final List<Widget> _pages;

  @override
  void initState() {
    super.initState();
    _pages = [
      _StatusTab(onTabChanged: (i) => setState(() => _index = i)),
      const VoiceScreen(),
      const TelemetryScreen(),
    ];
    // Start listening for telemetry as soon as status screen opens
    context.read<TelemetryBloc>().add(TelemetrySubscriptionStarted());
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(index: _index, children: _pages),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _index,
        onTap: (i) => setState(() => _index = i),
        items: const [
          BottomNavigationBarItem(
              icon: Icon(Icons.home_outlined), label: 'Home'),
          BottomNavigationBarItem(
              icon: Icon(Icons.mic_outlined), label: 'Voice'),
          BottomNavigationBarItem(
              icon: Icon(Icons.show_chart), label: 'Telemetry'),
        ],
      ),
    );
  }
}

// ── Status Tab ────────────────────────────────────────────────
class _StatusTab extends StatelessWidget {
  final Function(int) onTabChanged;
  const _StatusTab({required this.onTabChanged});

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Column(
        children: [
          // App bar
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 10),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('System Status', style: AppTheme.titleMedium),
                IconButton(
                  icon: const Icon(Icons.settings_outlined,
                      color: AppTheme.onSurfaceMid, size: 22),
                  onPressed: () {},
                ),
              ],
            ),
          ),
          const Divider(),

          Expanded(
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                // ── Connection card ────────────────────────────
                BlocBuilder<ConnectionBloc, ConnectionState>(
                  builder: (context, state) {
                    final isConnected = state is ConnectionConnected;
                    return TTCard(
                      child: Column(
                        children: [
                          TTStatusRow(
                            label: 'Laptop Server Link',
                            value: isConnected ? 'Connected' : 'Disconnected',
                            dotColor: isConnected
                                ? AppTheme.success
                                : AppTheme.danger,
                          ),
                          const SizedBox(height: 10),
                          TTStatusRow(
                            label: 'Server Address',
                            value: isConnected
                                ? 'Wi-Fi · ${(state).info.host}'
                                : '—',
                          ),
                          const SizedBox(height: 10),
                          const TTStatusRow(
                            label: 'Controller Mode',
                            value: 'Geometric · SE(3)',
                          ),
                        ],
                      ),
                    );
                  },
                ),
                const SizedBox(height: 12),

                // ── Live stat grid ─────────────────────────────
                BlocBuilder<TelemetryBloc, TelemetryState>(
                  builder: (context, state) {
                    final t = state is TelemetryLoaded
                        ? state.current
                        : TelemetryData.mock();
                    return GridView.count(
                      crossAxisCount: 2,
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      crossAxisSpacing: 8,
                      mainAxisSpacing: 8,
                      childAspectRatio: 1.6,
                      children: [
                        TTStatCard(
                          label: 'Pitch',
                          value: t.pitchDeg.toStringAsFixed(1),
                          unit: '°',
                        ),
                        TTStatCard(
                          label: 'Yaw',
                          value: t.yawDeg.toStringAsFixed(1),
                          unit: '°',
                        ),
                        TTStatCard(
                          label: 'R1 PWM',
                          value: t.pwm1Us.toString(),
                          unit: 'µs',
                        ),
                        TTStatCard(
                          label: 'R2 PWM',
                          value: t.pwm2Us.toString(),
                          unit: 'µs',
                        ),
                      ],
                    );
                  },
                ),
                const SizedBox(height: 12),

                // ── Quick actions ──────────────────────────────
                GridView.count(
                  crossAxisCount: 3,
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  crossAxisSpacing: 8,
                  mainAxisSpacing: 8,
                  childAspectRatio: 1.1,
                  children: [
                    TTQuickButton(
                      icon: Icons.mic_outlined,
                      label: 'Voice Cmd',
                      onTap: () => onTabChanged(1),
                    ),
                    TTQuickButton(
                      icon: Icons.show_chart,
                      label: 'Live Plot',
                      onTap: () => onTabChanged(2),
                    ),
                    TTQuickButton(
                      icon: Icons.stop_circle_outlined,
                      label: 'E-Stop',
                      onTap: () {
                        // Emergency stop — bypass all confirmations
                        showDialog(
                          context: context,
                          builder: (dialogContext) => AlertDialog(
                            backgroundColor: AppTheme.surfaceCard,
                            title: Text('Emergency Stop',
                                style: AppTheme.titleMedium
                                    .copyWith(color: AppTheme.danger)),
                            content: Text(
                              'This will immediately halt all rotor motion.',
                              style: AppTheme.bodyMedium,
                            ),
                            actions: [
                              TextButton(
                                onPressed: () => Navigator.pop(dialogContext),
                                child: const Text('Cancel'),
                              ),
                              ElevatedButton(
                                style: ElevatedButton.styleFrom(
                                    backgroundColor: AppTheme.danger),
                                onPressed: () {
                                  context.read<RotorConnectionService>().emergencyStop();
                                  Navigator.pop(dialogContext);
                                },
                                child: const Text('STOP'),
                              ),
                            ],
                          ),
                        );
                      },
                      isDanger: true,
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
