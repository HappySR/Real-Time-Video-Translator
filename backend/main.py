from fastapi import FastAPI, UploadFile, File, HTTPException, Query
import os
import shutil
import asyncio
import ffmpeg
from extract_audio import extract_audio
from transcribe_audio import transcribe_audio
from translate_text import translate_text
from generate_subtitles import generate_srt
from text_to_speech import text_to_speech
from merge_audio_with_video import adjust_audio_duration, merge_audio_with_video, merge_audio_segments

app = FastAPI()

TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)  # Ensure temp directory exists

@app.get("/")
async def index():
    return {"message": "FastAPI app is running!"}

@app.post("/process_video")
async def process_video(
    video: UploadFile = File(...), 
    target_language: str = Query("hi", description="Target language for translation and TTS")
):
    # Initialize file paths
    video_path = None
    audio_path = None
    srt_path_en = None
    srt_path_translated = None
    tts_translated_paths = []  # Store each segment's TTS file
    merged_tts_path = None
    adjusted_tts_path = None
    final_video_no_audio = None
    final_dubbed_video = None

    try:
        # Validate file type
        allowed_extensions = (".mp4", ".mkv", ".avi")
        if not video.filename.lower().endswith(allowed_extensions):
            raise HTTPException(status_code=400, detail="Invalid file format. Only MP4, MKV, and AVI videos are supported.")

        # Save uploaded video
        video_path = os.path.join(TEMP_DIR, video.filename)
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(video.file, buffer)

        # Extract audio
        audio_path = video_path.rsplit(".", 1)[0] + ".mp3"
        if not await extract_audio(video_path, audio_path):
            raise HTTPException(status_code=500, detail="Failed to extract audio from video.")

        # Transcribe audio
        transcript, segments = await transcribe_audio(audio_path)
        if not transcript or not segments:
            raise HTTPException(status_code=500, detail="Failed to transcribe audio.")

        # Generate English subtitles
        srt_path_en = video_path.rsplit(".", 1)[0] + "_en.srt"
        await generate_srt(segments, srt_path_en)

        # Translate each subtitle segment
        translated_segments = []
        for segment in segments:
            translated_text_response = await translate_text(segment["text"], target_language)

            # Extract translated text from response
            if isinstance(translated_text_response, dict):
                translated_text_response = translated_text_response.get("translated_text", "")

            if isinstance(translated_text_response, list):
                while isinstance(translated_text_response, list) and translated_text_response:
                    translated_text_response = translated_text_response[0]

            if not isinstance(translated_text_response, str):
                raise ValueError(f"❌ Translation error: Expected string but got {type(translated_text_response)}")

            translated_segments.append({
                "start": segment["start"],
                "end": segment["end"],
                "text": translated_text_response.strip()
            })

        # Generate Translated SRT
        srt_path_translated = video_path.rsplit(".", 1)[0] + f"_{target_language}.srt"
        await generate_srt(translated_segments, srt_path_translated)

        # Convert each subtitle line to speech
        segment_tts_paths = []
        for i, segment in enumerate(translated_segments):
            segment_path = video_path.rsplit(".", 1)[0] + f"_{target_language}_seg_{i}.mp3"
            await text_to_speech(segment["text"], segment_path, target_language)
            segment_tts_paths.append((segment_path, segment["start"], segment["end"]))

        # Merge TTS segments into a single audio file
        merged_tts_path = video_path.rsplit(".", 1)[0] + f"_{target_language}_merged.mp3"
        await merge_audio_segments(segment_tts_paths, merged_tts_path)

        # Adjust translated TTS duration to match the original
        adjusted_tts_path = video_path.rsplit(".", 1)[0] + f"_{target_language}_adjusted.mp3"
        await adjust_audio_duration(audio_path, merged_tts_path, adjusted_tts_path)

        # Remove original audio
        final_video_no_audio = video_path.rsplit(".", 1)[0] + "_no_audio.mp4"
        ffmpeg.input(video_path).output(final_video_no_audio, an=None).run(overwrite_output=True)

        # Merge adjusted TTS audio with the video
        final_dubbed_video = video_path.rsplit(".", 1)[0] + f"_{target_language}_dubbed.mp4"
        await merge_audio_with_video(final_video_no_audio, adjusted_tts_path, final_dubbed_video)

        return {
            "message": "Processing completed successfully",
            "files": {
                "subtitles": {
                    "english": srt_path_en, 
                    target_language: srt_path_translated
                },
                "audio": {
                    "original": audio_path, 
                    "merged_tts": merged_tts_path, 
                    "adjusted_tts": adjusted_tts_path
                },
                "videos": {
                    "without_audio": final_video_no_audio,
                    "dubbed": final_dubbed_video
                }
            }
        }

    except HTTPException as e:
        raise e  # Preserve HTTP exceptions

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server Error: {str(e)}")

    finally:
        # Cleanup only if files exist
        def safe_remove(file):
            if file and os.path.exists(file):
                os.remove(file)

        cleanup_files = [
            video_path, audio_path, srt_path_en, srt_path_translated,
            merged_tts_path, adjusted_tts_path, final_video_no_audio
        ] + [seg[0] for seg in segment_tts_paths]  # Remove individual TTS segments

        for file in cleanup_files:
            safe_remove(file)

