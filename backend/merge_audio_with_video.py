import asyncio
import ffmpeg
import os
import uuid

TEMP_DIR = "temp/"
os.makedirs(TEMP_DIR, exist_ok=True)  # Ensure temp directory exists

async def merge_audio_segments(audio_segments, output_audio):
    """Merges multiple audio segments into a single audio file while maintaining alignment."""
    try:
        if not audio_segments:
            raise ValueError("No audio segments provided for merging.")

        concat_list_path = os.path.join("temp", "concat_list.txt")
        with open(concat_list_path, "w", encoding="utf-8") as f:
            print("🔍 Debugging Audio Segments Paths:")
            for segment in audio_segments:
                print(os.path.normpath(segment))
                if isinstance(segment, tuple):
                    segment = segment[0]  # Extract only the file path

                # Ensure segment path is correct
                if not os.path.isabs(segment):  
                    segment_path = os.path.join("temp", os.path.basename(segment))  # Avoid double "temp/"
                else:
                    segment_path = segment  # If absolute, use as is

                segment_path = os.path.normpath(segment_path)  # Normalize path
                if not os.path.exists(segment_path):
                    raise FileNotFoundError(f"Audio segment not found: {segment_path}")

                f.write(f"file '{segment_path}'\n")

        # Merge audio segments using FFmpeg
        merge_command = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path,
            "-c", "copy", output_audio
        ]
        process_merge = await asyncio.create_subprocess_exec(*merge_command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await process_merge.communicate()

        if process_merge.returncode == 0:
            print(f"✅ Merged audio segments successfully: {output_audio}")
            os.remove(concat_list_path)  # Clean up temp file list
            return output_audio
        else:
            print(f"⚠️ Error merging audio segments: {stderr.decode().strip()}")
            raise RuntimeError(stderr.decode().strip())

    except Exception as e:
        print(f"⚠️ Exception in merge_audio_segments: {e}")
        raise

async def adjust_audio_duration(original_audio, translated_audio, output_audio):
    """Adjusts translated audio duration to match original video length."""
    try:
        original_duration = float(ffmpeg.probe(original_audio)["format"]["duration"])
        translated_duration = float(ffmpeg.probe(translated_audio)["format"]["duration"])

        speed_factor = original_duration / translated_duration
        atempo_filters = []

        while speed_factor > 2.0:
            atempo_filters.append("atempo=2.0")
            speed_factor /= 2.0
        while speed_factor < 0.5:
            atempo_filters.append("atempo=0.5")
            speed_factor *= 2.0
        atempo_filters.append(f"atempo={speed_factor}")
        atempo_filter = ",".join(atempo_filters)

        adjusted_audio = os.path.join(TEMP_DIR, f"adjusted_{uuid.uuid4().hex}.mp3")
        command = ["ffmpeg", "-y", "-i", translated_audio, "-filter:a", atempo_filter, "-vn", adjusted_audio]

        process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            print(f"✅ Adjusted TTS duration: {adjusted_audio}")
            return adjusted_audio
        else:
            raise RuntimeError(f"⚠️ Error adjusting TTS audio: {stderr.decode().strip()}")

    except Exception as e:
        print(f"⚠️ Exception in adjust_audio_duration: {e}")
        raise


async def merge_audio_with_video(video_no_audio, adjusted_audio, final_video):
    """Merges adjusted TTS audio with silent video efficiently."""
    try:
        print(f"🔄 Merging video: {video_no_audio} with audio: {adjusted_audio}")

        trimmed_audio = os.path.join(TEMP_DIR, f"trimmed_{uuid.uuid4().hex}.mp3")
        trim_command = [
            "ffmpeg", "-y", "-i", adjusted_audio, "-af", "silenceremove=start_periods=1", trimmed_audio
        ]
        process_trim = await asyncio.create_subprocess_exec(*trim_command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await process_trim.communicate()
        if process_trim.returncode != 0:
            print("⚠️ Error trimming silence, using original audio.")
            trimmed_audio = adjusted_audio  # Fallback

        converted_audio = os.path.join(TEMP_DIR, f"converted_{uuid.uuid4().hex}.m4a")
        convert_command = [
            "ffmpeg", "-y", "-i", trimmed_audio, "-acodec", "aac", "-b:a", "192k", converted_audio
        ]
        process_convert = await asyncio.create_subprocess_exec(*convert_command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await process_convert.communicate()
        if process_convert.returncode != 0:
            print("⚠️ Error converting audio, using original.")
            converted_audio = trimmed_audio

        merge_command = [
            "ffmpeg", "-y", "-threads", "4", "-i", video_no_audio, "-i", converted_audio,
            "-c:v", "copy", "-c:a", "aac", "-shortest", final_video
        ]
        process_merge = await asyncio.create_subprocess_exec(*merge_command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await process_merge.communicate()

        if process_merge.returncode == 0:
            print(f"🎬 ✅ Dubbed video created: {final_video}")
            # Cleanup temp files
            os.remove(trimmed_audio) if os.path.exists(trimmed_audio) else None
            os.remove(converted_audio) if os.path.exists(converted_audio) else None
            return final_video
        else:
            raise RuntimeError(f"⚠️ Error merging audio with video: {stderr.decode().strip()}")

    except Exception as e:
        print(f"⚠️ Exception in merge_audio_with_video: {e}")
        raise
