// lib/services/whisper_service.dart
import 'dart:io';
import 'package:logger/logger.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';
import 'package:google_generative_ai/google_generative_ai.dart' as genai;
import 'api_keys.dart';

/// Wraps the Google Gemini API for audio transcription.
///
/// SETUP: Add your Gemini API key to lib/services/api_keys.dart (never commit it).
/// The app records audio to a temporary .m4a file, sends it to the
/// Gemini 1.5 Flash model, and returns the transcribed text.
class WhisperService {
  final Logger _log = Logger();
  final AudioRecorder _recorder = AudioRecorder();

  // Gemini API key — see api_keys.dart
  static const String _apiKey = geminiApiKey;

  String? _recordingPath;
  bool _isRecording = false;

  bool get isRecording => _isRecording;

  // ── Start Recording ────────────────────────────────────────────
  Future<void> startRecording() async {
    final hasPermission = await _recorder.hasPermission();
    if (!hasPermission) {
      throw Exception('Microphone permission denied. Enable it in Settings.');
    }

    final dir = await getTemporaryDirectory();
    _recordingPath = '${dir.path}/twintalk_cmd_${DateTime.now().millisecondsSinceEpoch}.m4a';

    await _recorder.start(
      const RecordConfig(
        encoder: AudioEncoder.aacLc,
        sampleRate: 16000, // Gemini works great with 16 kHz audio
        numChannels: 1,    // Mono
        bitRate: 128000,
      ),
      path: _recordingPath!,
    );

    _isRecording = true;
    _log.i('Recording started → $_recordingPath');
  }

  // ── Stop and Transcribe ────────────────────────────────────────
  /// Stops recording, sends the audio to Gemini, returns transcript.
  Future<String> stopAndTranscribe() async {
    if (!_isRecording) return '';

    await _recorder.stop();
    _isRecording = false;

    if (_recordingPath == null) return '';

    _log.i('Recording stopped. Transcribing with Gemini...');
    final transcript = await _transcribeFile(File(_recordingPath!));
    _log.i('Transcript: "$transcript"');
    return transcript;
  }

  // ── Cancel ────────────────────────────────────────────────────
  Future<void> cancelRecording() async {
    if (_isRecording) {
      await _recorder.cancel();
      _isRecording = false;
    }
  }

  // ── API Call ───────────────────────────────────────────────────
  Future<String> _transcribeFile(File audioFile) async {
    try {
      final model = genai.GenerativeModel(
        model: 'gemini-2.5-flash',
        apiKey: _apiKey,
      );

      final audioBytes = await audioFile.readAsBytes();

      final response = await model.generateContent([
        genai.Content.multi([
          genai.TextPart(
            'Please transcribe this audio recording verbatim. '
            'Only output the transcript itself, with no added explanations, introductory comments, or punctuation/capitalization adjustments.',
          ),
          genai.DataPart('audio/m4a', audioBytes),
        ]),
      ]);

      final text = response.text;
      if (text == null || text.trim().isEmpty) {
        throw Exception('Empty response from Gemini API');
      }

      return text.trim();
    } catch (e) {
      _log.e('Gemini API error: $e');
      throw Exception('Transcription failed: $e');
    }
  }

  void dispose() => _recorder.dispose();
}
