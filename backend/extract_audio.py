import ffmpeg
import os

def extract_audio(video_path, output_audio_path):
    try:
        output_dir = os.path.dirname(output_audio_path)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        ffmpeg.input(video_path).output(output_audio_path, acodec="mp3").run()
        print(f"Audio extracted successfully: {output_audio_path}")
    except ffmpeg.Error as e:
        print(f"Error extracting audio from {video_path}: {e}")
        raise Exception(f"Audio extraction failed for {video_path}")
