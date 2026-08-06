// lib/screens/trajectory_approval_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../models/models.dart';
import '../services/agent_orchestrator.dart';
import '../theme/app_theme.dart';
import '../widgets/tt_widgets.dart';
import 'telemetry_screen.dart';

/// Human-in-the-Loop (HiL) gate: shows the trajectory preview and
/// requires explicit operator approval before any PWM command is sent.
class TrajectoryApprovalScreen extends StatelessWidget {
  final TrajectoryCommand trajectory;

  const TrajectoryApprovalScreen({super.key, required this.trajectory});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Approve Trajectory'),
        actions: [
          Container(
            margin: const EdgeInsets.only(right: 12),
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
            decoration: BoxDecoration(
              color: AppTheme.warning.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(
                  color: AppTheme.warning.withValues(alpha: 0.4), width: 0.5),
            ),
            child: Text('HiL Review',
                style: AppTheme.labelSmall
                    .copyWith(color: AppTheme.warning, fontSize: 11)),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            // ── 2D Trajectory Preview ────────────────────────────
            _TrajectoryPreview(trajectory: trajectory),
            const Divider(),

            // ── Scrollable parameters ────────────────────────────
            Expanded(
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  // Parameter grid
                  GridView.count(
                    crossAxisCount: 2,
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    crossAxisSpacing: 8,
                    mainAxisSpacing: 8,
                    childAspectRatio: 1.8,
                    children: [
                      TTStatCard(
                        label: 'Target Pitch',
                        value: trajectory.targetPitchDeg.toStringAsFixed(1),
                        unit: '°',
                      ),
                      TTStatCard(
                        label: 'Target Yaw',
                        value: trajectory.targetYawDeg.toStringAsFixed(1),
                        unit: '°',
                      ),
                      TTStatCard(
                        label: 'Duration',
                        value: trajectory.durationSec.toStringAsFixed(1),
                        unit: 's',
                      ),
                      TTStatCard(
                        label: 'Controller',
                        value: trajectory.mode.name.toUpperCase(),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),

                  // Voice command that triggered this
                  if (trajectory.rawVoiceText.isNotEmpty) ...[
                    TTCard(
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Icon(Icons.mic_outlined,
                              size: 16, color: AppTheme.onSurfaceMid),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              '"${trajectory.rawVoiceText}"',
                              style: AppTheme.bodyMedium.copyWith(
                                fontStyle: FontStyle.italic,
                                fontSize: 13,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 12),
                  ],

                  // HiL warning box
                  const TTHiLWarning(
                    title: 'Human-in-the-Loop Review',
                    body:
                        'The trajectory preview is shown above. Approving will '
                        'immediately send the command to the Laptop Server and '
                        'trigger the MeshCat 3D simulation animation.',
                  ),
                  const SizedBox(height: 12),

                  // Waypoints list (if any)
                  if (trajectory.waypoints.isNotEmpty) ...[
                    Text('Waypoints',
                        style: AppTheme.labelSmall.copyWith(fontSize: 11)),
                    const SizedBox(height: 8),
                    ...trajectory.waypoints.asMap().entries.map((e) {
                      final i = e.key + 1;
                      final w = e.value;
                      return Padding(
                        padding: const EdgeInsets.only(bottom: 6),
                        child: TTCard(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 14, vertical: 10),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text('WP$i',
                                  style: AppTheme.bodyMedium
                                      .copyWith(fontWeight: FontWeight.w500)),
                              Text(
                                  'P: ${w.pitchDeg.toStringAsFixed(1)}°  Y: ${w.yawDeg.toStringAsFixed(1)}°  t: ${w.atTimeSec.toStringAsFixed(1)}s',
                                  style: AppTheme.monoSmall),
                            ],
                          ),
                        ),
                      );
                    }),
                  ],
                ],
              ),
            ),

            // ── Approve / Cancel ─────────────────────────────────
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Row(
                children: [
                  // Cancel
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () {
                        try {
                          context.read<AgentOrchestrator>().authorizeMovement(false);
                        } catch (_) {}
                        Navigator.pop(context);
                      },
                      icon: const Icon(Icons.close, size: 16),
                      label: const Text('Cancel'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: AppTheme.danger,
                        side: BorderSide(
                            color: AppTheme.danger.withValues(alpha: 0.4),
                            width: 0.5),
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(14)),
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),

                  // Approve
                  Expanded(
                    flex: 2,
                    child: ElevatedButton.icon(
                      onPressed: () => _approve(context),
                      icon: const Icon(Icons.check, size: 16),
                      label: const Text('Approve & Execute'),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF1B5E20),
                        foregroundColor: const Color(0xFFA5D6A7),
                        side: const BorderSide(
                            color: AppTheme.success, width: 0.5),
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(14)),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _approve(BuildContext context) {
    // Release the safety gate on the Laptop Server
    try {
      context.read<AgentOrchestrator>().authorizeMovement(true);
    } catch (_) {}

    // Navigate to live telemetry
    Navigator.pushReplacement(
      context,
      MaterialPageRoute(builder: (_) => const TelemetryScreen(isLive: true)),
    );
  }
}

// ── Trajectory 2D Preview (CustomPaint) ─────────────────────────
class _TrajectoryPreview extends StatelessWidget {
  final TrajectoryCommand trajectory;
  const _TrajectoryPreview({required this.trajectory});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 160,
      child: CustomPaint(
        painter: _TrajPainter(trajectory: trajectory),
        child: Container(),
      ),
    );
  }
}

class _TrajPainter extends CustomPainter {
  final TrajectoryCommand trajectory;
  _TrajPainter({required this.trajectory});

  @override
  void paint(Canvas canvas, Size size) {
    final gridPaint = Paint()
      ..color = Colors.white.withValues(alpha: 0.05)
      ..strokeWidth = 0.5;

    // Grid
    for (double x = 0; x < size.width; x += 24) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), gridPaint);
    }
    for (double y = 0; y < size.height; y += 24) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), gridPaint);
    }

    // Axes (Centered Crosshair)
    final axisPaint = Paint()
      ..color = Colors.white.withValues(alpha: 0.12)
      ..strokeWidth = 1;
    // Horizontal axis (Yaw/X)
    canvas.drawLine(Offset(20, size.height / 2),
        Offset(size.width - 20, size.height / 2), axisPaint);
    // Vertical axis (Pitch/Y)
    canvas.drawLine(Offset(size.width / 2, 20),
        Offset(size.width / 2, size.height - 20), axisPaint);

    // Map pitch/yaw to canvas coords
    // Pitch → Y axis (up), Yaw → X axis (right)
    final maxAngle = 80.0;
    double toX(double yaw) =>
        (size.width / 2) + (yaw / maxAngle) * ((size.width - 40) / 2);
    double toY(double pitch) =>
        (size.height / 2) - (pitch / maxAngle) * ((size.height - 40) / 2);

    // Start point (current: 0,0)
    final start = Offset(toX(0), toY(0));
    final end =
        Offset(toX(trajectory.targetYawDeg), toY(trajectory.targetPitchDeg));

    // Path
    final pathPaint = Paint()
      ..color = AppTheme.primaryLight
      ..strokeWidth = 1.5
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    final path = Path()..moveTo(start.dx, start.dy);
    final cp1 = Offset(start.dx + (end.dx - start.dx) * 0.4, start.dy);
    final cp2 = Offset(start.dx + (end.dx - start.dx) * 0.6, end.dy);
    path.cubicTo(cp1.dx, cp1.dy, cp2.dx, cp2.dy, end.dx, end.dy);

    // Dashed path
    _drawDashed(canvas, path, pathPaint);

    // Arrow head at end
    final arrowPaint = Paint()..color = AppTheme.primaryLight;
    canvas.drawCircle(end, 5, arrowPaint);

    // Start dot (green)
    canvas.drawCircle(start, 5, Paint()..color = AppTheme.success);

    // Labels
    _label(canvas, start + const Offset(8, -14), 'Current', AppTheme.success);
    _label(
        canvas, end + const Offset(8, -14), 'Target', const Color(0xFFCE93D8));

    // Waypoints
    for (final wp in trajectory.waypoints) {
      final pt = Offset(toX(wp.yawDeg), toY(wp.pitchDeg));
      canvas.drawCircle(
          pt, 4, Paint()..color = AppTheme.warning.withValues(alpha: 0.8));
    }
  }

  void _drawDashed(Canvas canvas, Path path, Paint paint) {
    const dashLength = 6.0;
    const gapLength = 4.0;
    final metrics = path.computeMetrics();
    for (final metric in metrics) {
      double dist = 0;
      while (dist < metric.length) {
        final start = metric.getTangentForOffset(dist)!.position;
        final end = metric
            .getTangentForOffset((dist + dashLength).clamp(0, metric.length))!
            .position;
        canvas.drawLine(start, end, paint);
        dist += dashLength + gapLength;
      }
    }
  }

  void _label(Canvas canvas, Offset pos, String text, Color color) {
    final tp = TextPainter(
      text: TextSpan(
          text: text,
          style: TextStyle(color: color, fontSize: 9, fontFamily: 'Inter')),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, pos);
  }

  @override
  bool shouldRepaint(_TrajPainter old) => old.trajectory != trajectory;
}
