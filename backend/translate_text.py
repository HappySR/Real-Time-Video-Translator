import requests

def translate_text(text, target_lang):
    if not text:
        raise ValueError("The input text is empty, cannot translate.")

    response = requests.post(
        "https://libretranslate.com/translate",
        data={"q": text, "source": "en", "target": target_lang},
    )

    if response.status_code != 200:
        raise Exception(f"Translation failed with status code {response.status_code}: {response.text}")

    return response.json()["translatedText"]
