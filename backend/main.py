from fastapi import FastAPI, UploadFile, File, HTTPException, Query
import os
import shutil
import asyncio
import ffmpeg
from text_to_speech import LANGUAGE_MAP
from extract_audio import extract_audio
from transcribe_audio import transcribe_audio
from translate_text import translate_text
from generate_subtitles import generate_srt
from text_to_speech import generate_tts_segments
from merge_audio_with_video import merge_audio_with_video, merge_audio_segments

app = FastAPI()

TEMP_DIR = os.path.abspath("temp")
os.makedirs(TEMP_DIR, exist_ok=True)

def _group_segments_into_chunks(segments: list) -> list:
    """
    Groups segments into timing-preserved chunks for TTS generation.
    
    Args:
        segments: List of transcribed segments
        
    Returns:
        List of chunks with combined text and original timing
    """
    chunks = []
    current_chunk = None
    
    for segment in segments:
        if not current_chunk:
            current_chunk = {
                "texts": [segment["text"]],
                "start": segment["start"],
                "end": segment["end"]
            }
        else:
            # Merge if within the same timing block (same start/end)
            if segment["start"] == current_chunk["start"] and segment["end"] == current_chunk["end"]:
                current_chunk["texts"].append(segment["text"])
            else:
                chunks.append(current_chunk)
                current_chunk = {
                    "texts": [segment["text"]],
                    "start": segment["start"],
                    "end": segment["end"]
                }
    
    if current_chunk:
        chunks.append(current_chunk)
        
    return chunks

@app.post("/process_video")
async def process_video(
    video: UploadFile = File(...), 
    target_language: str = Query("hi", description="Target language for translation and TTS")
):
    video_path = None
    audio_path = None
    srt_path_en = None
    srt_path_translated = None
    merged_tts_path = None
    final_video_no_audio = None
    final_dubbed_video = None

    SUPPORTED_LANGUAGES = list(LANGUAGE_MAP.keys())
    if target_language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported target language. Supported: {SUPPORTED_LANGUAGES}"
        )

    try:
        # Validate and save video
        allowed_extensions = (".mp4", ".mkv", ".avi")
        if not video.filename.lower().endswith(allowed_extensions):
            raise HTTPException(status_code=400, detail="Invalid file format. Supported formats: MP4, MKV, AVI")

        video_path = os.path.join(TEMP_DIR, video.filename)
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(video.file, buffer)

        # Extract audio
        audio_path = video_path.rsplit(".", 1)[0] + ".mp3"
        if not await extract_audio(video_path, audio_path):
            raise HTTPException(status_code=500, detail="Audio extraction failed")

        # Transcribe audio with word-level timestamps
        segments = await transcribe_audio(audio_path)
        if not segments:
            raise HTTPException(status_code=500, detail="Audio transcription failed")

        # Generate English subtitles (preserve original timing chunks)
        srt_path_en = video_path.rsplit(".", 1)[0] + "_en.srt"
        await generate_srt(segments, srt_path_en)

        # Translate segments while preserving timing chunks
        translated_chunks = []
        original_chunks = _group_segments_into_chunks(segments)
        
        for chunk in original_chunks:
            try:
                # Combine all text in the chunk for translation
                combined_text = " ".join(chunk["texts"])
                translation_result = await translate_text(combined_text, target_language)
                translated_text = translation_result["translated_text"]
                
                # Handle both string and list responses
                if isinstance(translated_text, list):
                    translated_text = " ".join([str(t) for t in translated_text])
                
                # Clean and validate
                translated_text = str(translated_text).replace("\n", " ").strip()[:500]

                translated_chunks.append({
                    "texts": [translated_text],
                    "start": chunk["start"],
                    "end": chunk["end"]
                })
            except Exception as e:
                print(f"⚠️ Translation error: {e}")
                translated_chunks.append(chunk)  # Fallback to original

        # Generate translated subtitles
        srt_path_translated = video_path.rsplit(".", 1)[0] + f"_{target_language}.srt"
        translated_segments = []
        for chunk in translated_chunks:
            translated_segments.append({
                "text": " ".join(chunk["texts"]),
                "start": chunk["start"],
                "end": chunk["end"]
            })
        await generate_srt(translated_segments, srt_path_translated)

        # Process TTS for complete chunks (preserving timing blocks)
        segment_tts_paths = await generate_tts_segments(
            translated_chunks,
            TEMP_DIR,
            target_language
        )

        # Merge audio segments
        if segment_tts_paths:
            merged_tts_path = video_path.rsplit(".", 1)[0] + f"_{target_language}_merged.mp3"
            await merge_audio_segments([seg[0] for seg in segment_tts_paths], merged_tts_path)

        # Create video without audio
        final_video_no_audio = video_path.rsplit(".", 1)[0] + "_no_audio.mp4"
        (
            ffmpeg.input(video_path)
            .output(final_video_no_audio, vcodec='copy', an=None)
            .run(overwrite_output=True, quiet=True)
        )

        # Merge TTS audio with video
        final_dubbed_video = video_path.rsplit(".", 1)[0] + f"_{target_language}_dubbed.mp4"
        if not await merge_audio_with_video(final_video_no_audio, merged_tts_path, final_dubbed_video):
            raise HTTPException(status_code=500, detail="Failed to merge audio with video")

        return {
            "message": "Processing completed successfully",
            "files": {
                "subtitles": {
                    "english": srt_path_en, 
                    target_language: srt_path_translated
                },
                "audio": {
                    "original": audio_path, 
                    "merged_tts": merged_tts_path
                },
                "videos": {
                    "without_audio": final_video_no_audio,
                    "dubbed": final_dubbed_video
                }
            }
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")
    finally:
        # Cleanup temporary files
        def safe_remove(path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    print(f"⚠️ Cleanup error: {e}")

        cleanup_files = [
            video_path, audio_path, srt_path_en, srt_path_translated,
            merged_tts_path, final_video_no_audio
        ] + [seg[0] for seg in (segment_tts_paths or []) if seg and seg[0]]

        for file in cleanup_files:
            safe_remove(file)