# 🎥 Real-Time Video Translation

A fully automated pipeline for real-time translation and voice-over of videos. This project extracts the audio from a given video, transcribes it, translates it into the desired language, and regenerates audio using text-to-speech — all while maintaining accurate timing and seamless reintegration into the video.

## 🔧 Features

- 🎙️ Extracts audio from any video using **FFmpeg**
- 📝 Transcribes speech with **OpenAI Whisper**
- 🌍 Translates text using **LibreTranslate**
- 🔊 Converts translated text to speech with **Coqui TTS**
- 🕒 Syncs generated audio to original subtitle timings
- 📼 Merges the final audio with the original video
- 🧹 Automatically cleans up temporary files

---

## 🛠 Tech Stack

| Tool/Library     | Purpose                           |
|------------------|-----------------------------------|
| **FastAPI**       | Backend API framework              |
| **FFmpeg**        | Audio extraction & video merging  |
| **Whisper**       | Speech-to-text transcription      |
| **LibreTranslate**| Text translation                  |
| **Coqui TTS**     | Text-to-speech synthesis          |

---

## 📦 Installation

> ⚠️ Prerequisites:
> - Python 3.8+
> - FFmpeg installed and accessible in system PATH

### Step 1: Clone the repository

```bash
git clone https://github.com/HappySR/rtvat-og.git
cd backend
```

### Step 2: Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### Step 3: Install dependencies

```bash
pip install -r requirements.txt
```

---

## ▶️ Usage

Run the FastAPI app:

```bash
uvicorn main:app --reload
```

Access the API documentation at:  
**http://localhost:8000/docs**

Upload a video and specify the target language via the API.

---

## 🧼 Cleanup

All temporary files (audio clips, transcriptions, intermediate files) are automatically removed after final video generation to save storage space.

---

## 📄 License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**. Feel free to use, modify, and distribute it.  

📄 [Full License Text](https://www.gnu.org/licenses/agpl-3.0.txt)

---

## 🤝 Contributions

Contributions, suggestions, and issues are welcome! Feel free to fork the repo and submit a pull request.
