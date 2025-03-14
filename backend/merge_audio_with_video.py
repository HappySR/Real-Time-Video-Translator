import asyncio
import ffmpeg
import os
import uuid

TEMP_DIR = "temp/"
os.makedirs(TEMP_DIR, exist_ok=True)  # Ensure temp directory exists

async def merge_audio_segments(audio_segments, output_audio):
    """Merges multiple audio segments into a single MP3 file while ensuring format consistency."""
    try:
        if not audio_segments:
            raise ValueError("No audio segments provided for merging.")

        concat_list_path = os.path.join(TEMP_DIR, "concat_list.txt")
        converted_segments = []  # Store paths of converted MP3 files

        print("🔍 Debugging Audio Segments Paths:")
        for segment in audio_segments:
            if isinstance(segment, tuple):
                segment = segment[0]  # Extract only the file path from tuple

            segment_path = os.path.normpath(segment)  # Normalize path
            if not os.path.isabs(segment_path):  
                segment_path = os.path.join(TEMP_DIR, os.path.basename(segment))  # Ensure correct path

            if not os.path.exists(segment_path):
                raise FileNotFoundError(f"⚠️ Audio segment not found: {segment_path}")

            # Convert all audio files to standardized MP3 format
            converted_segment = os.path.join(TEMP_DIR, f"converted_{uuid.uuid4().hex}.mp3")
            convert_command = [
                "ffmpeg", "-y", "-i", segment_path, "-acodec", "libmp3lame", "-ar", "24000", "-b:a", "128k", converted_segment
            ]
            process_convert = await asyncio.create_subprocess_exec(*convert_command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await process_convert.communicate()

            if process_convert.returncode != 0:
                raise RuntimeError(f"⚠️ Error converting audio: {segment_path}")

            converted_segments.append(converted_segment)

        # Write to concat_list.txt (ONLY file names, NO 'temp/' prefix)
        with open(concat_list_path, "w", encoding="utf-8") as f:
            for segment in converted_segments:
                f.write(f"file '{os.path.basename(segment)}'\n")  # ✅ FIXED

        # Merge audio using FFmpeg
        merge_command = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path,
            "-c", "copy", output_audio
        ]
        process_merge = await asyncio.create_subprocess_exec(*merge_command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await process_merge.communicate()

        if process_merge.returncode == 0:
            print(f"✅ Merged audio segments successfully: {output_audio}")
            os.remove(concat_list_path)  # Clean up temp file list

            # Remove temp converted files
            for file in converted_segments:
                os.remove(file) if os.path.exists(file) else None

            return output_audio
        else:
            print(f"⚠️ Error merging audio segments: {stderr.decode().strip()}")
            raise RuntimeError(stderr.decode().strip())

    except Exception as e:
        print(f"⚠️ Exception in merge_audio_segments: {e}")
        raise

async def adjust_audio_duration(segment_path, target_duration):
    """Adjusts a single audio segment's duration to match the target duration."""
    try:
        if not os.path.exists(segment_path):
            raise FileNotFoundError(f"⚠️ Audio segment not found: {segment_path}")

        # Get current duration
        segment_info = ffmpeg.probe(segment_path)
        segment_duration = float(segment_info["format"]["duration"])

        if segment_duration == 0:
            raise ValueError(f"⚠️ Audio segment has zero duration: {segment_path}")

        speed_factor = segment_duration / target_duration

        # Ensure proper `atempo` values
        atempo_filters = []
        while speed_factor > 2.0:
            atempo_filters.append("atempo=2.0")
            speed_factor /= 2.0
        while speed_factor < 0.5:
            atempo_filters.append("atempo=0.5")
            speed_factor *= 2.0
        atempo_filters.append(f"atempo={speed_factor}")

        adjusted_segment = os.path.join(TEMP_DIR, f"adjusted_{uuid.uuid4().hex}.mp3")
        command = ["ffmpeg", "-y", "-i", segment_path, "-filter:a", ",".join(atempo_filters), "-vn", adjusted_segment]

        process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            print(f"✅ Adjusted segment: {adjusted_segment}")
            return adjusted_segment
        else:
            raise RuntimeError(f"⚠️ Error adjusting segment: {stderr.decode().strip()}")

    except Exception as e:
        print(f"⚠️ Exception in adjust_audio_segment_duration: {e}")
        raise

async def merge_audio_with_video(video_no_audio, subtitle_data, audio_segments, final_video):
    """Processes and merges adjusted audio segments into the video at their correct timestamps."""
    try:
        adjusted_segments = []

        for (segment_path, start_time, end_time) in audio_segments:
            target_duration = end_time - start_time
            adjusted_segment = await adjust_audio_duration(segment_path, target_duration)
            adjusted_segments.append((adjusted_segment, start_time))

        # Generate silent base audio with the same length as the video
        video_info = ffmpeg.probe(video_no_audio)
        video_duration = float(video_info["format"]["duration"])
        silent_audio = os.path.join(TEMP_DIR, "silent_audio.mp3")
        await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-f", "lavfi", "-t", str(video_duration),
            "-i", "anullsrc=channel_layout=stereo:sample_rate=24000",
            "-q:a", "9", "-acodec", "libmp3lame", silent_audio
        )

        # Overlay adjusted audio segments onto the silent audio
        overlay_filter = "".join(
            f"[{i}:a]adelay={int(start_time * 1000)}|{int(start_time * 1000)}[a{i}];"
            for i, (_, start_time) in enumerate(adjusted_segments)
        )
        input_files = [silent_audio] + [seg[0] for seg in adjusted_segments]
        filter_complex = overlay_filter + "".join(f"[a{i}]" for i in range(len(adjusted_segments))) + "amix=inputs=" + str(len(adjusted_segments) + 1) + "[aout]"

        final_audio = os.path.join(TEMP_DIR, "final_audio.mp3")
        merge_command = [
            "ffmpeg", "-y",
            *sum([["-i", f] for f in input_files], []),  # Add input files dynamically
            "-filter_complex", filter_complex,
            "-map", "[aout]", "-acodec", "libmp3lame", "-q:a", "4", final_audio
        ]
        process_merge = await asyncio.create_subprocess_exec(*merge_command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await process_merge.communicate()

        if not os.path.exists(final_audio):
            raise RuntimeError("⚠️ Failed to merge adjusted audio segments!")

        # Merge final audio with the video
        merge_video_command = [
            "ffmpeg", "-y", "-i", video_no_audio, "-i", final_audio,
            "-c:v", "copy", "-c:a", "aac", "-strict", "experimental", "-map", "0:v:0", "-map", "1:a:0", final_video
        ]
        process_video_merge = await asyncio.create_subprocess_exec(*merge_video_command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await process_video_merge.communicate()

        if process_video_merge.returncode == 0:
            print(f"🎬 ✅ Final dubbed video created: {final_video}")
            return final_video
        else:
            raise RuntimeError("⚠️ Error merging adjusted audio with video.")

    except Exception as e:
        print(f"⚠️ Exception in merge_audio_with_video: {e}")
        raise