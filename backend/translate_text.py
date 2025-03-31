import httpx
import asyncio
import os
import logging
import re

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LIBRETRANSLATE_URL = os.getenv("LIBRETRANSLATE_URL", "http://127.0.0.1:5000/translate")
MAX_TEXT_LENGTH = 500
RETRY_ATTEMPTS = 3
TIMEOUT = 15.0

def clean_text(text):
    """Clean text while preserving essential characters and content"""
    # Allow Hindi, Latin letters, numbers, and basic punctuation
    allowed_chars = r"[\u0900-\u097F\w\s.,!?।0-9]"
    cleaned = re.sub(fr"[^{allowed_chars}]", '', str(text))
    
    # Normalize spaces and remove leading/trailing spaces
    cleaned = ' '.join(cleaned.split())
    
    # Preserve original if cleaning removes all meaningful content
    if len(cleaned.strip()) < 1:
        return text.strip()
    return cleaned

async def translate_text(text, target_lang, source_lang="auto"):
    """
    Translates text using LibreTranslate with careful content preservation.
    """
    if not text:
        raise ValueError("❌ Input text is empty.")

    def flatten_text(data):
        structure = []
        flat_list = []
        
        def recurse(sub_data):
            if isinstance(sub_data, list):
                sub_structure = []
                for item in sub_data:
                    sub_structure.append(recurse(item))
                structure.append(sub_structure)
            else:
                original = str(sub_data)
                cleaned = clean_text(original)
                # Preserve original if cleaning removes too much
                final_text = cleaned if len(cleaned) > len(original)*0.5 else original
                sub_structure = len(flat_list)
                flat_list.append(final_text)
                structure.append(sub_structure)
            return sub_structure

        recurse(data)
        return flat_list, structure

    def restore_structure(flat_translations, structure):
        def recurse(struct):
            if isinstance(struct, list):
                return [recurse(sub_struct) for sub_struct in struct]
            return flat_translations[struct]
        return recurse(structure)

    text_list, structure = flatten_text(text)

    # Split long texts into smaller chunks
    chunked_texts = []
    for chunk in text_list:
        if len(chunk) > MAX_TEXT_LENGTH:
            chunked_texts.extend([chunk[i:i+MAX_TEXT_LENGTH] for i in range(0, len(chunk), MAX_TEXT_LENGTH)])
        else:
            chunked_texts.append(chunk)

    translated_chunks = []

    for attempt in range(RETRY_ATTEMPTS):
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
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

                break

            except httpx.HTTPStatusError as http_err:
                logger.warning(f"🚨 HTTP error (attempt {attempt+1}): {http_err.response.status_code} - {http_err.response.text}")
            except httpx.RequestError as req_err:
                logger.warning(f"🚨 Network error (attempt {attempt+1}): {req_err}")
            except Exception as e:
                logger.error(f"🚨 Unexpected error: {e}")

            if attempt == RETRY_ATTEMPTS - 1:
                raise Exception("🚨 Translation failed after multiple retries.")

    reconstructed_translations = restore_structure(translated_chunks, structure)

    return {
        "translated_text": reconstructed_translations,
        "target_lang": target_lang,
        "source_lang": source_lang,
    }