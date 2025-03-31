from fastapi import FastAPI, UploadFile, File, HTTPException, Query
import os
import shutil
import asyncio
import ffmpeg
import re
from text_to_speech import LANGUAGE_MAP
from extract_audio import extract_audio
from transcribe_audio import transcribe_audio
from translate_text import translate_text
from generate_subtitles import generate_srt
from text_to_speech import text_to_speech
from merge_audio_with_video import merge_audio_with_video, merge_audio_segments

app = FastAPI()

TEMP_DIR = os.path.abspath("temp")
os.makedirs(TEMP_DIR, exist_ok=True)

def split_sentences_with_timing(segments):
    """Split segments into sentences with accurate timing"""
    sentence_segments = []
    
    for segment in segments:
        text = segment["text"].strip()
        start = segment["start"]
        end = segment["end"]
        
        if not text:
            continue
            
        # Split into sentences while preserving timing
        sentences = re.split(r'(?<=[.!?])\s+', text)
        sentence_count = len(sentences)
        
        if sentence_count == 0:
            continue
        elif sentence_count == 1:
            # Single sentence, use original timing
            sentence_segments.append({
                "start": start,
                "end": end,
                "text": text
            })
        else:
            # Multiple sentences, distribute time proportionally
            total_duration = end - start
            words = text.split()
            word_count = len(words)
            
            if word_count == 0:
                continue
                
            # Calculate word durations
            word_durations = []
            current_word_start = start
            for i, word in enumerate(words):
                if i < len(words) - 1:
                    word_end = start + (i+1) * (total_duration / word_count)
                else:
                    word_end = end
                word_durations.append((current_word_start, word_end))
                current_word_start = word_end
            
            # Reconstruct sentences with proper timing
            current_sentence = []
            current_sentence_start = None
            word_index = 0
            
            for sentence in sentences:
                sentence_words = sentence.split()
                sentence_word_count = len(sentence_words)
                
                if sentence_word_count == 0:
                    continue
                    
                # Get timing for first word in sentence
                first_word_start = word_durations[word_index][0]
                if current_sentence_start is None:
                    current_sentence_start = first_word_start
                
                # Get timing for last word in sentence
                last_word_end = word_durations[word_index + sentence_word_count - 1][1]
                
                sentence_segments.append({
                    "start": first_word_start,
                    "end": last_word_end,
                    "text": sentence
                })
                
                word_index += sentence_word_count
    
    return sentence_segments

@app.post("/process_video")
async def process_video(
    video: UploadFile = File(...), 
    target_language: str = Query("hi", description="Target language for translation and TTS")
):
    video_path = None
    audio_path = None
    srt_path_en = None
    srt_path_translated = None
    segment_tts_paths = []
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

        # Split into proper sentences with accurate timing
        sentence_segments = split_sentences_with_timing(segments)

        # Generate English subtitles
        srt_path_en = video_path.rsplit(".", 1)[0] + "_en.srt"
        await generate_srt(sentence_segments, srt_path_en)

        # Translate segments
        translated_segments = []
        for segment in sentence_segments:
            try:
                translation_result = await translate_text(segment["text"], target_language)
                translated_text = translation_result["translated_text"]
                
                # Handle both string and list responses
                if isinstance(translated_text, list):
                    # If we get a list of translations, join them with spaces
                    translated_text = " ".join([str(t) for t in translated_text])
                
                # Clean and validate
                translated_text = str(translated_text).replace("\n", " ").strip()[:500]  # Ensure string and limit length

                translated_segments.append({
                    "start": segment["start"],
                    "end": segment["end"],
                    "text": translated_text
                })
            except Exception as e:
                print(f"⚠️ Translation error: {e}")
                translated_segments.append(segment)  # Fallback to original

        # Generate translated subtitles
        srt_path_translated = video_path.rsplit(".", 1)[0] + f"_{target_language}.srt"
        await generate_srt(translated_segments, srt_path_translated)

        # Process TTS for complete segments
        for idx, segment in enumerate(translated_segments):
            try:
                segment_path = os.path.join(
                    TEMP_DIR,
                    f"{os.path.basename(video_path).rsplit('.', 1)[0]}_{target_language}_seg_{idx}.mp3"
                )
                
                if not segment["text"].strip():
                    print(f"⚠️ Skipping empty segment {idx}")
                    continue
                
                if await text_to_speech(
                    text=segment["text"],
                    output_audio_path=segment_path,
                    target_language=target_language
                ):
                    segment_tts_paths.append((
                        segment_path,
                        segment["start"],
                        segment["end"]
                    ))

            except Exception as e:
                print(f"⚠️ TTS error for segment {idx}: {e}")
                continue

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
        ] + [seg[0] for seg in segment_tts_paths if seg and seg[0]]

        for file in cleanup_files:
            safe_remove(file)