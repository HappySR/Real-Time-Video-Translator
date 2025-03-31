import asyncio
import ffmpeg
import os
import uuid
import subprocess
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEMP_DIR = os.path.abspath("temp")
os.makedirs(TEMP_DIR, exist_ok=True)

async def merge_audio_segments(audio_segments, output_audio):
    """Merges audio segments with proper path handling and format conversion"""
    try:
        # Validate input
        if not audio_segments:
            raise ValueError("No audio segments provided for merging")

        # Create temporary files list
        temp_files = []
        concat_list = os.path.join(TEMP_DIR, f"concat_{uuid.uuid4().hex}.txt")

        # Prepare all segments with consistent format
        with open(concat_list, "w") as f:
            for seg in audio_segments:
                # Handle both tuple and string paths
                seg_path = seg[0] if isinstance(seg, tuple) else seg
                seg_path = os.path.abspath(seg_path)

                if not os.path.exists(seg_path):
                    logger.warning(f"⚠️ Segment not found: {seg_path}")
                    continue

                # Convert to consistent MP3 format
                temp_file = os.path.join(TEMP_DIR, f"conv_{uuid.uuid4().hex}.mp3")
                temp_files.append(temp_file)

                convert_cmd = [
                    "ffmpeg", "-y", "-i", seg_path,
                    "-acodec", "libmp3lame", "-ar", "44100",
                    "-ac", "1", "-b:a", "192k", temp_file
                ]

                try:
                    process = await asyncio.create_subprocess_exec(
                        *convert_cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    stdout, stderr = await process.communicate()

                    if process.returncode != 0:
                        logger.error(f"⚠️ Conversion failed for {seg_path}: {stderr.decode()}")
                        continue

                    if os.path.exists(temp_file):
                        f.write(f"file '{temp_file}'\n")
                    else:
                        logger.error(f"⚠️ Converted file not created: {temp_file}")

                except Exception as e:
                    logger.error(f"⚠️ Error converting {seg_path}: {str(e)}")
                    continue

        # Check if we have any valid segments
        if os.path.getsize(concat_list) == 0:
            raise ValueError("No valid audio segments to merge")

        # Merge using concat protocol
        merge_cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_list, "-c", "copy", output_audio
        ]

        process = await asyncio.create_subprocess_exec(
            *merge_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise RuntimeError(f"Merge failed: {stderr.decode()}")

        logger.info(f"✅ Successfully merged audio to {output_audio}")
        return output_audio

    except Exception as e:
        logger.error(f"❌ Error in merge_audio_segments: {str(e)}")
        raise
    finally:
        # Cleanup temporary files
        for f in temp_files + [concat_list]:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception as e:
                logger.warning(f"⚠️ Cleanup error for {f}: {str(e)}")

async def adjust_audio_duration(segment_path, target_duration):
    """Adjusts audio segment duration precisely using ffmpeg filters"""
    try:
        if not os.path.exists(segment_path):
            raise FileNotFoundError(f"Audio segment not found: {segment_path}")

        # Get current duration
        probe = await asyncio.to_thread(ffmpeg.probe, segment_path)
        current_duration = float(probe["format"]["duration"])

        if current_duration <= 0:
            raise ValueError(f"Invalid duration: {current_duration}")

        # Calculate speed factor with limits
        speed_factor = current_duration / target_duration
        speed_factor = max(0.5, min(2.0, speed_factor))  # Keep within reasonable bounds

        # Build atempo filter chain
        atempo_filters = []
        while speed_factor > 2.0:
            atempo_filters.append("atempo=2.0")
            speed_factor /= 2.0
        while speed_factor < 0.5:
            atempo_filters.append("atempo=0.5")
            speed_factor *= 2.0
        atempo_filters.append(f"atempo={speed_factor:.3f}")

        adjusted_path = os.path.join(TEMP_DIR, f"adjusted_{uuid.uuid4().hex}.mp3")
        
        cmd = [
            "ffmpeg", "-y", "-i", segment_path,
            "-filter:a", ",".join(atempo_filters),
            "-c:a", "libmp3lame", "-b:a", "192k",
            adjusted_path
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise RuntimeError(f"Adjustment failed: {stderr.decode()}")

        return adjusted_path

    except Exception as e:
        logger.error(f"❌ Error adjusting audio duration: {str(e)}")
        raise

async def merge_audio_with_video(video_no_audio, merged_audio_path, final_video):
    """Merges audio with video while maintaining sync"""
    try:
        if not os.path.exists(video_no_audio):
            raise FileNotFoundError(f"Video file not found: {video_no_audio}")
        if not os.path.exists(merged_audio_path):
            raise FileNotFoundError(f"Audio file not found: {merged_audio_path}")

        cmd = [
            "ffmpeg", "-y",
            "-i", video_no_audio,
            "-i", merged_audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            final_video
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise RuntimeError(f"Final merge failed: {stderr.decode()}")

        logger.info(f"✅ Successfully created final video: {final_video}")
        return final_video

    except Exception as e:
        logger.error(f"❌ Error in merge_audio_with_video: {str(e)}")
        raise