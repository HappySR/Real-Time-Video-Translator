import httpx
import asyncio
import subprocess
import torch
import os

# LibreTranslate endpoint
LIBRETRANSLATE_URL = "http://127.0.0.1:5000/detect"

# Speaker WAV file path (must be a real file)
SPEAKER_WAV = "sample_voice/sample_voice.wav"  # Update this path

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

async def text_to_speech(text, output_audio_path, target_language=None, max_retries=3):
    """Converts text to speech with retry logic"""
    try:
        if not text.strip():
            raise ValueError("❌ Empty text input for TTS")

        # Validate speaker file exists
        if not os.path.exists(SPEAKER_WAV):
            raise FileNotFoundError(f"❌ Speaker WAV file not found: {SPEAKER_WAV}")

        # Determine language code
        detected_lang = target_language if target_language else await detect_language(text)
        coqui_lang = LANGUAGE_MAP.get(detected_lang.lower(), "en")

        # Determine CUDA availability
        use_cuda = "true" if torch.cuda.is_available() else "false"

        for attempt in range(max_retries):
            try:
                command = [
                    "tts",
                    "--model_name", "tts_models/multilingual/multi-dataset/xtts_v2",
                    "--text", text,
                    "--out_path", output_audio_path,
                    "--use_cuda", use_cuda,
                    "--speaker_wav", SPEAKER_WAV,
                    "--language_idx", coqui_lang,  # Using correct parameter name
                    # "--output_sample_rate", "44100"
                ]

                print(f"🔊 TTS attempt {attempt + 1} for: {text[:50]}...")
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await process.communicate()
                
                if process.returncode == 0:
                    if os.path.exists(output_audio_path):
                        print(f"✅ TTS successful: {output_audio_path}")
                        return output_audio_path
                    else:
                        raise FileNotFoundError("TTS output file not created")
                else:
                    raise RuntimeError(stderr.decode().strip())

            except Exception as e:
                if attempt == max_retries - 1:
                    raise RuntimeError(f"❌ TTS failed after {max_retries} attempts: {str(e)}")
                
                print(f"⚠️ TTS attempt {attempt + 1} failed, retrying...")
                await asyncio.sleep(1)  # Wait before retrying

    except Exception as e:
        print(f"❌ Final TTS error: {e}")
        raise