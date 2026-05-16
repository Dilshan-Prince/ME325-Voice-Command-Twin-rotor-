// lib/screens/telemetry_screen.dart
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../blocs/telemetry_bloc.dart';
import '../models/models.dart';
import '../theme/app_theme.dart';
import '../widgets/tt_widgets.dart';

class TelemetryScreen extends StatefulWidget {
  final bool isLive;
  const TelemetryScreen({super.key, this.isLive = false});

  @override
  State<TelemetryScreen> createState() => _TelemetryScreenState();
}

class _TelemetryScreenState extends State<TelemetryScreen> {
  // Simulated target values (set when a trajectory is approved)
  double _targetPitch = 30.0;
  double _targetYaw = 45.0;

  final List<Map<String, String>> _logs = [
    {'time': '09:41:02', 'msg': 'Trajectory approved by operator', 'lvl': 'ok'},
    {'time': '09:41:02', 'msg': 'Geometric controller engaged (SE3)', 'lvl': 'info'},
    {'time': '09:41:03', 'msg': 'PWM streaming → Raspberry Pi', 'lvl': 'info'},
    {'time': '09:41:04', 'msg': 'Pitch error 11.8° — converging', 'lvl': 'warn'},
    {'time': '09:41:05', 'msg': 'Ψ decreasing: 0.81 → 0.23', 'lvl': 'ok'},
  ];

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
                Text('Live Telemetry', style: AppTheme.titleMedium),
                if (widget.isLive)
                  Row(
                    children: [
                      _PulseDot(),
                      const SizedBox(width: 6),
                      Text('Executing',
                          style: AppTheme.labelSmall.copyWith(
                              color: AppTheme.success, fontSize: 11)),
                    ],
                  ),
              ],
            ),
          ),
          const Divider(),

          Expanded(
            child: BlocBuilder<TelemetryBloc, TelemetryState>(
              builder: (context, state) {
                final t = state is TelemetryLoaded
                    ? state.current
                    : TelemetryData.mock();
                final history = state is TelemetryLoaded ? state.history : <TelemetryData>[];

                return ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    // ── Pitch / Yaw gauges ─────────────────────
                    Row(
                      children: [
                        Expanded(
                          child: TTGauge(
                            label: 'Pitch',
                            current: t.pitchDeg,
                            target: _targetPitch,
                            barColor: AppTheme.primaryLight,
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: TTGauge(
                            label: 'Yaw',
                            current: t.yawDeg,
                            target: _targetYaw,
                            barColor: AppTheme.accent,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),

                    // ── PWM + Error row ────────────────────────
                    TTCard(
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceAround,
                        children: [
                          _MiniStat('R1 PWM', '${t.pwm1Us}', 'µs'),
                          _vDivider(),
                          _MiniStat('R2 PWM', '${t.pwm2Us}', 'µs'),
                          _vDivider(),
                          _MiniStat('Error Ψ', t.psiError.toStringAsFixed(2), '',
                              valueColor: AppTheme.primaryLight),
                        ],
                      ),
                    ),
                    const SizedBox(height: 12),

                    // ── Live chart ─────────────────────────────
                    if (history.length > 2) ...[
                      Text('Pitch history',
                          style: AppTheme.labelSmall.copyWith(fontSize: 11)),
                      const SizedBox(height: 8),
                      TTCard(
                        padding: const EdgeInsets.fromLTRB(8, 14, 14, 8),
                        child: SizedBox(
                          height: 120,
                          child: LineChart(
                            LineChartData(
                              gridData: FlGridData(
                                show: true,
                                drawVerticalLine: false,
                                getDrawingHorizontalLine: (v) => FlLine(
                                  color: AppTheme.borderFaint,
                                  strokeWidth: 0.5,
                                ),
                              ),
                              titlesData: FlTitlesData(
                                leftTitles: AxisTitles(
                                  sideTitles: SideTitles(
                                    showTitles: true,
                                    reservedSize: 30,
                                    getTitlesWidget: (v, _) => Text(
                                      v.toStringAsFixed(0),
                                      style: AppTheme.labelSmall.copyWith(fontSize: 9),
                                    ),
                                  ),
                                ),
                                bottomTitles: const AxisTitles(
                                    sideTitles: SideTitles(showTitles: false)),
                                topTitles: const AxisTitles(
                                    sideTitles: SideTitles(showTitles: false)),
                                rightTitles: const AxisTitles(
                                    sideTitles: SideTitles(showTitles: false)),
                              ),
                              borderData: FlBorderData(show: false),
                              lineBarsData: [
                                // Pitch line
                                LineChartBarData(
                                  spots: history.asMap().entries.map((e) =>
                                      FlSpot(e.key.toDouble(), e.value.pitchDeg)).toList(),
                                  isCurved: true,
                                  color: AppTheme.primaryLight,
                                  barWidth: 1.5,
                                  dotData: const FlDotData(show: false),
                                  belowBarData: BarAreaData(
                                    show: true,
                                    color: AppTheme.primaryLight.withValues(alpha: 0.05),
                                  ),
                                ),
                                // Target line
                                LineChartBarData(
                                  spots: [
                                    FlSpot(0, _targetPitch),
                                    FlSpot(history.length.toDouble(), _targetPitch),
                                  ],
                                  color: AppTheme.success.withValues(alpha: 0.4),
                                  barWidth: 1,
                                  dashArray: [4, 4],
                                  dotData: const FlDotData(show: false),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(height: 12),
                    ],

                    // ── System log ─────────────────────────────
                    Text('System log',
                        style: AppTheme.labelSmall.copyWith(fontSize: 11)),
                    const SizedBox(height: 8),
                    TTCard(
                      child: Column(
                        children: _logs.map((l) {
                          final lvl = switch (l['lvl']) {
                            'ok'   => LogLevel.ok,
                            'warn' => LogLevel.warn,
                            'err'  => LogLevel.error,
                            _      => LogLevel.info,
                          };
                          return TTLogEntry(
                              time: l['time']!, message: l['msg']!, level: lvl);
                        }).toList(),
                      ),
                    ),
                    const SizedBox(height: 12),

                    // ── Control strip ──────────────────────────
                    Row(
                      children: [
                        Expanded(
                          child: _CtrlButton(
                            icon: Icons.pause_circle_outline,
                            label: 'Pause',
                            onTap: () {},
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: _CtrlButton(
                            icon: Icons.stop_circle_outlined,
                            label: 'Stop',
                            isDanger: true,
                            onTap: () {},
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: _CtrlButton(
                            icon: Icons.download_outlined,
                            label: 'Log CSV',
                            onTap: () {},
                          ),
                        ),
                      ],
                    ),
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _vDivider() => Container(
        width: 0.5,
        height: 32,
        color: AppTheme.borderFaint,
      );
}

class _MiniStat extends StatelessWidget {
  final String label;
  final String value;
  final String unit;
  final Color? valueColor;

  const _MiniStat(this.label, this.value, this.unit, {this.valueColor});

  @override
  Widget build(BuildContext context) => Column(
        children: [
          Text(label, style: AppTheme.labelSmall),
          const SizedBox(height: 4),
          RichText(
            text: TextSpan(children: [
              TextSpan(
                text: value,
                style: TextStyle(
                  fontFamily: 'RobotoMono',
                  fontSize: 15,
                  fontWeight: FontWeight.w500,
                  color: valueColor ?? AppTheme.onSurface,
                ),
              ),
              if (unit.isNotEmpty)
                TextSpan(
                  text: ' $unit',
                  style: AppTheme.labelSmall.copyWith(fontSize: 9),
                ),
            ]),
          ),
        ],
      );
}

class _CtrlButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final bool isDanger;

  const _CtrlButton({
    required this.icon,
    required this.label,
    required this.onTap,
    this.isDanger = false,
  });

  @override
  Widget build(BuildContext context) {
    final color = isDanger ? AppTheme.danger : AppTheme.primaryLight;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 11),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: color.withValues(alpha: 0.3), width: 0.5),
        ),
        child: Column(
          children: [
            Icon(icon, size: 18, color: color),
            const SizedBox(height: 3),
            Text(label,
                style: AppTheme.labelSmall.copyWith(color: color, fontSize: 10)),
          ],
        ),
      ),
    );
  }
}

class _PulseDot extends StatefulWidget {
  @override
  State<_PulseDot> createState() => _PulseDotState();
}

class _PulseDotState extends State<_PulseDot>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _anim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 900))
      ..repeat(reverse: true);
    _anim = Tween<double>(begin: 0.3, end: 1.0).animate(_ctrl);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: _anim,
        builder: (_, __) => Container(
          width: 7,
          height: 7,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: AppTheme.success.withValues(alpha: _anim.value),
          ),
        ),
      );
}
