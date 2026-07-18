"""Central config for the automation pipeline. Edit freely."""
import os

# --- Channel / format ---
NICHE_NAME = "Space & Science Mysteries"
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920   # vertical, for Shorts
VOICE = "en-US-GuyNeural"          # free edge-tts voice; try en-US-AriaNeural, en-GB-RyanNeural, etc.
BACKGROUND_MUSIC_PATH = None        # optional path to a royalty-free mp3 (e.g. from YouTube Audio Library) mixed in quietly.
                                     # Leave as None to use the built-in synthesized ambient bed instead (no download needed).
MUSIC_VOLUME_DB = -22                # how far to duck a BACKGROUND_MUSIC_PATH track under narration, if one is set

# --- Audio mastering ---
NARRATION_TARGET_LUFS = -14          # loudness narration is normalized to (YouTube/TikTok/Reels typically sit around -14 LUFS)
AMBIENT_MUSIC = True                 # add a subtle synthesized background bed under the narration when no BACKGROUND_MUSIC_PATH is set
AMBIENT_MUSIC_GAIN = 0.35            # linear gain of the synthesized ambient bed (higher = more audible); ~0.35 sits well under narration

# --- Captions / subtitle style ---
CAPTION_FONTSIZE = 62                # in px, relative to a 1080x1920 canvas
CAPTION_MARGIN_V = 700               # distance of the caption box from the bottom edge, in px (kept above the Shorts UI safe zone)
CAPTION_HIGHLIGHT_COLOR = "&H0000D7FF&"  # ASS BGR hex for the highlighted-keyword color (gold/yellow)

# --- Upload behavior ---
DEFAULT_PRIVACY = "private"   # "private" | "unlisted" | "public" -- keep "private" until you trust the pipeline
DEFAULT_CATEGORY_ID = "27"    # 27 = Education. See https://developers.google.com/youtube/v3/docs/videoCategories/list
MADE_FOR_KIDS = False

# --- Footage sources (in priority order; first with results wins per keyword) ---
FOOTAGE_SOURCES = ["nasa", "pexels", "pixabay"]  # NASA needs no key; Pexels/Pixabay need free API keys below

# --- Secrets (set as environment variables / GitHub Actions secrets — never hardcode) ---
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")
YT_CLIENT_ID = os.environ.get("YT_CLIENT_ID", "")
YT_CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET", "")
YT_REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN", "")

# --- Paths ---
QUEUE_DIR = "content_queue"
DONE_DIR = "content_done"
WORK_DIR = "work"   # scratch space for downloaded clips / intermediate files, wiped each run
