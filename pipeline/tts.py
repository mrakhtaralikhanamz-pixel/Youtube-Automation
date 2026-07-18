"""Text -> narration.mp3 + captions.ass using edge-tts (free, no API key).

edge-tts normally streams audio plus word-boundary timing events, which we
use to build a tightly-synced .ass caption file. Some edge-tts versions /
voices don't reliably emit those timing events though, which used to leave
us with a completely empty caption file -- and ffmpeg's subtitles filter
can't open an empty subtitle file at all (hard failure, not just "no
captions"). So if no word timings come back, we fall back to splitting the
script text into even chunks spread proportionally across the narration's
actual length (measured with ffprobe once the audio is written). Slightly
less perfectly synced than word-level timing, but always produces a valid
file.

We write .ass instead of plain .srt because .ass supports inline style
overrides -- that's what lets us bold the whole line, draw an opaque box
behind it, and highlight specific keywords (e.g. the video's subject) in a
different color, matching a bold "callout" caption style instead of a
plain outlined subtitle.
"""
import asyncio
import subprocess

import config
import edge_tts

MAX_CHARS_PER_CUE = 42  # roughly one short caption line

# ASS colors are &HAABBGGRR (alpha, blue, green, red) with AA=00 meaning fully opaque.
HIGHLIGHT_COLOR_TAG = config.CAPTION_HIGHLIGHT_COLOR  # e.g. "&H0000D7FF&" (gold)
DEFAULT_COLOR_TAG = "&H00FFFFFF&"  # white, matches the Default style's PrimaryColour

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,{fontsize},&H00FFFFFF,{highlight_style},&H00000000,&H00000000,1,0,0,0,100,100,0,0,3,14,0,2,60,60,{marginv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ass_header() -> str:
    return ASS_HEADER.format(
        width=config.VIDEO_WIDTH,
        height=config.VIDEO_HEIGHT,
        fontsize=config.CAPTION_FONTSIZE,
        marginv=config.CAPTION_MARGIN_V,
        highlight_style=HIGHLIGHT_COLOR_TAG.rstrip("&"),  # style rows don't take the trailing '&'
    )


def _ticks_to_ass_time(ticks: int) -> str:
    """edge-tts reports offsets in 100-nanosecond ticks; convert to ASS H:MM:SS.cc."""
    total_cs = ticks // 100_000  # 100ns ticks -> centiseconds
    hours, rem = divmod(total_cs, 360_000)
    minutes, rem = divmod(rem, 6_000)
    seconds, cs = divmod(rem, 100)
    return f"{hours:d}:{minutes:02d}:{seconds:02d}.{cs:02d}"


def _seconds_to_ass_time(seconds: float) -> str:
    return _ticks_to_ass_time(int(seconds * 10_000_000))


def _clean_word(word: str) -> str:
    return "".join(ch for ch in word.lower() if ch.isalnum())


def _highlighted_line(words, highlight_terms) -> str:
    """Join words into one caption line, wrapping any word that matches
    highlight_terms (a set of lowercased alnum-only keywords) in the
    gold highlight color."""
    if not highlight_terms:
        return " ".join(words)
    parts = []
    for w in words:
        if _clean_word(w) in highlight_terms:
            parts.append(f"{{\\c{HIGHLIGHT_COLOR_TAG}}}{w}{{\\c{DEFAULT_COLOR_TAG}}}")
        else:
            parts.append(w)
    return " ".join(parts)


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

    Returns a list of (start_seconds, end_seconds, words) tuples spanning the
    whole narration, weighted by each chunk's character length. `words` is a
    list of the individual words in that chunk (kept as a list, not a joined
    string, so highlighting can still be applied per-word).
    """
    words = text.split()
    chunks, current, current_len = [], [], 0
    for w in words:
        if current and current_len + len(w) + 1 > MAX_CHARS_PER_CUE:
            chunks.append(current)
            current, current_len = [], 0
        current.append(w)
        current_len += len(w) + 1
    if current:
        chunks.append(current)
    if not chunks:
        return [(0.0, duration_seconds, text.split())] if text else []

    total_chars = sum(len(" ".join(c)) for c in chunks) or 1
    cues, t = [], 0.0
    for c in chunks:
        dur = duration_seconds * (len(" ".join(c)) / total_chars)
        cues.append((t, t + dur, c))
        t += dur
    return cues


async def _synthesize(text: str, voice: str, mp3_path: str, ass_path: str, highlight_terms):
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
        with open(ass_path, "w", encoding="utf-8") as ass_file:
            ass_file.write(_ass_header())
            for cue in cues:
                start = cue[0]["offset"]
                end = cue[-1]["offset"] + cue[-1]["duration"]
                line = _highlighted_line([w["text"] for w in cue], highlight_terms)
                ass_file.write(
                    f"Dialogue: 0,{_ticks_to_ass_time(start)},{_ticks_to_ass_time(end)},"
                    f"Default,,0,0,0,,{line}\n"
                )
        last = word_events[-1]
        return (last["offset"] + last["duration"]) / 10_000_000

    # Fallback: no word-boundary timing came back from edge-tts at all.
    duration = _ffprobe_duration_seconds(mp3_path)
    fallback_cues = _fallback_cues_from_text(text, duration)
    with open(ass_path, "w", encoding="utf-8") as ass_file:
        ass_file.write(_ass_header())
        for start, end, words in fallback_cues:
            line = _highlighted_line(words, highlight_terms)
            ass_file.write(
                f"Dialogue: 0,{_seconds_to_ass_time(start)},{_seconds_to_ass_time(end)},"
                f"Default,,0,0,0,,{line}\n"
            )
    return duration


def synthesize(text: str, voice: str, mp3_path: str, ass_path: str, highlight_terms=None) -> float:
    """Synchronous wrapper. Returns approximate narration duration in seconds.

    highlight_terms: optional iterable of keywords (matched case-insensitively,
    punctuation-stripped) that should be rendered in the caption highlight color
    -- typically the video's main subject (e.g. {"venus"} or {"fermi", "paradox"}).
    """
    terms = {(_clean_word(t)) for t in (highlight_terms or [])}
    return asyncio.run(_synthesize(text, voice, mp3_path, ass_path, terms))
