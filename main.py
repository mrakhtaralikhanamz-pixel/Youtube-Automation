"""Orchestrates the full pipeline for the single oldest script in content_queue/."""
import glob
import json
import os
import shutil

import config
from pipeline import tts, footage, assemble, thumbnail, upload, seo


def _next_queued_script():
    files = sorted(glob.glob(os.path.join(config.QUEUE_DIR, "*.json")))
    if not files:
        return None
    return files[0]


def _highlight_terms(script):
    """Pick the words to highlight in captions -- the video's main subject,
    taken from its first (most specific) tag, e.g. "venus" or "fermi paradox".
    """
    tags = script.get("tags", [])
    if not tags:
        return set()
    words = tags[0].replace("-", " ").split()
    return {w.strip(".,'\"").lower() for w in words if len(w.strip(".,'\"")) > 2}


def run_one():
    script_path = _next_queued_script()
    if not script_path:
        print("Content queue is empty — nothing to produce. Ask Claude to write more scripts.")
        return

    with open(script_path) as f:
        script = json.load(f)

    work_dir = config.WORK_DIR
    if os.path.exists(work_dir):
        shutil.rmtree(work_dir)
    os.makedirs(work_dir)

    full_text = " ".join([script["hook"], script["body"], script["cta"]])
    narration_path = os.path.join(work_dir, "narration.mp3")
    ass_path = os.path.join(work_dir, "captions.ass")
    print(f"[1/5] Synthesizing narration for: {script['title']}")
    tts.synthesize(full_text, config.VOICE, narration_path, ass_path, highlight_terms=_highlight_terms(script))

    print(f"[2/5] Fetching footage for keywords: {script['footage_keywords']}")
    clip_paths = footage.fetch_all(script["footage_keywords"], os.path.join(work_dir, "clips"))

    final_path = os.path.join(work_dir, "final.mp4")
    print("[3/5] Assembling final video with ffmpeg...")
    assemble.assemble(clip_paths, narration_path, ass_path, final_path, work_dir)

    thumb_path = os.path.join(work_dir, "thumbnail.jpg")
    frame_path = os.path.join(work_dir, "frame.jpg")
    print("[4/5] Generating thumbnail...")
    thumbnail.make_thumbnail(final_path, script["title"], thumb_path, frame_path)

    print("[5/5] Uploading to YouTube...")
    footage_credit = "Footage: NASA/Pexels/Pixabay (public domain / free-use, per each service's license)."
    description = seo.build_description(script, footage_credit)
    video_id = upload.upload_video(
        final_path,
        title=script["title"],
        description=description,
        tags=script.get("tags", []),
        thumbnail_path=thumb_path,
    )
    print(f"Uploaded as https://youtu.be/{video_id} (privacy: {config.DEFAULT_PRIVACY})")

    os.makedirs(config.DONE_DIR, exist_ok=True)
    shutil.move(script_path, os.path.join(config.DONE_DIR, os.path.basename(script_path)))
    shutil.rmtree(work_dir)


if __name__ == "__main__":
    run_one()
