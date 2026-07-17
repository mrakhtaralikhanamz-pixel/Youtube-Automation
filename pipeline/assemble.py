"""clips + narration + captions -> final vertical .mp4, via ffmpeg (CLI, no extra deps)."""
import json
import os
import subprocess

import config


def _ffprobe_duration(path: str) -> float:
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokeys=1", path,
        ]
    )
    return float(out.strip())


def _normalize_clip(src: str, dst: str, target_seconds: float):
    """Scale/crop to portrait 1080x1920, loop if needed to cover target_seconds, strip audio."""
    w, h = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1"
    subprocess.run(
        [
            "ffmpeg", "-y", "-stream_loop", "-1", "-i", src,
            "-t", str(target_seconds), "-vf", vf, "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", dst,
        ],
        check=True,
    )


def assemble(clip_paths, narration_path: str, srt_path: str, out_path: str, work_dir: str):
    os.makedirs(work_dir, exist_ok=True)
    narration_duration = _ffprobe_duration(narration_path)
    per_clip_seconds = max(narration_duration / max(len(clip_paths), 1), 1.0)

    normalized = []
    for i, clip in enumerate(clip_paths):
        norm_path = os.path.join(work_dir, f"norm_{i:02d}.mp4")
        _normalize_clip(clip, norm_path, per_clip_seconds)
        normalized.append(norm_path)

    concat_list_path = os.path.join(work_dir, "concat_list.txt")
    with open(concat_list_path, "w") as f:
        for p in normalized:
            f.write(f"file '{os.path.abspath(p)}'\n")

    silent_video = os.path.join(work_dir, "silent_concat.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path,
         "-c", "copy", silent_video],
        check=True,
    )

    # Burn in captions (subtitles filter re-encodes, so do it in the same pass as trimming to
    # the exact narration length and adding audio).
    srt_escaped = srt_path.replace(":", "\\:")
    subtitle_style = "FontName=Arial,Fontsize=13,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Alignment=2,MarginV=120"
    vf = f"subtitles={srt_escaped}:force_style='{subtitle_style}'"

    cmd = [
        "ffmpeg", "-y",
        "-i", silent_video,
        "-i", narration_path,
    ]

    filter_complex = None
    audio_map = ["-map", "0:v", "-map", "1:a"]

    if config.BACKGROUND_MUSIC_PATH and os.path.exists(config.BACKGROUND_MUSIC_PATH):
        cmd += ["-stream_loop", "-1", "-i", config.BACKGROUND_MUSIC_PATH]
        filter_complex = (
            f"[2:a]volume={config.MUSIC_VOLUME_DB}dB[music];"
            f"[1:a][music]amix=inputs=2:duration=first[aout]"
        )
        cmd += ["-filter_complex", filter_complex, "-map", "0:v", "-map", "[aout]"]
    else:
        cmd += audio_map

    cmd += [
        "-t", str(narration_duration),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k",
        "-shortest",
        out_path,
    ]
    subprocess.run(cmd, check=True)
    return out_path
