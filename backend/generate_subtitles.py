import asyncio
import os
import httpx
import logging
from typing import List, Dict

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LIBRETRANSLATE_URL = os.getenv("LIBRETRANSLATE_URL", "http://127.0.0.1:5000/translate")
MAX_TEXT_LENGTH = 500  # LibreTranslate API limit

async def generate_srt(segments: List[Dict], output_path: str, target_lang: str = None, source_lang: str = "auto") -> str:
    """
    Generates an SRT file while preserving original timing chunks.
    
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

        # Group segments into timing-preserved chunks
        merged_segments = _group_segments_by_timing(segments)

        # Write to SRT file
        await asyncio.to_thread(_write_srt_file, merged_segments, output_path)
        logger.info(f"✅ Subtitles generated successfully: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"❌ Error generating subtitles: {e}")
        raise

def _group_segments_by_timing(segments: List[Dict]) -> List[Dict]:
    """
    Groups segments into chunks based on original timing blocks.
    
    Args:
        segments: List of individual segments
        
    Returns:
        List of merged segments preserving original timing blocks
    """
    if not segments:
        return []
        
    # Group segments that share the same timing block
    chunks = []
    current_chunk = None
    
    for segment in segments:
        if not current_chunk:
            current_chunk = {
                "text": segment["text"],
                "start": segment["start"],
                "end": segment["end"]
            }
        else:
            # Merge if within the same timing block (same start/end)
            if segment["start"] == current_chunk["start"] and segment["end"] == current_chunk["end"]:
                current_chunk["text"] += " " + segment["text"]
            else:
                chunks.append(current_chunk)
                current_chunk = {
                    "text": segment["text"],
                    "start": segment["start"],
                    "end": segment["end"]
                }
    
    if current_chunk:
        chunks.append(current_chunk)
        
    return chunks

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
    milliseconds = int((seconds - int(seconds)) * 1000)
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