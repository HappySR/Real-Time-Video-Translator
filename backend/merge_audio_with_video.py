import asyncio
import ffmpeg
import os
import uuid
import subprocess
import logging
import pysrt
from itertools import chain
import shutil

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEMP_DIR = os.path.abspath("temp")
os.makedirs(TEMP_DIR, exist_ok=True)

async def get_video_duration(video_path):
    """Get video duration in seconds"""
    try:
        probe = await asyncio.to_thread(ffmpeg.probe, video_path)
        return float(probe["format"]["duration"])
    except Exception as e:
        logger.error(f"Failed to get video duration: {str(e)}")
        raise

async def merge_audio_segments(audio_segments, srt_path, video_duration, output_audio):
    """Merge audio segments with proper timing from SRT file"""
    try:
        # Validate inputs
        if not audio_segments or not os.path.exists(srt_path):
            raise ValueError("Invalid audio segments or SRT path")

        subs = pysrt.open(srt_path)
        if len(audio_segments) != len(subs):
            raise ValueError("Audio segments and subtitles count mismatch")

        inputs = []
        temp_files = []
        filter_chains = []

        # Process each segment with proper timing
        for idx, (seg_path, sub) in enumerate(zip(audio_segments, subs)):
            seg_path = seg_path[0] if isinstance(seg_path, tuple) else seg_path
            if not os.path.exists(seg_path):
                logger.warning(f"Skipping missing segment {idx}: {seg_path}")
                continue

            # Calculate timing from SRT (in seconds)
            start = sub.start.ordinal / 1000
            end = sub.end.ordinal / 1000
            duration = end - start

            if duration <= 0:
                logger.warning(f"Skipping invalid duration {duration}s for segment {idx}")
                continue

            processed = os.path.join(TEMP_DIR, f"seg_{uuid.uuid4().hex}.wav")
            inputs.extend(["-i", seg_path])
            
            # Create filter chain for this segment
            filter_chains.append(
                f"[{len(inputs)//2 - 1}:a]atrim=0:{duration},"
                f"asetpts=N/SR/TB,"
                f"adelay={int(start*1000)}|{int(start*1000)},"
                f"apad=whole_dur={video_duration}[a{idx}]"
            )
            temp_files.append(processed)

        if not filter_chains:
            raise ValueError("No valid audio segments to merge")

        # Build final filtergraph
        mix_inputs = "".join([f"[a{i}]" for i in range(len(filter_chains))])
        filtergraph = ";".join(filter_chains) + f";{mix_inputs}amix=inputs={len(filter_chains)}:duration=longest[outa]"

        # Execute FFmpeg
        await run_command([
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filtergraph,
            "-map", "[outa]",
            "-c:a", "libmp3lame", "-b:a", "192k",
            output_audio
        ])

        return output_audio

    except Exception as e:
        logger.error(f"Audio merge failed: {str(e)}", exc_info=True)
        raise
    finally:
        cleanup(temp_files)

async def run_command(cmd):
    """Robust command executor with full diagnostics"""
    logger.debug(f"Executing: {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    
    if proc.returncode != 0:
        error_msg = stderr.decode().strip()
        logger.error(f"Command failed ({proc.returncode}): {error_msg}")
        raise RuntimeError(f"FFmpeg error: {error_msg}")
    
    return stdout

def cleanup(files):
    """Atomic file cleanup with existence checks"""
    for f in files:
        try:
            if os.path.exists(f):
                if os.path.isdir(f):
                    shutil.rmtree(f)
                else:
                    os.remove(f)
        except Exception as e:
            logger.warning(f"Cleanup error for {f}: {str(e)}")

async def adjust_audio_duration(segment_path, target_duration):
    """Adjust audio duration safely"""
    try:
        if not os.path.exists(segment_path):
            raise FileNotFoundError(f"Audio not found: {segment_path}")

        probe = await asyncio.to_thread(ffmpeg.probe, segment_path)
        current_duration = float(probe["format"]["duration"])
        
        if current_duration <= 0.01 or target_duration <= 0.01:
            raise ValueError(f"Invalid durations: {current_duration}s -> {target_duration}s")

        speed_factor = max(0.5, min(2.0, current_duration / target_duration))
        
        adjusted_path = os.path.join(TEMP_DIR, f"adj_{uuid.uuid4().hex}.mp3")
        await run_command([
            "ffmpeg", "-y", "-i", segment_path,
            "-af", f"atempo={speed_factor:.3f}",
            "-c:a", "libmp3lame", "-b:a", "192k",
            adjusted_path
        ])
        
        return adjusted_path

    except Exception as e:
        logger.error(f"Duration adjustment failed: {str(e)}", exc_info=True)
        raise

async def merge_audio_with_video(video_no_audio, merged_audio_path, final_video):
    """Merge audio and video with sync protection"""
    try:
        if not all(os.path.exists(f) for f in [video_no_audio, merged_audio_path]):
            raise FileNotFoundError("Missing input files")

        await run_command([
            "ffmpeg", "-y",
            "-i", video_no_audio,
            "-i", merged_audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            "-shortest",
            final_video
        ])

        logger.info(f"✅ Final video created: {final_video}")
        return final_video

    except Exception as e:
        logger.error(f"Video merge failed: {str(e)}", exc_info=True)
        raise

async def process_video(video_path, audio_segments, srt_path, output_video):
    """Complete processing pipeline example"""
    try:
        # Get video duration
        duration = await get_video_duration(video_path)
        
        # Process audio
        merged_audio = os.path.join(TEMP_DIR, "merged_audio.mp3")
        await merge_audio_segments(
            audio_segments=audio_segments,
            srt_path=srt_path,
            video_duration=duration,
            output_audio=merged_audio
        )
        
        # Merge with video
        await merge_audio_with_video(
            video_no_audio=video_path,
            merged_audio_path=merged_audio,
            final_video=output_video
        )
        
        return output_video
    except Exception as e:
        logger.error(f"Video processing failed: {str(e)}")
        raise