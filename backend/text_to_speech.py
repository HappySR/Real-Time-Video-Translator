import requests

def text_to_speech(text, output_audio_path):
    try:
        if not text:
            raise ValueError("The input text is empty.")

        # Use a TTS API (this is a placeholder; replace with actual API call)
        
        response = requests.post(
            "https://api.example.com/tts",
            json={"text": text},  # Adjust according to your TTS API's requirements.
            headers={"Authorization": "Bearer YOUR_API_KEY"}
        )

        if response.status_code == 200:
            with open(output_audio_path, 'wb') as f:
                f.write(response.content)
            print(f"TTS audio generated successfully: {output_audio_path}")
        
        else:
            raise Exception(f"TTS request failed with status code {response.status_code}: {response.text}")

    except Exception as e:
        print(f"Error generating TTS audio: {e}")
