import whisper
import os

def transcribe_audio(audio_path):
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    model = whisper.load_model("base")
    result = model.transcribe(audio_path)

    print(f"Audio transcribed successfully: {audio_path}")
    return result["text"], result["segments"]
