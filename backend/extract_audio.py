import asyncio
import os
import shutil
import subprocess

async def extract_audio(video_path, output_audio_path):
    """Extracts audio from a video file asynchronously using FFmpeg."""
    try:
        # Check if FFmpeg is installed
        if not shutil.which("ffmpeg"):
            raise EnvironmentError("❌ FFmpeg is not installed or not found in system PATH.")

        # Ensure output directory exists
        output_dir = os.path.dirname(output_audio_path)
        os.makedirs(output_dir, exist_ok=True)

        # Determine audio format from file extension
        audio_ext = os.path.splitext(output_audio_path)[-1].lower()
        codec = "libmp3lame" if audio_ext == ".mp3" else "pcm_s16le" if audio_ext == ".wav" else "aac"

        # FFmpeg command to extract audio
        command = [
            "ffmpeg", "-y", "-i", video_path, "-vn",  # Remove video
            "-acodec", codec, output_audio_path
        ]

        # Run FFmpeg process asynchronously
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            print(f"✅ Audio extracted successfully: {output_audio_path}")
            return output_audio_path
        else:
            error_message = stderr.decode().strip()
            print(f"❌ Error extracting audio: {error_message}")
            return None  # Return None instead of raising an error

    except Exception as e:
        print(f"❌ Exception in extract_audio: {e}")
        return None  # Return None for better error handling

def extract_audio_sync(video_path, output_audio_path):
    """Synchronous version of extract_audio() for non-async functions."""
    try:
        # Ensure FFmpeg exists
        if not shutil.which("ffmpeg"):
            raise EnvironmentError("❌ FFmpeg is not installed or not found in system PATH.")

        # Ensure output directory exists
        output_dir = os.path.dirname(output_audio_path)
        os.makedirs(output_dir, exist_ok=True)

        # Determine audio format
        audio_ext = os.path.splitext(output_audio_path)[-1].lower()
        codec = "libmp3lame" if audio_ext == ".mp3" else "pcm_s16le" if audio_ext == ".wav" else "aac"

        # FFmpeg command
        command = [
            "ffmpeg", "-y", "-i", video_path, "-vn",
            "-acodec", codec, output_audio_path
        ]

        # Run FFmpeg process synchronously
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if result.returncode == 0:
            print(f"✅ Audio extracted successfully: {output_audio_path}")
            return output_audio_path
        else:
            error_message = result.stderr.decode().strip()
            print(f"❌ Error extracting audio: {error_message}")
            return None

    except Exception as e:
        print(f"❌ Exception in extract_audio_sync: {e}")
        return None
