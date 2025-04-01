import httpx
import asyncio
import subprocess
import torch
import os
from pydub import AudioSegment

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

async def generate_tts_segments(chunks: list, output_dir: str, target_language: str) -> list:
    """
    Generate TTS audio for complete subtitle chunks
    Args:
        chunks: List of {'texts': list, 'start': float, 'end': float}
        output_dir: Output directory
        target_language: Target language code
    Returns:
        List of (audio_path, start, end)
    """
    os.makedirs(output_dir, exist_ok=True)
    results = []

    for idx, chunk in enumerate(chunks):
        try:
            # Combine all phrases in the chunk and clean brackets
            full_text = " ".join(chunk["texts"])
            # Remove surrounding square brackets
            full_text = full_text.strip('[]')  # <-- ADD THIS LINE
            duration = chunk["end"] - chunk["start"]
            
            output_path = os.path.join(
                output_dir,
                f"chunk_{idx}_{chunk['start']:.2f}-{chunk['end']:.2f}.wav"
            )

            success = await text_to_speech(
                text=full_text,
                output_audio_path=output_path,
                target_language=target_language,
                duration=duration
            )
            
            if success:
                results.append((output_path, chunk["start"], chunk["end"]))

        except Exception as e:
            print(f"⚠️ Failed to generate TTS for chunk {idx}: {e}")

    return results

# Modified text_to_speech function
async def text_to_speech(text, output_audio_path, target_language=None, duration=None, max_retries=3):
    """Converts text to speech with post-processing duration control"""
    try:
        cleaned_text = text.strip("['']")
        if not text.strip():
            raise ValueError("❌ Empty text input for TTS")

        if not os.path.exists(SPEAKER_WAV):
            raise FileNotFoundError(f"❌ Speaker WAV file not found: {SPEAKER_WAV}")

        detected_lang = target_language if target_language else await detect_language(cleaned_text)
        coqui_lang = LANGUAGE_MAP.get(detected_lang.lower(), "en")

        command = [
            "tts",
            "--model_name", "tts_models/multilingual/multi-dataset/xtts_v2",
            "--text", cleaned_text,
            "--out_path", output_audio_path,
            "--speaker_wav", SPEAKER_WAV,
            "--language_idx", coqui_lang
        ]

        if torch.cuda.is_available():
            command += ["--use_cuda", "true"]

        # Generate initial TTS without speed adjustment
        for attempt in range(max_retries):
            try:
                print(f"🔊 TTS attempt {attempt + 1} for: {cleaned_text[:50]}...")
                
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                stdout, stderr = await process.communicate()
                
                if process.returncode == 0 and os.path.exists(output_audio_path):
                    # Post-process speed adjustment if duration is specified
                    if duration and duration > 0:
                        adjust_audio_speed(output_audio_path, duration)
                    print(f"✅ TTS successful: {output_audio_path}")
                    return True
                
                print(f"❌ TTS error: {stderr.decode().strip()}")
                
            except Exception as e:
                print(f"⚠️ TTS attempt {attempt + 1} failed: {str(e)}")
                if attempt == max_retries - 1:
                    raise RuntimeError(f"❌ TTS failed after {max_retries} attempts")
                await asyncio.sleep(1)

        return False
    except Exception as e:
        print(f"❌ Final TTS error: {str(e)}")
        return False

def adjust_audio_speed(file_path, target_duration):
    """Adjust audio speed with safety checks"""
    try:
        if target_duration <= 0.1:  # Minimum 100ms duration
            print("⏩ Skipping invalid target duration")
            return

        audio = AudioSegment.from_file(file_path)
        current_duration = len(audio) / 1000
        
        if current_duration <= 0.1:
            print("⏩ Invalid audio duration")
            return

        speed_factor = current_duration / target_duration
        speed_factor = max(0.5, min(2.0, speed_factor))

        # Preserve audio characteristics
        adjusted = audio.speedup(
            playback_speed=speed_factor,
            chunk_size=150,  # Smoother speed adjustment
            crossfade=25     # Prevent audio artifacts
        )
        
        # Ensure exact duration
        if len(adjusted) > target_duration * 1000:
            adjusted = adjusted[:int(target_duration * 1000)]
            
        adjusted.export(file_path, format="wav")
        print(f"⚡ Adjusted {os.path.basename(file_path)} by {speed_factor:.2f}x")

    except Exception as e:
        print(f"⚠️ Speed adjustment failed: {str(e)}")