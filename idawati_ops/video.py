"""Promo-video assembler: 3 clips + end card into a 30s 9:16 video.

Proven recipe (Berta videos): each clip is scaled/cropped to 704x1248
(crop-fill, NO blur bands), 30 fps, H.264 + AAC. Three 9s clips plus a
3s end card (solid maroon background, gold lines, bold serif text).
Audio is prepared separately and muxed at the end.

This module only assembles files the operator supplies — it generates no
media itself. ffmpeg/ffprobe must be installed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

WIDTH = 704
HEIGHT = 1248
FPS = 30
CLIP_SECONDS = 9
CARD_SECONDS = 3
TOTAL_SECONDS = CLIP_SECONDS * 3 + CARD_SECONDS
MAROON = "0x6B1F2A"
GOLD = "D4AF37"

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)


class VideoError(Exception):
    """Raised when ffmpeg is missing or an assembly step fails."""


def find_tools() -> tuple[str, str]:
    """Return (ffmpeg, ffprobe) paths, or raise VideoError if missing."""
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise VideoError(
            "ffmpeg and ffprobe are required but were not found in PATH. "
            "Install ffmpeg (e.g. `sudo apt install ffmpeg`) and retry."
        )
    return ffmpeg, ffprobe


def pick_font() -> str:
    """Return the first available bold serif font, or '' if none found."""
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return ""


def segment_filter() -> str:
    """Crop-fill filter for one clip: 704x1248, 30 fps, yuv420p."""
    return (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},fps={FPS},format=yuv420p"
    )


def escape_drawtext(text: str) -> str:
    """Escape text for ffmpeg drawtext (colons, quotes, backslashes, %)."""
    return (
        text.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace(":", "\\:")
        .replace("%", "\\%")
    )


def endcard_input() -> str:
    """Lavfi input spec for the end card: solid maroon frame, 3 seconds.

    The frame rate is forced to the project fps: without it the color
    source defaults to 25 fps, and concatenating mixed-fps segments with
    stream copy silently shortens the card.
    """
    return f"color=c={MAROON}:s={WIDTH}x{HEIGHT}:d={CARD_SECONDS}:r={FPS}"


def endcard_filter(text: str, font: str) -> str:
    """Build the end-card filtergraph: maroon bg, gold lines, centered text.

    Layout: two horizontal gold lines with the credit text between them,
    all centered on a solid maroon frame.
    """
    safe = escape_drawtext(text)
    font_opt = f":fontfile={font}" if font else ""
    return (
        f"fps={FPS},format=yuv420p,"
        f"drawbox=x=32:y=520:w={WIDTH - 64}:h=4:color={GOLD}:t=fill,"
        f"drawbox=x=32:y=724:w={WIDTH - 64}:h=4:color={GOLD}:t=fill,"
        f"drawtext=text='{safe}'{font_opt}:fontsize=44:fontcolor={GOLD}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2"
    )


def probe_duration(ffprobe: str, path: str) -> float:
    """Return the duration in seconds of a media file via ffprobe."""
    out = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def _run(cmd: list[str], step: str) -> None:
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        raise VideoError(
            f"ffmpeg step failed ({step}): {exc.stderr.strip()[-500:]}"
        ) from exc


def build_video(clips: list[str], audio: str, text: str, out: str) -> dict:
    """Assemble 3 clips + audio + end card into a 30s 9:16 video.

    Returns {"out": path, "duration": seconds, "segments": [paths]}.
    Raises VideoError on any failure. Temporary files are cleaned up.
    """
    if len(clips) != 3:
        raise VideoError(f"exactly 3 clips are required, got {len(clips)}")
    for path in list(clips) + [audio]:
        if not os.path.isfile(path):
            raise VideoError(f"file not found: {path}")
    if not text.strip():
        raise VideoError("end-card --text must not be empty")
    ffmpeg, ffprobe = find_tools()
    font = pick_font()

    tmp = tempfile.mkdtemp(prefix="idawati-ops-video-")
    try:
        segments: list[str] = []
        for i, clip in enumerate(clips):
            seg = os.path.join(tmp, f"seg{i}.mp4")
            _run(
                [ffmpeg, "-y", "-v", "error", "-i", clip,
                 "-vf", segment_filter(), "-t", str(CLIP_SECONDS),
                 "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", seg],
                f"segment {i + 1}",
            )
            segments.append(seg)

        card = os.path.join(tmp, "card.mp4")
        _run(
            [ffmpeg, "-y", "-v", "error", "-f", "lavfi",
             "-i", endcard_input(),
             "-vf", endcard_filter(text, font),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", card],
            "end card",
        )

        concat_list = os.path.join(tmp, "concat.txt")
        with open(concat_list, "w", encoding="utf-8") as fh:
            for seg in segments + [card]:
                fh.write(f"file '{seg}'\n")
        video_only = os.path.join(tmp, "video.mp4")
        _run(
            [ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0",
             "-i", concat_list, "-c", "copy", video_only],
            "concat",
        )

        # Audio is prepared separately (trimmed/padded to 30s), then muxed.
        audio_30 = os.path.join(tmp, "audio.m4a")
        _run(
            [ffmpeg, "-y", "-v", "error", "-i", audio,
             "-af", f"apad,atrim=0:{TOTAL_SECONDS}",
             "-t", str(TOTAL_SECONDS), "-c:a", "aac", "-b:a", "128k", audio_30],
            "audio",
        )
        _run(
            [ffmpeg, "-y", "-v", "error", "-i", video_only, "-i", audio_30,
             "-c:v", "copy", "-c:a", "aac", "-shortest", out],
            "mux",
        )
        duration = probe_duration(ffprobe, out)
        return {"out": out, "duration": duration, "segments": segments}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
