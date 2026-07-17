"""Central config for the automation pipeline. Edit freely."""
import os

# --- Channel / format ---
NICHE_NAME = "Space & Science Mysteries"
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920   # vertical, for Shorts
VOICE = "en-US-GuyNeural"          # free edge-tts voice; try en-US-AriaNeural, en-GB-RyanNeural, etc.
BACKGROUND_MUSIC_PATH = None        # optional path to a royalty-free mp3 (e.g. from YouTube Audio Library) mixed in quietly
MUSIC_VOLUME_DB = -22                # how far to duck the background track under narration

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
