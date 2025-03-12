import httpx
import asyncio
import subprocess
import torch

# LibreTranslate endpoint
LIBRETRANSLATE_URL = "http://127.0.0.1:5000/detect"

# **UPDATE THIS**: Provide a real `.wav` file of any speaker  
SPEAKER_WAV = "sample_voice/sample_voice.wav"  # Replace with actual path

# Language mapping for Coqui TTS
LANGUAGE_MAP = {
    "en": "en", "hi": "hi", "bn": "bn", "ta": "ta",
    "te": "te", "mr": "mr", "gu": "gu", "pa": "pa",
    "kn": "kn", "ml": "ml"
}

async def detect_language(text):
    """Detects language using LibreTranslate."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(LIBRETRANSLATE_URL, json={"q": text})
            response.raise_for_status()
            result = response.json()

            # Ensure result is correctly formatted
            if isinstance(result, list) and result:
                result = result[0]  # Extract first element if it's a list

            detected_lang = result.get("language", "en") if isinstance(result, dict) else "en"
            return detected_lang

        except httpx.RequestError as e:
            print(f"🚨 Language detection failed: {e}")
            return "en"

async def text_to_speech(text, output_audio_path, target_language=None):
    """Converts text to speech using Coqui TTS."""
    try:
        # Ensure text is a string
        if isinstance(text, list):
            text = " ".join(text)  # Convert list to string

        text = text.strip()
        if not text:
            raise ValueError("❌ The input text is empty.")

        # Detect language if not provided
        detected_lang = target_language if target_language else await detect_language(text)
        coqui_lang = LANGUAGE_MAP.get(detected_lang, "en")

        # Determine CUDA availability
        use_cuda = "true" if torch.cuda.is_available() else "false"

        # **YOU NEED A REAL WAV FILE FOR XTTS v2**
        if not SPEAKER_WAV or SPEAKER_WAV == "path/to/a_real_speaker.wav":
            raise ValueError("❌ You must provide a real speaker `.wav` file!")

        # Command for TTS
        command = [
            "tts", "--model_name", "tts_models/multilingual/multi-dataset/xtts_v2",
            "--text", text,  # Directly pass text
            "--out_path", output_audio_path,
            "--use_cuda", use_cuda,
            "--speaker_wav", SPEAKER_WAV,  # Use real speaker WAV
            "--language_idx", coqui_lang
        ]

        print(f"🔹 Running TTS command: {' '.join(command)}")

        process = await asyncio.create_subprocess_exec(
            *command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            print(f"✅ TTS audio generated: {output_audio_path}")
            return output_audio_path
        else:
            error_message = stderr.decode().strip()
            print(f"❌ TTS generation failed: {error_message}")
            raise RuntimeError(error_message)

    except Exception as e:
        print(f"❌ TTS error: {e}")
        raise
