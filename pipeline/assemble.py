"""clips + narration + captions -> final vertical .mp4, via ffmpeg (CLI, no extra deps)."""
import os
import subprocess

import config


def _ffprobe_duration(path: str) -> float:
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "csv=p=0", path,
        ]
    )
    return float(out.strip())


def _normalize_clip(src: str, dst: str, target_seconds: float):
    """Scale/crop to portrait 1080x1920, loop if needed to cover target_seconds, strip audio.

    Also forces a consistent 30fps output -- source stock/NASA clips arrive at all
    sorts of native frame rates (15fps is common for older archival footage), and
    without normalizing this here the final video inherits whatever the clip happened
    to be shot at, which reads as choppy/stuttery when it's lower than ~24fps.
    """
    w, h = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps=30"
    subprocess.run(
        [
            "ffmpeg", "-y", "-stream_loop", "-1", "-i", src,
            "-t", str(target_seconds), "-vf", vf, "-an",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", dst,
        ],
        check=True,
    )


def _loudnorm_narration(narration_path: str, out_path: str):
    """Normalize narration loudness as its own standalone ffmpeg pass.

    This has to run as a separate pass rather than as one branch of the bigger
    mixing filter_complex below -- piping loudnorm's output directly into an amix
    in the same filter graph is a known bad combo that silently truncates the
    mixed audio to a few seconds (reproduced locally: an 8s narration mixed this
    way came out ~5s every time). Normalizing to its own file first avoids it.
    """
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", narration_path,
            "-af", f"loudnorm=I={config.NARRATION_TARGET_LUFS}:TP=-1.5:LRA=11",
            "-ar", "44100", out_path,
        ],
        check=True,
    )


def _ambient_music_inputs_and_filter(narration_label: str, out_label: str):
    """Build ffmpeg -i args + a filter_complex fragment for a synthesized, royalty-free
    ambient background bed (three soft sine tones + gentle tremolo + lowpass), mixed
    quietly under the narration. No file to download, no license/attribution to track.
    """
    input_args = [
        "-f", "lavfi", "-i", "sine=frequency=110:sample_rate=44100",
        "-f", "lavfi", "-i", "sine=frequency=164.81:sample_rate=44100",
        "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100",
    ]
    # indices shift depending on how many inputs come before these three -- caller fills them in
    filt = (
        "[IDX0][IDX1][IDX2]amix=inputs=3:duration=longest:dropout_transition=0,"
        f"tremolo=f=0.12:d=0.25,lowpass=f=900,volume={config.AMBIENT_MUSIC_GAIN}[amb];"
        f"[{narration_label}][amb]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[{out_label}]"
    )
    return input_args, filt


def assemble(clip_paths, narration_path: str, ass_path: str, out_path: str, work_dir: str):
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

    # Loudness-normalize narration as its own pass first (see _loudnorm_narration for why).
    narration_norm_path = os.path.join(work_dir, "narration_norm.wav")
    _loudnorm_narration(narration_path, narration_norm_path)

    # Burn in captions (subtitles filter re-encodes, so do it in the same pass as trimming to
    # the exact narration length and adding audio). The .ass file already carries its own
    # bold/boxed/highlighted style, so no force_style override is needed here.
    ass_escaped = ass_path.replace(":", "\\:")

    cmd = ["ffmpeg", "-y", "-i", silent_video, "-i", narration_norm_path]
    # input index 0 = video, 1 = normalized narration; next free index tracks whatever
    # extra audio inputs (custom music file, or the 3 synthesized ambient tones) follow.
    next_idx = 2

    if config.BACKGROUND_MUSIC_PATH and os.path.exists(config.BACKGROUND_MUSIC_PATH):
        cmd += ["-stream_loop", "-1", "-i", config.BACKGROUND_MUSIC_PATH]
        audio_filter = (
            f"[{next_idx}:a]volume={config.MUSIC_VOLUME_DB}dB[music];"
            f"[1:a][music]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
        )
        next_idx += 1
    elif config.AMBIENT_MUSIC:
        amb_inputs, amb_filter = _ambient_music_inputs_and_filter("1:a", "aout")
        amb_filter = amb_filter.replace("IDX0", f"{next_idx}:a").replace(
            "IDX1", f"{next_idx + 1}:a"
        ).replace("IDX2", f"{next_idx + 2}:a")
        cmd += amb_inputs
        audio_filter = amb_filter
        next_idx += 3
    else:
        audio_filter = "[1:a]anull[aout]"

    filter_complex = f"[0:v]subtitles={ass_escaped}[vout];{audio_filter}"

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-t", str(narration_duration),
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k",
        "-shortest",
        out_path,
    ]
    subprocess.run(cmd, check=True)
    return out_path
