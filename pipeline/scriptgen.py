"""Auto-writes new content_queue/*.json scripts using the free Google Gemini API,
so the queue never runs dry and nobody has to hand-write scripts anymore.

Requires a free GEMINI_API_KEY (no credit card): https://aistudio.google.com/apikey
If no key is set, top_up_queue() just prints a note and does nothing -- the
pipeline still runs fine on whatever's manually queued, same as before.
"""
import glob
import json
import os
import re

import requests

import config

GEMINI_URL_TMPL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "title": {"type": "STRING"},
        "hook": {"type": "STRING"},
        "body": {"type": "STRING"},
        "cta": {"type": "STRING"},
        "footage_keywords": {"type": "ARRAY", "items": {"type": "STRING"}},
        "tags": {"type": "ARRAY", "items": {"type": "STRING"}},
        "description": {"type": "STRING"},
    },
    "required": ["title", "hook", "body", "cta", "footage_keywords", "tags", "description"],
}

REQUIRED_FIELDS = RESPONSE_SCHEMA["required"]

PROMPT_TMPL = """You write scripts for a YouTube Shorts channel called "{niche}".
Each short is ~35-45 seconds of narration covering ONE real, well-documented
space or science mystery/phenomenon -- the kind of thing a curious general
audience finds genuinely surprising, told factually (no invented facts, no
clickbait exaggeration of things that were never actually proposed by
scientists).

Match this exact tone and structure (these are examples already produced,
for style reference only -- do NOT reuse these topics):
- Tabby's Star: unexplained irregular dimming once floated as a possible
  alien megastructure, now thought to be dust, but not fully settled.
- 'Oumuamua: first interstellar object ever observed, tumbling oddly and
  accelerating in a way not fully explained by outgassing alone.
- Betelgeuse's 2019 Great Dimming: a supergiant losing half its brightness
  from a self-ejected dust cloud, raising supernova-timing questions.

Do NOT write about any of these already-covered topics: {covered}

Return a single JSON object with these exact fields:
- title: a punchy, curiosity-driving title, under 100 characters
- hook: 1-2 sentences that open the video and grab attention immediately
- body: 3-5 sentences of the core factual explanation, calm and clear, written
  to be read aloud naturally by text-to-speech
- cta: 1-2 sentences closing the video and inviting a follow, tying back to
  the topic
- footage_keywords: exactly 3 short, generic stock-footage search phrases
  (e.g. "deep space nebula", "telescope night sky") that would return real
  matching b-roll from stock video libraries -- keep these generic, not
  overly specific to the topic, since specific phrases return no results
- tags: 5-6 lowercase YouTube tags, most specific first, last one "shorts"
- description: one sentence, under 200 characters, summarizing the video for
  the YouTube description field

Pick a topic that hasn't been covered yet. Output ONLY the JSON object."""


def _read_json_safe(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _covered_topics():
    """Titles + primary tag of every script already queued or done, so we
    don't ask Gemini to write something we've already made."""
    topics = []
    for d in (config.QUEUE_DIR, config.DONE_DIR):
        for path in sorted(glob.glob(os.path.join(d, "*.json"))):
            data = _read_json_safe(path)
            if data and data.get("title"):
                tag = (data.get("tags") or [""])[0]
                topics.append(f"{data['title']} ({tag})" if tag else data["title"])
    return topics


def _next_queue_number():
    existing = glob.glob(os.path.join(config.QUEUE_DIR, "*.json")) + glob.glob(
        os.path.join(config.DONE_DIR, "*.json")
    )
    nums = []
    for path in existing:
        m = re.match(r"(\d+)_", os.path.basename(path))
        if m:
            nums.append(int(m.group(1)))
    return (max(nums) + 1) if nums else 1


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    words = slug.split("_")
    return "_".join(words[:6]) or "untitled"


def _validate(script: dict) -> bool:
    if not isinstance(script, dict):
        return False
    for field in REQUIRED_FIELDS:
        val = script.get(field)
        if not val:
            return False
    if not isinstance(script.get("footage_keywords"), list) or not isinstance(script.get("tags"), list):
        return False
    return True


def _call_gemini(covered_topics):
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set")

    prompt = PROMPT_TMPL.format(
        niche=config.NICHE_NAME,
        covered=", ".join(covered_topics) if covered_topics else "(none yet)",
    )
    url = GEMINI_URL_TMPL.format(model=config.SCRIPTGEN_MODEL)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
            "temperature": 1.0,
        },
    }
    resp = requests.post(
        url,
        params={"key": config.GEMINI_API_KEY},
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


def generate_one(covered_topics, attempts=3):
    """Ask Gemini for one new script, retrying on invalid/malformed output.
    Returns a validated dict, or None if every attempt failed."""
    last_err = None
    for i in range(attempts):
        try:
            script = _call_gemini(covered_topics)
        except (requests.RequestException, KeyError, IndexError, ValueError) as e:
            last_err = e
            print(f"  (scriptgen attempt {i + 1}/{attempts} failed: {e})")
            continue
        if _validate(script):
            return script
        last_err = f"invalid/incomplete script: {script}"
        print(f"  (scriptgen attempt {i + 1}/{attempts} returned {last_err})")
    print(f"  (scriptgen: giving up after {attempts} attempts, last issue: {last_err})")
    return None


def top_up_queue(min_size=None, target_size=None):
    """If content_queue has fewer than min_size scripts, generate new ones
    (via Gemini) until it reaches target_size. Safe to call every run --
    it's a no-op once the queue is already full enough, and a no-op
    (with a printed note) if no GEMINI_API_KEY is configured."""
    min_size = config.QUEUE_MIN_SIZE if min_size is None else min_size
    target_size = config.QUEUE_TARGET_SIZE if target_size is None else target_size

    current = len(glob.glob(os.path.join(config.QUEUE_DIR, "*.json")))
    if current >= min_size:
        return 0

    if not config.GEMINI_API_KEY:
        print(
            f"  (content_queue has {current} script(s), below the minimum of {min_size}, "
            "but GEMINI_API_KEY isn't set -- add it as a repo secret to auto-generate new "
            "scripts, or keep queueing them manually)"
        )
        return 0

    to_make = target_size - current
    print(f"  (content_queue has {current} script(s); auto-generating {to_make} more via Gemini)")
    os.makedirs(config.QUEUE_DIR, exist_ok=True)
    covered = _covered_topics()
    made = 0
    for _ in range(to_make):
        script = generate_one(covered)
        if not script:
            break
        num = _next_queue_number()
        filename = f"{num:04d}_{_slugify(script['title'])}.json"
        path = os.path.join(config.QUEUE_DIR, filename)
        with open(path, "w") as f:
            json.dump(script, f, indent=2)
            f.write("\n")
        print(f"  (wrote {path}: {script['title']})")
        covered.append(f"{script['title']} ({(script.get('tags') or [''])[0]})")
        made += 1
    return made
