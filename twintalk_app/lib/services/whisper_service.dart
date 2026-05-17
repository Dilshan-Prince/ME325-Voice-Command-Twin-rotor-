// lib/services/whisper_service.dart
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:logger/logger.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

/// Wraps the OpenAI Whisper REST API for audio transcription.
///
/// SETUP: Add your OpenAI API key to lib/services/api_keys.dart (never commit it).
/// The app records audio to a temporary .m4a file, sends it to the
/// Whisper endpoint, and returns the transcribed text.
class WhisperService {
  final Logger _log = Logger();
  final AudioRecorder _recorder = AudioRecorder();

  // Replace with your OpenAI API key — see api_keys.dart
  static const String _apiKey = String.fromEnvironment(
    'OPENAI_API_KEY',
    defaultValue: 'YOUR_OPENAI_API_KEY_HERE',
  );

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
        sampleRate: 16000, // Whisper works best at 16 kHz
        numChannels: 1,    // Mono
        bitRate: 128000,
      ),
      path: _recordingPath!,
    );

    _isRecording = true;
    _log.i('Recording started → $_recordingPath');
  }

  // ── Stop and Transcribe ────────────────────────────────────────
  /// Stops recording, sends the audio to Whisper, returns transcript.
  Future<String> stopAndTranscribe() async {
    if (!_isRecording) return '';

    await _recorder.stop();
    _isRecording = false;

    if (_recordingPath == null) return '';

    _log.i('Recording stopped. Transcribing...');
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
    const url = 'https://api.openai.com/v1/audio/transcriptions';

    final request = http.MultipartRequest('POST', Uri.parse(url))
      ..headers['Authorization'] = 'Bearer $_apiKey'
      ..fields['model'] = 'whisper-1'
      ..fields['language'] = 'en'
      ..fields['response_format'] = 'text'
      ..files.add(await http.MultipartFile.fromPath('file', audioFile.path));

    final response = await request.send();
    final body = await response.stream.bytesToString();

    if (response.statusCode == 200) {
      return body.trim();
    } else {
      _log.e('Whisper API error ${response.statusCode}: $body');
      throw Exception('Transcription failed: ${response.statusCode}');
    }
  }

  void dispose() => _recorder.dispose();
}
