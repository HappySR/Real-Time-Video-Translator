import asyncio
import os
import httpx
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LIBRETRANSLATE_URL = os.getenv("LIBRETRANSLATE_URL", "http://127.0.0.1:5000/translate")
MAX_TEXT_LENGTH = 500  # LibreTranslate API limit

async def generate_srt(segments, output_path, target_lang=None, source_lang="auto"):
    """
    Generates an SRT file asynchronously from transcript segments.
    Supports translation if a target language is provided.

    Args:
        segments (list): List of subtitle segments.
        output_path (str): Output SRT file path.
        target_lang (str): Target language for translation (optional).
        source_lang (str): Source language (default: auto).
    """
    try:
        if not segments:
            raise ValueError("❌ No segments found for subtitle generation.")

        # Translate subtitles if a target language is provided
        if target_lang:
            translated_texts = await translate_subtitles([seg["text"] for seg in segments], target_lang, source_lang)
            for i, seg in enumerate(segments):
                seg["text"] = translated_texts[i]

        # Write the translated subtitles asynchronously
        await asyncio.to_thread(write_srt_file, segments, output_path)

        logger.info(f"✅ Subtitles generated successfully: {output_path}")
        return output_path

    except Exception as e:
        logger.error(f"❌ Error generating subtitles: {e}")
        raise

def write_srt_file(segments, output_path):
    """
    Writes subtitles to an SRT file.

    Args:
        segments (list): Subtitle segments.
        output_path (str): Output SRT file path.
    """
    try:
        with open(output_path, "w", encoding="utf-8") as srt_file:
            for idx, segment in enumerate(segments):
                if not segment.get("text") or "start" not in segment or "end" not in segment:
                    continue  # Skip invalid segments
                
                start = format_time(segment["start"])
                end = format_time(segment["end"])
                text = segment["text"].strip().replace("\n", " ")  # Clean formatting
                
                srt_file.write(f"{idx + 1}\n{start} --> {end}\n{text}\n\n")

    except Exception as e:
        logger.error(f"❌ Error writing SRT file: {e}")
        raise

async def translate_subtitles(texts, target_lang, source_lang="auto", retries=3):
    """
    Translates a list of subtitle texts using LibreTranslate.

    Args:
        texts (list): List of subtitle texts.
        target_lang (str): Target language.
        source_lang (str): Source language (default: auto).
        retries (int): Number of retry attempts.
    
    Returns:
        list: Translated subtitles in the same order.
    """
    if not texts:
        return texts

    chunked_texts = []
    for chunk in texts:
        if len(chunk) > MAX_TEXT_LENGTH:
            chunked_texts.extend([chunk[i:i+MAX_TEXT_LENGTH] for i in range(0, len(chunk), MAX_TEXT_LENGTH)])
        else:
            chunked_texts.append(chunk)

    translated_chunks = []

    for attempt in range(retries):
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(
                    LIBRETRANSLATE_URL,
                    json={"q": chunked_texts, "source": source_lang, "target": target_lang}
                )
                response.raise_for_status()
                response_data = response.json()

                if isinstance(response_data, list):
                    translated_chunks = [item.get("translatedText", "") for item in response_data]
                elif isinstance(response_data, dict) and "translatedText" in response_data:
                    translated_chunks = [response_data["translatedText"]]
                else:
                    raise ValueError(f"🚨 Unexpected API response: {response_data}")

                break  # Exit retry loop if successful

            except httpx.HTTPStatusError as http_err:
                logger.warning(f"🚨 HTTP error (attempt {attempt+1}): {http_err.response.status_code} - {http_err.response.text}")
            except httpx.RequestError as req_err:
                logger.warning(f"🚨 Network error (attempt {attempt+1}): {req_err}")
            except Exception as e:
                logger.error(f"🚨 Unexpected error: {e}")

            if attempt == retries - 1:
                raise Exception("🚨 Translation failed after multiple retries.")

    return translated_chunks

def format_time(seconds):
    """
    Formats time in HH:MM:SS,mmm format for SRT files.

    Args:
        seconds (float): Time in seconds.

    Returns:
        str: Formatted timestamp.
    """
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)  # Avoid rounding errors
    return f"{h:02}:{m:02}:{s:02},{ms:03}"
