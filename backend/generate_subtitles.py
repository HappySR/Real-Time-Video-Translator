import asyncio
import os
import httpx
import logging
import re
from typing import List, Dict

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LIBRETRANSLATE_URL = os.getenv("LIBRETRANSLATE_URL", "http://127.0.0.1:5000/translate")
MAX_TEXT_LENGTH = 500  # LibreTranslate API limit
MAX_PHRASE_GAP = 1.0  # Maximum gap between words to merge into same subtitle

async def generate_srt(segments: List[Dict], output_path: str, target_lang: str = None, source_lang: str = "auto") -> str:
    """
    Generates an SRT file with proper sentence segmentation and accurate timing.
    
    Args:
        segments: List of segments with start/end times and text
        output_path: Path to save the SRT file
        target_lang: Optional target language for translation
        source_lang: Source language (default: "auto")
        
    Returns:
        Path to generated SRT file
    """
    try:
        if not segments:
            raise ValueError("❌ No segments found for subtitle generation")

        # Translate if needed
        if target_lang:
            texts = [seg["text"] for seg in segments]
            translated = await translate_subtitles(texts, target_lang, source_lang)
            for i, seg in enumerate(segments):
                seg["text"] = translated[i]

        # Split into proper sentences with timing
        sentence_segments = []
        for segment in segments:
            sentence_segments.extend(
                _split_into_sentences(
                    segment["text"],
                    segment["start"],
                    segment["end"]
                )
            )

        # Merge short consecutive segments
        merged_segments = _merge_short_segments(sentence_segments)

        # Write to SRT file
        await asyncio.to_thread(_write_srt_file, merged_segments, output_path)
        logger.info(f"✅ Subtitles generated successfully: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"❌ Error generating subtitles: {e}")
        raise

def _split_into_sentences(text: str, start_time: float, end_time: float) -> List[Dict]:
    """
    Split text into sentences with smart timing using speech rate calculation.
    Maintains original segment duration while creating natural pauses.
    """
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    if not sentences:
        return []
    
    # Calculate speech rate (characters per second) for timing distribution
    total_chars = sum(len(s) for s in sentences)
    total_duration = end_time - start_time
    speech_rate = total_chars / total_duration if total_duration > 0 else 15  # Fallback to 15 cps
    
    sentence_segments = []
    current_start = start_time
    
    for sentence in sentences:
        if not sentence:
            continue
            
        # Calculate duration based on actual speech rate
        sentence_duration = len(sentence) / speech_rate
        
        # Add natural pause after punctuation
        pause_duration = 0.4 if sentence.endswith(('.', '!', '?')) else 0.2
        
        current_end = current_start + sentence_duration + pause_duration
        
        # Ensure we don't exceed original segment duration
        if current_end > end_time:
            current_end = end_time
            
        sentence_segments.append({
            "text": sentence,
            "start": current_start,
            "end": current_end
        })
        
        # Next sentence starts after pause
        current_start = current_end + 0.1  # Small buffer
    
    # Adjust last sentence to match original end time
    if sentence_segments:
        sentence_segments[-1]["end"] = end_time
    
    return sentence_segments

def _merge_short_segments(segments: List[Dict]) -> List[Dict]:
    """
    Merge very short consecutive segments for better readability.
    
    Args:
        segments: List of sentence segments
        
    Returns:
        List of merged segments
    """
    if not segments:
        return []
        
    merged = []
    current_segment = segments[0].copy()
    
    for segment in segments[1:]:
        # Merge if gap is small and combined text isn't too long
        if (segment["start"] - current_segment["end"] <= MAX_PHRASE_GAP and 
            len(current_segment["text"]) + len(segment["text"]) < 80):
            current_segment["text"] += " " + segment["text"]
            current_segment["end"] = segment["end"]
        else:
            merged.append(current_segment)
            current_segment = segment.copy()
    
    merged.append(current_segment)
    return merged

def _write_srt_file(segments: List[Dict], output_path: str):
    """
    Write segments to SRT file with proper formatting.
    
    Args:
        segments: List of segments with text and timing
        output_path: Path to output file
    """
    with open(output_path, "w", encoding="utf-8") as f:
        for i, segment in enumerate(segments, 1):
            start = _format_time(segment["start"])
            end = _format_time(segment["end"])
            f.write(f"{i}\n{start} --> {end}\n{segment['text']}\n\n")

def _format_time(seconds: float) -> str:
    """
    Format seconds into SRT timestamp (HH:MM:SS,mmm).
    
    Args:
        seconds: Time in seconds
        
    Returns:
        Formatted timestamp string
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = seconds % 60
    milliseconds = int(seconds - int(seconds)) * 1000
    return f"{hours:02}:{minutes:02}:{int(seconds):02},{milliseconds:03}"

async def translate_subtitles(texts: List[str], target_lang: str, source_lang: str = "auto", retries: int = 3) -> List[str]:
    """
    Translate list of texts using LibreTranslate API.
    
    Args:
        texts: List of texts to translate
        target_lang: Target language code
        source_lang: Source language code (default: "auto")
        retries: Number of retry attempts
        
    Returns:
        List of translated texts
    """
    if not texts:
        return texts

    # Prepare chunks respecting API limits
    chunked_texts = []
    for text in texts:
        if len(text) > MAX_TEXT_LENGTH:
            chunked_texts.extend(text[i:i+MAX_TEXT_LENGTH] for i in range(0, len(text), MAX_TEXT_LENGTH))
        else:
            chunked_texts.append(text)

    translated_chunks = []

    for attempt in range(retries):
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(
                    LIBRETRANSLATE_URL,
                    json={
                        "q": chunked_texts,
                        "source": source_lang,
                        "target": target_lang
                    }
                )
                response.raise_for_status()
                response_data = response.json()

                # Handle different response formats
                if isinstance(response_data, list):
                    translated_chunks = [item.get("translatedText", "") for item in response_data]
                elif isinstance(response_data, dict):
                    if "translatedText" in response_data:
                        translated_chunks = [response_data["translatedText"]]
                    elif "error" in response_data:
                        raise ValueError(f"Translation error: {response_data['error']}")
                else:
                    raise ValueError(f"Unexpected API response format: {response_data}")

                break  # Success - exit retry loop

            except httpx.HTTPStatusError as http_err:
                logger.warning(f"HTTP error (attempt {attempt+1}/{retries}): {http_err}")
            except httpx.RequestError as req_err:
                logger.warning(f"Network error (attempt {attempt+1}/{retries}): {req_err}")
            except Exception as e:
                logger.error(f"Unexpected error (attempt {attempt+1}/{retries}): {e}")

            if attempt == retries - 1:
                raise Exception("🚨 Translation failed after multiple retries")

    # Reconstruct original text order
    translated_texts = []
    chunk_index = 0
    for original in texts:
        if len(original) <= MAX_TEXT_LENGTH:
            translated_texts.append(translated_chunks[chunk_index])
            chunk_index += 1
        else:
            # Recombine chunks
            parts = []
            remaining_length = len(original)
            while remaining_length > 0:
                parts.append(translated_chunks[chunk_index])
                chunk_index += 1
                remaining_length -= MAX_TEXT_LENGTH
            translated_texts.append(" ".join(parts))

    return translated_texts