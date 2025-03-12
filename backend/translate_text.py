import httpx
import asyncio
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LIBRETRANSLATE_URL = os.getenv("LIBRETRANSLATE_URL", "http://127.0.0.1:5000/translate")
MAX_TEXT_LENGTH = 500  # Prevents large requests from failing
RETRY_ATTEMPTS = 3     # Number of retries
TIMEOUT = 15.0         # Request timeout (seconds)

async def translate_text(text, target_lang, source_lang="auto"):
    """
    Translates text using LibreTranslate.

    - Supports single string, list of strings, or nested lists.
    - Automatically chunks large text.
    - Implements retry logic.
    - Maintains input structure in output.
    """
    if not text:
        raise ValueError("❌ Input text is empty.")

    # Normalize input: Convert all text into a flattened list while keeping track of structure
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
                sub_structure = len(flat_list)
                flat_list.append(sub_data)
                structure.append(sub_structure)
            return sub_structure

        recurse(data)
        return flat_list, structure

    # Restore original structure
    def restore_structure(flat_translations, structure):
        def recurse(struct):
            if isinstance(struct, list):
                return [recurse(sub_struct) for sub_struct in struct]
            return flat_translations[struct]

        return recurse(structure)

    # Flatten input text while preserving structure
    text_list, structure = flatten_text(text)

    # Split long texts into smaller chunks
    chunked_texts = []
    for chunk in text_list:
        if len(chunk) > MAX_TEXT_LENGTH:
            chunked_texts.extend([chunk[i:i+MAX_TEXT_LENGTH] for i in range(0, len(chunk), MAX_TEXT_LENGTH)])
        else:
            chunked_texts.append(chunk)

    translated_chunks = []

    # Perform translation with retries
    for attempt in range(RETRY_ATTEMPTS):
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            try:
                response = await client.post(
                    LIBRETRANSLATE_URL,
                    json={"q": chunked_texts, "source": source_lang, "target": target_lang}
                )
                response.raise_for_status()
                response_data = response.json()

                # Ensure we always get a list of translations
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

            if attempt == RETRY_ATTEMPTS - 1:
                raise Exception("🚨 Translation failed after multiple retries.")

    # Restore the original structure
    reconstructed_translations = restore_structure(translated_chunks, structure)

    return {
        "translated_text": reconstructed_translations,
        "target_lang": target_lang,
        "source_lang": source_lang,
    }
