// lib/widgets/tt_card.dart  — Shared card, badge, stat, and log widgets

import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

// ── Base Card ─────────────────────────────────────────────────
class TTCard extends StatelessWidget {
  final Widget child;
  final EdgeInsets? padding;
  final Color? borderColor;

  const TTCard({super.key, required this.child, this.padding, this.borderColor});

  @override
  Widget build(BuildContext context) => Container(
        padding: padding ?? const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppTheme.surfaceCard,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: borderColor ?? AppTheme.borderFaint,
            width: 0.5,
          ),
        ),
        child: child,
      );
}

// ── Badge / Chip ──────────────────────────────────────────────
class TTBadge extends StatelessWidget {
  final String label;
  final Color color;
  final Color bgColor;
  final IconData? icon;

  const TTBadge({
    super.key,
    required this.label,
    required this.color,
    required this.bgColor,
    this.icon,
  });

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: bgColor,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: color.withValues(alpha: 0.3), width: 0.5),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (icon != null) ...[
              Icon(icon, size: 12, color: color),
              const SizedBox(width: 4),
            ],
            Text(label,
                style: AppTheme.labelSmall.copyWith(color: color, letterSpacing: 0)),
          ],
        ),
      );
}

// ── Connection Status Row ─────────────────────────────────────
class TTStatusRow extends StatelessWidget {
  final String label;
  final String value;
  final Color? dotColor;

  const TTStatusRow({
    super.key,
    required this.label,
    required this.value,
    this.dotColor,
  });

  @override
  Widget build(BuildContext context) => Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: AppTheme.labelSmall),
          Row(
            children: [
              if (dotColor != null) ...[
                Container(
                  width: 7,
                  height: 7,
                  margin: const EdgeInsets.only(right: 6),
                  decoration: BoxDecoration(
                    color: dotColor,
                    shape: BoxShape.circle,
                  ),
                ),
              ],
              Text(value,
                  style: AppTheme.bodyMedium.copyWith(
                    color: AppTheme.onSurface,
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                  )),
            ],
          ),
        ],
      );
}

// ── Stat Card ─────────────────────────────────────────────────
class TTStatCard extends StatelessWidget {
  final String label;
  final String value;
  final String unit;
  final Color? valueColor;

  const TTStatCard({
    super.key,
    required this.label,
    required this.value,
    this.unit = '',
    this.valueColor,
  });

  @override
  Widget build(BuildContext context) => TTCard(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: AppTheme.labelSmall),
            const SizedBox(height: 4),
            RichText(
              text: TextSpan(
                children: [
                  TextSpan(
                    text: value,
                    style: TextStyle(
                      fontFamily: 'RobotoMono',
                      fontSize: 20,
                      fontWeight: FontWeight.w500,
                      color: valueColor ?? AppTheme.onSurface,
                    ),
                  ),
                  TextSpan(
                    text: ' $unit',
                    style: AppTheme.labelSmall.copyWith(fontSize: 10),
                  ),
                ],
              ),
            ),
          ],
        ),
      );
}

// ── Progress Gauge ────────────────────────────────────────────
class TTGauge extends StatelessWidget {
  final String label;
  final double current;
  final double target;
  final String unit;
  final Color barColor;

  const TTGauge({
    super.key,
    required this.label,
    required this.current,
    required this.target,
    this.unit = '°',
    this.barColor = AppTheme.primaryLight,
  });

  @override
  Widget build(BuildContext context) {
    final fraction = target == 0 ? 0.0 : (current / target).clamp(0.0, 1.0);
    return TTCard(
      padding: const EdgeInsets.all(12),
      child: Column(
        children: [
          Text(label, style: AppTheme.labelSmall),
          const SizedBox(height: 6),
          Text(
            '${current.toStringAsFixed(1)}$unit',
            style: const TextStyle(
              fontFamily: 'RobotoMono',
              fontSize: 22,
              fontWeight: FontWeight.w500,
              color: AppTheme.onSurface,
            ),
          ),
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: fraction,
              minHeight: 4,
              backgroundColor: AppTheme.borderFaint,
              valueColor: AlwaysStoppedAnimation<Color>(barColor),
            ),
          ),
          const SizedBox(height: 4),
          Text(
            '→ ${target.toStringAsFixed(0)}$unit target',
            style: AppTheme.labelSmall.copyWith(
              color: barColor.withValues(alpha: 0.6),
              fontSize: 9,
            ),
          ),
        ],
      ),
    );
  }
}

// ── Quick Action Button ───────────────────────────────────────
class TTQuickButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final bool isDanger;

  const TTQuickButton({
    super.key,
    required this.icon,
    required this.label,
    required this.onTap,
    this.isDanger = false,
  });

  @override
  Widget build(BuildContext context) {
    final fg = isDanger ? AppTheme.danger : AppTheme.primaryLight;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
        decoration: BoxDecoration(
          color: fg.withValues(alpha: 0.1),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: fg.withValues(alpha: 0.35), width: 0.5),
        ),
        child: Row(
          children: [
            Icon(icon, size: 16, color: fg),
            const SizedBox(width: 6),
            Text(label,
                style: AppTheme.labelSmall.copyWith(
                    color: fg, fontSize: 12, letterSpacing: 0)),
          ],
        ),
      ),
    );
  }
}

// ── Log Entry ─────────────────────────────────────────────────
enum LogLevel { ok, info, warn, error }

class TTLogEntry extends StatelessWidget {
  final String time;
  final String message;
  final LogLevel level;

  const TTLogEntry({
    super.key,
    required this.time,
    required this.message,
    this.level = LogLevel.info,
  });

  Color get _color => switch (level) {
        LogLevel.ok    => const Color(0xFFA5D6A7),
        LogLevel.info  => const Color(0xFF90CAF9),
        LogLevel.warn  => const Color(0xFFFFD54F),
        LogLevel.error => const Color(0xFFEF9A9A),
      };

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(time, style: AppTheme.monoSmall.copyWith(fontSize: 10)),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                '▸ $message',
                style: AppTheme.monoSmall.copyWith(
                  fontSize: 11,
                  color: _color,
                ),
              ),
            ),
          ],
        ),
      );
}

// ── HiL Warning Box ───────────────────────────────────────────
class TTHiLWarning extends StatelessWidget {
  final String title;
  final String body;

  const TTHiLWarning({super.key, required this.title, required this.body});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: AppTheme.warning.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AppTheme.warning.withValues(alpha: 0.3), width: 0.5),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.shield_outlined, size: 18, color: AppTheme.warning),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title,
                      style: AppTheme.bodyMedium.copyWith(
                        color: const Color(0xFFFFD54F),
                        fontSize: 12,
                        fontWeight: FontWeight.w500,
                      )),
                  const SizedBox(height: 2),
                  Text(body, style: AppTheme.bodyMedium.copyWith(fontSize: 12)),
                ],
              ),
            ),
          ],
        ),
      );
}
