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
    try:
        model = await get_model()
        result = await asyncio.to_thread(
            model.transcribe,
            audio_path,
            # These parameters help with sentence segmentation
            word_timestamps=False,  # Disable word-level timestamps
            verbose=False,
            condition_on_previous_text=False  # Better sentence separation
        )

        # Return full sentences with their timestamps
        return [
            {
                "start": segment["start"],
                "end": segment["end"],
                "text": segment["text"].strip()
            }
            for segment in result.get("segments", [])
        ]

    except Exception as e:
        print(f"Transcription error: {e}")
        return []