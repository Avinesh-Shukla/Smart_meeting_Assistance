import argparse
import os
from typing import Iterable

from faster_whisper import WhisperModel


def chunk_text(text: str, chunk_size: int = 900) -> Iterable[str]:
    words = text.split()
    current = []
    current_len = 0

    for word in words:
        current.append(word)
        current_len += len(word) + 1
        if current_len >= chunk_size:
            yield " ".join(current)
            current = []
            current_len = 0

    if current:
        yield " ".join(current)


def transcribe_audio(audio_file: str, model_name: str = "base") -> str:
    if not os.path.exists(audio_file):
        raise FileNotFoundError(audio_file)

    model = WhisperModel(model_name, device="auto", compute_type="int8")
    segments, _ = model.transcribe(audio_file)
    return " ".join(segment.text.strip() for segment in segments if segment.text).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcribe meeting audio with Whisper.")
    parser.add_argument("audio_file", help="Path to the audio file")
    parser.add_argument("--model", default="base", help="Whisper model size")
    parser.add_argument("--chunks", action="store_true", help="Print transcript in chunks")
    args = parser.parse_args()

    transcript = transcribe_audio(args.audio_file, args.model)

    if args.chunks:
        for part in chunk_text(transcript):
            print(part)
    else:
        print(transcript)


if __name__ == "__main__":
    main()
