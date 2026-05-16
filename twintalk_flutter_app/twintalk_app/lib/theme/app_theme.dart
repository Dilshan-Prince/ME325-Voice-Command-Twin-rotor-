// lib/theme/app_theme.dart
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class AppTheme {
  // ── Brand Colours ──────────────────────────────────────────────
  static const Color primary       = Color(0xFF1565C0); // deep blue
  static const Color primaryLight  = Color(0xFF1E88E5);
  static const Color accent        = Color(0xFF7C4DFF); // purple (yaw)
  static const Color success       = Color(0xFF4CAF50);
  static const Color warning       = Color(0xFFFFC107);
  static const Color danger        = Color(0xFFF44336);
  static const Color surface       = Color(0xFF0D1117); // phone bg
  static const Color surfaceCard   = Color(0xFF161B22); // card bg
  static const Color surfaceElevated = Color(0xFF21262D);
  static const Color onSurface     = Color(0xFFFFFFFF);
  static const Color onSurfaceMid  = Color(0x99FFFFFF); // 60 %
  static const Color onSurfaceLow  = Color(0x40FFFFFF); // 25 %
  static const Color borderFaint   = Color(0x14FFFFFF); // 8 %

  // ── Text Styles ────────────────────────────────────────────────
  static TextStyle get displayLarge => GoogleFonts.inter(
    fontSize: 26, fontWeight: FontWeight.w500, color: onSurface,
    letterSpacing: -0.5,
  );
  static TextStyle get titleMedium => GoogleFonts.inter(
    fontSize: 16, fontWeight: FontWeight.w500, color: onSurface,
  );
  static TextStyle get bodyMedium => GoogleFonts.inter(
    fontSize: 14, fontWeight: FontWeight.w400, color: onSurfaceMid,
    height: 1.5,
  );
  static TextStyle get labelSmall => GoogleFonts.inter(
    fontSize: 10, fontWeight: FontWeight.w500, color: onSurfaceLow,
    letterSpacing: 0.08,
  );
  static TextStyle get monoSmall => GoogleFonts.robotoMono(
    fontSize: 11, fontWeight: FontWeight.w400, color: onSurfaceMid,
  );

  // ── ThemeData ──────────────────────────────────────────────────
  static ThemeData get dark => ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    scaffoldBackgroundColor: surface,
    colorScheme: const ColorScheme.dark(
      primary: primary,
      secondary: accent,
      surface: surfaceCard,
      error: danger,
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: surface,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: titleMedium,
      iconTheme: const IconThemeData(color: onSurfaceMid, size: 22),
    ),
    cardTheme: CardThemeData(
      color: surfaceCard,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: const BorderSide(color: borderFaint, width: 0.5),
      ),
      margin: EdgeInsets.zero,
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: primary,
        foregroundColor: onSurface,
        minimumSize: const Size.fromHeight(50),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        textStyle: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w500),
      ),
    ),
    textTheme: GoogleFonts.interTextTheme(ThemeData.dark().textTheme),
    dividerTheme: const DividerThemeData(
      color: borderFaint, thickness: 0.5, space: 0,
    ),
    bottomNavigationBarTheme: BottomNavigationBarThemeData(
      backgroundColor: surface,
      selectedItemColor: primaryLight,
      unselectedItemColor: onSurfaceLow,
      type: BottomNavigationBarType.fixed,
      selectedLabelStyle: GoogleFonts.inter(fontSize: 9, fontWeight: FontWeight.w500),
      unselectedLabelStyle: GoogleFonts.inter(fontSize: 9),
      elevation: 0,
    ),
  );
}
