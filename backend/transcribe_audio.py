import whisper
import asyncio
import os

WHISPER_MODEL = "base"
_model = None  # Lazy-load model only when needed

async def get_model():
    """Loads the Whisper model asynchronously if not already loaded."""
    global _model
    if _model is None:
        print(f"⏳ Loading Whisper-{WHISPER_MODEL} model...")
        _model = await asyncio.to_thread(whisper.load_model, WHISPER_MODEL)
        print(f"✅ Whisper-{WHISPER_MODEL} model loaded.")
    return _model

async def transcribe_audio(audio_path):
    """Transcribes an audio file asynchronously using Whisper."""
    try:
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"❌ Audio file not found: {audio_path}")

        model = await get_model()  # Ensure model is loaded

        print(f"🎙️ Transcribing: {audio_path} using Whisper-{WHISPER_MODEL}")

        result = await asyncio.to_thread(model.transcribe, audio_path)

        transcribed_text = result.get("text", "").strip()
        segments = result.get("segments", []) or []  # Ensure it's always a list

        print(f"✅ Transcription complete for: {audio_path}")

        return transcribed_text, segments  # ✅ Returning a tuple (fixes unpacking issue)

    except Exception as e:
        print(f"❌ Transcription error: {e}")
        return "", []  # ✅ Ensure a consistent return format in case of an error
