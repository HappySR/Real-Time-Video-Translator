def generate_srt(transcript, segments, output_path):
    try:
        if not segments:
            raise ValueError("No segments found for subtitle generation.")

        with open(output_path, "w") as srt_file:
            for idx, segment in enumerate(segments):
                start = format_time(segment["start"])
                end = format_time(segment["end"])
                srt_file.write(f"{idx + 1}\n{start} --> {end}\n{segment['text']}\n\n")

        print(f"Subtitles generated successfully: {output_path}")

    except ValueError as e:
        print(f"Error: {e}")
        raise

    except Exception as e:
        print(f"Error generating subtitles: {e}")
        raise Exception("Subtitle generation failed.")

def format_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"
