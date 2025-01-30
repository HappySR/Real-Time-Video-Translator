from flask import Flask, request, jsonify
import os
import ffmpeg
import whisper
import requests
from extract_audio import extract_audio
from transcribe_audio import transcribe_audio
from translate_text import translate_text
from generate_subtitles import generate_srt
from text_to_speech import text_to_speech

app = Flask(__name__)

@app.route("/")
def index():
    return "Flask app is running!"

@app.route("/process_video", methods=["POST"])
def process_video():
    try:
        # Upload video
        file = request.files["video"]
        video_path = os.path.join("temp", file.filename)
        file.save(video_path)

        # Extract audio from video
        audio_path = video_path.replace(".mp4", ".mp3")
        extract_audio(video_path, audio_path)

        # Transcribe audio using Whisper
        transcript, segments = transcribe_audio(audio_path)

        # Generate subtitles for English and Hindi languages based on the transcript
        srt_path_en = video_path.replace(".mp4", "_en.srt")
        srt_path_hi = video_path.replace(".mp4", "_hi.srt")
        generate_srt(transcript, segments, srt_path_en)
        translated_transcript = translate_text(transcript, "hi")
        generate_srt(translated_transcript, segments, srt_path_hi)

        # Convert transcripts to speech for both languages
        tts_en_path = video_path.replace(".mp4", "_en.mp3")
        tts_hi_path = video_path.replace(".mp4", "_hi.mp3")
        text_to_speech(transcript, tts_en_path)
        text_to_speech(translated_transcript, tts_hi_path)

        # Prepare final output paths and store them accordingly
        final_video_no_audio = video_path.replace(".mp4", "_no_audio.mp4")
        ffmpeg.input(video_path).output(final_video_no_audio, an=None).run()

        return jsonify({
            "message": "Processed successfully",
            "srt_paths": {"english": srt_path_en, "hindi": srt_path_hi},
            "audio_paths": {"original": audio_path, "english_tts": tts_en_path, "hindi_tts": tts_hi_path},
            "video_no_audio": final_video_no_audio,
        })

    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == "__main__":
    app.run(debug=True)
