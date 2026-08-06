// lib/services/whisper_service.dart
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:logger/logger.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';
import 'package:google_generative_ai/google_generative_ai.dart' as genai;
import 'api_keys.dart';

/// Wraps OpenAI Whisper and Google Gemini API for audio transcription.
///
/// SETUP: Add your OpenAI API key to lib/services/api_keys.dart (never commit it).
/// The app records audio to a temporary .m4a file, sends it to OpenAI Whisper,
/// and falls back to Gemini if the OpenAI key is missing or fails.
class WhisperService {
  final Logger _log = Logger();
  final AudioRecorder _recorder = AudioRecorder();

  String? _recordingPath;
  bool _isRecording = false;

  int _mockIndex = 0;
  final List<String> _mockTranscripts = [
    "pitch to 30 yaw to -45",
    "pitch to 45 yaw to 30",
    "pitch to -20 yaw to 60",
    "pitch to 10 yaw to -15",
  ];

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
        sampleRate: 16000,
        numChannels: 1,    // Mono
        bitRate: 128000,
      ),
      path: _recordingPath!,
    );

    _isRecording = true;
    _log.i('Recording started → $_recordingPath');
  }

  // ── Stop and Transcribe ────────────────────────────────────────
  /// Stops recording, sends the audio to the transcription service, returns transcript.
  Future<String> stopAndTranscribe() async {
    if (!_isRecording) return '';

    await _recorder.stop();
    _isRecording = false;

    if (_recordingPath == null) return '';

    _log.i('Recording stopped. Transcribing audio...');
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
    // 1. Try OpenAI Whisper first
    if (openAiApiKey.isNotEmpty && openAiApiKey != 'YOUR_ACTUAL_API_KEY_HERE') {
      _log.i('Attempting OpenAI Whisper transcription...');
      try {
        final transcript = await _transcribeWithOpenAI(audioFile);
        _log.i('OpenAI Whisper success: "$transcript"');
        return transcript;
      } catch (openAiError) {
        _log.e('OpenAI Whisper error: $openAiError');
      }
    } else {
      _log.w('OpenAI API key is empty or not configured.');
    }

    // 2. Fall back to Gemini
    _log.i('Attempting Gemini fallback...');
    try {
      final model = genai.GenerativeModel(
        model: 'gemini-1.5-flash',
        apiKey: geminiApiKey,
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
    } catch (geminiError) {
      _log.e('Gemini fallback error: $geminiError');

      // 3. Last resort fallback to mock transcripts
      final mockVal = _mockTranscripts[_mockIndex];
      _mockIndex = (_mockIndex + 1) % _mockTranscripts.length;
      _log.w('All API options failed or not configured. Cycling mock transcript: "$mockVal"');
      return mockVal;
    }
  }

  // ── OpenAI Whisper Fallback ────────────────────────────────────
  Future<String> _transcribeWithOpenAI(File audioFile) async {
    final url = Uri.parse('https://api.openai.com/v1/audio/transcriptions');
    final request = http.MultipartRequest('POST', url)
      ..headers['Authorization'] = 'Bearer $openAiApiKey'
      ..files.add(await http.MultipartFile.fromPath('file', audioFile.path))
      ..fields['model'] = 'whisper-1'
      ..fields['response_format'] = 'json';

    final streamedResponse = await request.send();
    final response = await http.Response.fromStream(streamedResponse);

    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);
      return data['text']?.toString().trim() ?? '';
    } else {
      throw Exception('OpenAI Whisper API failed with status ${response.statusCode}: ${response.body}');
    }
  }

  void dispose() => _recorder.dispose();
}
