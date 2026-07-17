"""Text -> narration.mp3 + captions.srt using edge-tts (free, no API key).

edge-tts normally streams audio plus word-boundary timing events, which we
use to build a tightly-synced .srt caption file. Some edge-tts versions /
voices don't reliably emit those timing events though, which used to leave
us with a completely empty .srt file -- and ffmpeg's subtitles filter can't
open an empty subtitle file at all (hard failure, not just "no captions").
So if no word timings come back, we fall back to splitting the script text
into even chunks spread proportionally across the narration's actual
length (measured with ffprobe once the audio is written). Slightly less
perfectly synced than word-level timing, but always produces a valid file.
"""
import asyncio
import subprocess

import edge_tts

MAX_CHARS_PER_CUE = 42  # roughly one short caption line


def _ticks_to_srt_time(ticks: int) -> str:
    """edge-tts reports offsets in 100-nanosecond ticks; convert to SRT HH:MM:SS,mmm."""
    total_ms = ticks // 10_000
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"


def _seconds_to_srt_time(seconds: float) -> str:
    return _ticks_to_srt_time(int(seconds * 10_000_000))


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


def _ffprobe_duration_seconds(path: str) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]
    )
    return float(out.strip())


def _fallback_cues_from_text(text: str, duration_seconds: float):
    """Even-split fallback used when edge-tts gave us no word-boundary timing at all.

    Returns a list of (start_seconds, end_seconds, line_text) tuples spanning the
    whole narration, weighted by each chunk's character length.
    """
    words = text.split()
    chunks, current, current_len = [], [], 0
    for w in words:
        if current and current_len + len(w) + 1 > MAX_CHARS_PER_CUE:
            chunks.append(" ".join(current))
            current, current_len = [], 0
        current.append(w)
        current_len += len(w) + 1
    if current:
        chunks.append(" ".join(current))
    if not chunks:
        return [(0.0, duration_seconds, text)] if text else []

    total_chars = sum(len(c) for c in chunks) or 1
    cues, t = [], 0.0
    for c in chunks:
        dur = duration_seconds * (len(c) / total_chars)
        cues.append((t, t + dur, c))
        t += dur
    return cues


async def _synthesize(text: str, voice: str, mp3_path: str, srt_path: str):
    # edge-tts defaults to sentence-level ("SentenceBoundary") timing metadata, which is why
    # word_events kept coming back empty and triggering the even-split fallback below --
    # explicitly asking for word-level boundaries gives us real per-word sync instead.
    communicate = edge_tts.Communicate(text, voice, boundary="WordBoundary")
    word_events = []

    with open(mp3_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                audio_file.write(chunk["data"])
            elif chunk.get("type") == "WordBoundary" and "text" in chunk:
                word_events.append(
                    {
                        "text": chunk["text"],
                        "offset": chunk["offset"],
                        "duration": chunk["duration"],
                    }
                )

    cues = _group_words_into_cues(word_events)

    if cues:
        with open(srt_path, "w", encoding="utf-8") as srt_file:
            for i, cue in enumerate(cues, start=1):
                start = cue[0]["offset"]
                end = cue[-1]["offset"] + cue[-1]["duration"]
                line = " ".join(w["text"] for w in cue)
                srt_file.write(f"{i}\n")
                srt_file.write(f"{_ticks_to_srt_time(start)} --> {_ticks_to_srt_time(end)}\n")
                srt_file.write(f"{line}\n\n")
        last = word_events[-1]
        return (last["offset"] + last["duration"]) / 10_000_000

    # Fallback: no word-boundary timing came back from edge-tts at all.
    duration = _ffprobe_duration_seconds(mp3_path)
    fallback_cues = _fallback_cues_from_text(text, duration)
    with open(srt_path, "w", encoding="utf-8") as srt_file:
        for i, (start, end, line) in enumerate(fallback_cues, start=1):
            srt_file.write(f"{i}\n")
            srt_file.write(f"{_seconds_to_srt_time(start)} --> {_seconds_to_srt_time(end)}\n")
            srt_file.write(f"{line}\n\n")
    return duration


def synthesize(text: str, voice: str, mp3_path: str, srt_path: str) -> float:
    """Synchronous wrapper. Returns approximate narration duration in seconds."""
    return asyncio.run(_synthesize(text, voice, mp3_path, srt_path))
