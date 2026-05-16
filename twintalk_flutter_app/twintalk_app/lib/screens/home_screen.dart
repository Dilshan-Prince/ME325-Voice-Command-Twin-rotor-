// lib/screens/home_screen.dart
import 'package:flutter/material.dart' hide ConnectionState;
import 'package:flutter_bloc/flutter_bloc.dart';
import '../blocs/connection_bloc.dart';
import '../theme/app_theme.dart';
import '../widgets/tt_widgets.dart';
import 'status_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _hostController = TextEditingController(text: '192.168.1.42');
  final _portController = TextEditingController(text: '8765');

  @override
  void dispose() {
    _hostController.dispose();
    _portController.dispose();
    super.dispose();
  }

  void _connect(BuildContext context) {
    final host = _hostController.text.trim();
    final port = int.tryParse(_portController.text.trim()) ?? 8765;
    context.read<ConnectionBloc>().add(
          ConnectionConnectRequested(host: host, port: port),
        );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: BlocListener<ConnectionBloc, ConnectionState>(
        listener: (context, state) {
          if (state is ConnectionConnected) {
            Navigator.pushReplacement(
              context,
              MaterialPageRoute(builder: (_) => const StatusScreen()),
            );
          } else if (state is ConnectionFailure) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text('Connection failed: ${state.message}'),
                backgroundColor: AppTheme.danger,
              ),
            );
          }
        },
        child: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                const SizedBox(height: 40),

                // ── Logo ─────────────────────────────────────────
                Container(
                  width: 88,
                  height: 88,
                  decoration: BoxDecoration(
                    color: AppTheme.primary,
                    borderRadius: BorderRadius.circular(24),
                  ),
                  child: const Icon(Icons.air, size: 48, color: Colors.white),
                ),
                const SizedBox(height: 24),

                // ── Title ─────────────────────────────────────────
                Text('TwinTalk', style: AppTheme.displayLarge),
                const SizedBox(height: 8),
                Text(
                  'Voice-Actuated Control\nfor Twin Rotor V1.0',
                  textAlign: TextAlign.center,
                  style: AppTheme.bodyMedium,
                ),
                const SizedBox(height: 20),

                // ── Capability badges ─────────────────────────────
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  alignment: WrapAlignment.center,
                  children: const [
                    TTBadge(
                      label: 'AI Agent',
                      color: Color(0xFF90CAF9),
                      bgColor: Color(0x1490CAF9),
                      icon: Icons.psychology_outlined,
                    ),
                    TTBadge(
                      label: 'Geometric Control',
                      color: Color(0xFF80CBC4),
                      bgColor: Color(0x1480CBC4),
                      icon: Icons.rotate_90_degrees_ccw_outlined,
                    ),
                    TTBadge(
                      label: 'HiL Safety',
                      color: Color(0xFFFFD54F),
                      bgColor: Color(0x14FFD54F),
                      icon: Icons.shield_outlined,
                    ),
                  ],
                ),
                const SizedBox(height: 48),

                // ── Connection form ───────────────────────────────
                TTCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Raspberry Pi Connection',
                          style: AppTheme.titleMedium.copyWith(fontSize: 14)),
                      const SizedBox(height: 16),
                      _field('Host / IP Address', _hostController,
                          hint: '192.168.1.42'),
                      const SizedBox(height: 12),
                      _field('Port', _portController,
                          hint: '8765', keyboard: TextInputType.number),
                    ],
                  ),
                ),
                const SizedBox(height: 16),

                // ── Connect button ────────────────────────────────
                BlocBuilder<ConnectionBloc, ConnectionState>(
                  builder: (context, state) {
                    final isLoading = state is ConnectionInProgress;
                    return ElevatedButton.icon(
                      onPressed: isLoading ? null : () => _connect(context),
                      icon: isLoading
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(
                                  strokeWidth: 2, color: Colors.white),
                            )
                          : const Icon(Icons.bluetooth_searching),
                      label: Text(
                          isLoading ? 'Connecting…' : 'Connect to Twin Rotor'),
                    );
                  },
                ),
                const SizedBox(height: 16),

                // ── Demo mode (no hardware) ───────────────────────
                TextButton(
                  onPressed: () {
                    Navigator.pushReplacement(
                      context,
                      MaterialPageRoute(builder: (_) => const StatusScreen()),
                    );
                  },
                  child: Text(
                    'Continue in Demo Mode (no hardware)',
                    style: AppTheme.labelSmall.copyWith(
                      color: AppTheme.onSurfaceMid,
                      fontSize: 12,
                    ),
                  ),
                ),

                const SizedBox(height: 32),
                Text('ME 325 · Engineering Design · 2026',
                    style: AppTheme.labelSmall),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _field(
    String label,
    TextEditingController ctrl, {
    String hint = '',
    TextInputType keyboard = TextInputType.text,
  }) =>
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: AppTheme.labelSmall.copyWith(fontSize: 11)),
          const SizedBox(height: 6),
          TextField(
            controller: ctrl,
            keyboardType: keyboard,
            style: AppTheme.bodyMedium.copyWith(color: AppTheme.onSurface),
            decoration: InputDecoration(
              hintText: hint,
              hintStyle:
                  AppTheme.bodyMedium.copyWith(color: AppTheme.onSurfaceLow),
              filled: true,
              fillColor: AppTheme.surfaceElevated,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide:
                    const BorderSide(color: AppTheme.borderFaint, width: 0.5),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide:
                    const BorderSide(color: AppTheme.borderFaint, width: 0.5),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide:
                    const BorderSide(color: AppTheme.primaryLight, width: 1),
              ),
              contentPadding:
                  const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            ),
          ),
        ],
      );
}
