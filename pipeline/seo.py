"""Lightweight SEO helpers: auto-generate hashtags and a consistent description
from a script's existing `tags` list, so every video gets this automatically --
no manual per-video hashtag writing needed.
"""

_ACRONYMS = {"seti", "nasa", "uap", "ufo", "iss"}


def _tag_to_hashtag(tag: str) -> str:
    words = tag.replace("-", " ").split()
    parts = [w.upper() if w.lower() in _ACRONYMS else w.capitalize() for w in words]
    return "#" + "".join(parts)


def build_hashtags(tags, max_hashtags: int = 5) -> str:
    """Turn a list of plain-text tags into a de-duplicated hashtag line.

    Capped conservatively: YouTube only displays the first 3 hashtags above your
    title, and if a video has more than ~15 total hashtags, YouTube ignores ALL
    of them. 5 keeps it well inside that limit while still covering the video.
    """
    seen, hashtags = set(), []
    for tag in tags:
        h = _tag_to_hashtag(tag)
        key = h.lower()
        if key in seen:
            continue
        seen.add(key)
        hashtags.append(h)
        if len(hashtags) >= max_hashtags:
            break
    return " ".join(hashtags)


def build_description(script: dict, footage_credit: str) -> str:
    """Compose the final YouTube description: base description + auto hashtags + footage credit."""
    base = script.get("description") or script["body"]
    hashtags = build_hashtags(script.get("tags", []))
    parts = [base]
    if hashtags:
        parts.append(hashtags)
    parts.append(footage_credit)
    return "\n\n".join(parts)
