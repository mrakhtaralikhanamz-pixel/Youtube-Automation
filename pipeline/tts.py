"""Text -> narration.mp3 + captions.srt using edge-tts (free, no API key).

edge-tts streams audio plus word-boundary timing events, which we use to
build an .srt caption file that stays in sync with the generated voice.
"""
import asyncio
import edge_tts

MAX_CHARS_PER_CUE = 42  # roughly one short caption line


def _ticks_to_srt_time(ticks: int) -> str:
    """edge-tts reports offsets in 100-nanosecond ticks; convert to SRT HH:MM:SS,mmm."""
    total_ms = ticks // 10_000
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"


def _group_words_into_cues(word_events):
    """Group individual word timings into short multi-word caption cues."""
    cues, current, current_len = [], [], 0
    for w in word_events:
        text = w["text"]
        if current and current_len + len(text) + 1 > MAX_CHARS_PER_CUE:
            cues.append(current)
            current, current_len = [], 0
        current.append(w)
        current_len += len(text) + 1
    if current:
        cues.append(current)
    return cues


async def _synthesize(text: str, voice: str, mp3_path: str, srt_path: str):
    communicate = edge_tts.Communicate(text, voice)
    word_events = []

    with open(mp3_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                word_events.append(
                    {
                        "text": chunk["text"],
                        "offset": chunk["offset"],
                        "duration": chunk["duration"],
                    }
                )

    cues = _group_words_into_cues(word_events)
    with open(srt_path, "w", encoding="utf-8") as srt_file:
        for i, cue in enumerate(cues, start=1):
            start = cue[0]["offset"]
            end = cue[-1]["offset"] + cue[-1]["duration"]
            line = " ".join(w["text"] for w in cue)
            srt_file.write(f"{i}\n")
            srt_file.write(f"{_ticks_to_srt_time(start)} --> {_ticks_to_srt_time(end)}\n")
            srt_file.write(f"{line}\n\n")

    # Total audio duration in seconds, from the last word boundary (approximate but close enough
    # for footage-length planning; ffprobe is used for the authoritative value in assemble.py).
    if word_events:
        last = word_events[-1]
        return (last["offset"] + last["duration"]) / 10_000_000
    return 0.0


def synthesize(text: str, voice: str, mp3_path: str, srt_path: str) -> float:
    """Synchronous wrapper. Returns approximate narration duration in seconds."""
    return asyncio.run(_synthesize(text, voice, mp3_path, srt_path))
