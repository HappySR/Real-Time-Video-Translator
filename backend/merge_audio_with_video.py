import asyncio
import ffmpeg
import os
import uuid
import subprocess

TEMP_DIR = "temp/"
os.makedirs(TEMP_DIR, exist_ok=True)  # Ensure temp directory exists

async def merge_audio_segments(audio_segments, output_audio):
    """Merges audio segments with proper path handling"""
    try:
        # Create absolute paths for all temporary files
        TEMP_DIR = os.path.abspath("temp")
        os.makedirs(TEMP_DIR, exist_ok=True)

        # Generate unique temporary list file with absolute path
        concat_list = os.path.join(TEMP_DIR, f"concat_{uuid.uuid4().hex}.txt")
        temp_files = []

        # Write valid segments with absolute paths
        with open(concat_list, "w") as f:
            for seg in audio_segments:
                if isinstance(seg, tuple):
                    seg_path = seg[0]
                else:
                    seg_path = seg
                
                # Normalize and verify path
                seg_path = os.path.abspath(os.path.normpath(seg_path))
                if not os.path.exists(seg_path):
                    continue

                # Create converted file with absolute path
                temp_file = os.path.join(TEMP_DIR, f"conv_{uuid.uuid4().hex}.mp3")
                temp_files.append(temp_file)

                # Convert to consistent format
                convert_cmd = [
                    "ffmpeg", "-y", "-i", seg_path,
                    "-acodec", "libmp3lame", "-ar", "44100",
                    "-ac", "1", "-b:a", "192k", temp_file
                ]
                process = await asyncio.create_subprocess_exec(*convert_cmd)
                await process.wait()
                
                # Verify conversion succeeded
                if os.path.exists(temp_file):
                    f.write(f"file '{temp_file}'\n")
                else:
                    print(f"⚠️ Failed to convert {seg_path}")

        # Merge using absolute paths
        command = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_list, "-c:a", "copy", output_audio
        ]
        
        process = await asyncio.create_subprocess_exec(*command)
        await process.wait()

        # Cleanup temporary files
        for f in temp_files + [concat_list]:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception as e:
                print(f"⚠️ Error cleaning up {f}: {e}")

        return output_audio

    except Exception as e:
        print(f"⚠️ Error merging audio: {e}")
        # Cleanup on error
        for f in temp_files + [concat_list]:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except:
                pass
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
        temp_files = []

        # 1. Adjust durations for all segments
        for segment_path, start_time, end_time in audio_segments:
            target_duration = end_time - start_time
            adjusted_segment = await adjust_audio_duration(segment_path, target_duration)
            adjusted_segments.append((adjusted_segment, start_time))
            temp_files.append(adjusted_segment)

        # 2. Generate silent audio base
        video_info = await asyncio.to_thread(ffmpeg.probe, video_no_audio)
        video_duration = float(video_info["format"]["duration"])
        silent_audio = os.path.join(TEMP_DIR, "silent_audio.wav")
        
        # Create silent audio with standardized format
        silent_process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-f", "lavfi", "-t", str(video_duration),
            "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2", silent_audio
        )
        await silent_process.wait()
        temp_files.append(silent_audio)

        # 3. Convert all segments to WAV with consistent format
        converted_segments = []
        for seg_path, start_time in adjusted_segments:
            wav_path = seg_path.replace(".mp3", ".wav")
            convert_cmd = [
                "ffmpeg", "-y", "-i", seg_path,
                "-ac", "1", "-ar", "44100",  # Force mono and consistent sample rate
                wav_path
            ]
            process = await asyncio.create_subprocess_exec(*convert_cmd)
            await process.wait()
            converted_segments.append((wav_path, start_time))
            temp_files.append(wav_path)

        # 4. Build filter graph
        if not converted_segments:
            # Just use silent audio
            filter_complex = "anullsrc=channel_layout=stereo:sample_rate=44100[aout]"
        else:
            filter_chains = []
            inputs = [silent_audio]
            for idx, (seg_path, start_time) in enumerate(converted_segments):
                filter_chains.append(
                    f"[{idx+1}:a]adelay={int(start_time*1000)}|{int(start_time*1000)}[a{idx}]"
                )
                inputs.append(seg_path)
            mix_inputs = "".join(f"[a{idx}]" for idx in range(len(converted_segments)))
            filter_complex = ";".join(filter_chains) + f";{mix_inputs}amix=inputs={len(converted_segments)}:duration=longest[aout]"

        # 5. Merge audio tracks
        merged_audio = os.path.join(TEMP_DIR, "final_audio.wav")
        merge_cmd = [
            "ffmpeg", "-y",
            "-i", silent_audio,
            *[arg for pair in [["-i", f] for f, _ in converted_segments] for arg in pair],
            "-filter_complex", filter_complex,
            "-map", "[aout]",
            "-ac", "2",  # Output stereo
            "-ar", "44100",
            "-acodec", "pcm_s16le",
            merged_audio
        ]
        merge_process = await asyncio.create_subprocess_exec(*merge_cmd)
        await merge_process.wait()
        temp_files.append(merged_audio)

        # 6. Merge with video
        merge_video_cmd = [
            "ffmpeg", "-y",
            "-i", video_no_audio,
            "-i", merged_audio,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-ac", "2",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            final_video
        ]
        video_process = await asyncio.create_subprocess_exec(*merge_video_cmd)
        await video_process.wait()

        # Cleanup temporary files
        for f in temp_files:
            if os.path.exists(f):
                os.remove(f)

        return final_video

    except Exception as e:
        print(f"Error in merge_audio_with_video: {str(e)}")
        # Cleanup on error
        for f in temp_files:
            if os.path.exists(f):
                os.remove(f)
        raise