"""final .mp4 -> thumbnail .jpg, via ffmpeg (frame grab) + Pillow (text overlay)."""
import subprocess

from PIL import Image, ImageDraw, ImageFont


def _grab_frame(video_path: str, out_path: str, at_seconds: float = 1.0):
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(at_seconds), "-i", video_path, "-frames:v", "1", out_path],
        check=True,
    )


def _find_font(size: int):
    for candidate in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_thumbnail(video_path: str, title_text: str, out_path: str, frame_path: str):
    _grab_frame(video_path, frame_path)
    img = Image.open(frame_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    requested_size = int(img.width * 0.09)
    font = _find_font(size=requested_size)
    font_size = getattr(font, "size", requested_size)

    # simple word-wrap
    words, lines, current = title_text.split(), [], ""
    for w in words:
        trial = f"{current} {w}".strip()
        if draw.textlength(trial, font=font) > img.width * 0.9 and current:
            lines.append(current)
            current = w
        else:
            current = trial
    if current:
        lines.append(current)

    line_height = font_size + 10
    total_height = line_height * len(lines)
    y = img.height * 0.55 - total_height / 2

    for line in lines:
        w = draw.textlength(line, font=font)
        x = (img.width - w) / 2
        # outline for readability over any background
        for dx in (-3, 3):
            for dy in (-3, 3):
                draw.text((x + dx, y + dy), line, font=font, fill="black")
        draw.text((x, y), line, font=font, fill="white")
        y += line_height

    img.save(out_path, quality=92)
    return out_path
