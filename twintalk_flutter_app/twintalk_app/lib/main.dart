// lib/main.dart
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import 'blocs/connection_bloc.dart';
import 'blocs/voice_bloc.dart';
import 'blocs/telemetry_bloc.dart';
import 'screens/home_screen.dart';
import 'services/agent_orchestrator.dart';
import 'services/rotor_connection_service.dart';
import 'services/whisper_service.dart';
import 'theme/app_theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // Force portrait mode — optimised for single-handed lab operation
  SystemChrome.setPreferredOrientations([
    DeviceOrientation.portraitUp,
    DeviceOrientation.portraitDown,
  ]);
  runApp(const TwinTalkApp());
}

class TwinTalkApp extends StatelessWidget {
  const TwinTalkApp({super.key});

  @override
  Widget build(BuildContext context) {
    // ── Singleton services ──────────────────────────────────────
    final rotorService      = RotorConnectionService();
    final whisperService    = WhisperService();
    final agentOrchestrator = AgentOrchestrator();

    return MultiRepositoryProvider(
      providers: [
        // Expose the connection service so child widgets can call
        // emergencyStop() etc. without going through BLoC
        RepositoryProvider<RotorConnectionService>.value(value: rotorService),
      ],
      child: MultiBlocProvider(
        providers: [
          BlocProvider(
            create: (_) => ConnectionBloc(rotorService),
          ),
          BlocProvider(
            create: (_) => VoiceBloc(whisperService, agentOrchestrator),
          ),
          BlocProvider(
            create: (_) => TelemetryBloc(rotorService),
            lazy: false, // Start listening as soon as app launches
          ),
        ],
        child: MaterialApp(
          title: 'TwinTalk',
          debugShowCheckedModeBanner: false,
          theme: AppTheme.dark,
          home: const HomeScreen(),
        ),
      ),
    );
  }
}
