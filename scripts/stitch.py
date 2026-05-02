#!/usr/bin/env python3
"""
stitch.py — Concatenate multiple Grok Imagine clips into one video.

USAGE:
    stitch.py CLIP1 CLIP2 [CLIP3 ...] --output OUTPUT [options]

OPTIONS:
    --output PATH           output .mp4 path (required)
    --crossfade N           crossfade duration in seconds (e.g. 0.5). Default: hard cuts.
    --reencode              force re-encode (libx264 + aac). Default: try stream copy first.
    --normalize-streams     pre-normalize each clip (drop poster stream, fix codec mismatches)

Stream-copy concat works when all clips share codec, resolution, fps. Grok Imagine
clips usually do, but the script falls back to re-encode automatically if copy fails.

EXAMPLES:
    stitch.py clip1.mp4 clip2.mp4 clip3.mp4 --output story.mp4
    stitch.py clip1.mp4 clip2.mp4 clip3.mp4 --output story.mp4 --crossfade 0.5
    stitch.py *.mp4 --output complete.mp4 --reencode
"""
import argparse
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from grok_client import load_config, FFMPEG, stage_for_ffmpeg


def normalize_clip(src: Path, staging: Path) -> Path:
    """Drop the embedded poster stream, ensure clean H.264/AAC."""
    out = staging / f"norm-{src.name}"
    subprocess.run(
        [FFMPEG, "-y", "-i", str(src),
         "-map", "0:v:0", "-map", "0:a:0?",
         "-c:v", "libx264", "-c:a", "aac",
         "-pix_fmt", "yuv420p",
         str(out)],
        capture_output=True, check=True,
    )
    return out


def concat_copy(clips: list[Path], staging: Path, output: Path) -> bool:
    """Stream-copy concat. Returns True on success, False on codec mismatch."""
    list_file = staging / "concat.txt"
    list_file.write_text("\n".join(f"file '{c}'" for c in clips) + "\n")
    result = subprocess.run(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
         "-c", "copy", str(output)],
        capture_output=True,
    )
    return result.returncode == 0


def concat_reencode(clips: list[Path], staging: Path, output: Path) -> None:
    """Re-encode concat. Slower but always works."""
    list_file = staging / "concat.txt"
    list_file.write_text("\n".join(f"file '{c}'" for c in clips) + "\n")
    subprocess.run(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
         "-c:v", "libx264", "-c:a", "aac",
         "-pix_fmt", "yuv420p",
         str(output)],
        capture_output=True, check=True,
    )


def concat_crossfade(clips: list[Path], staging: Path, output: Path, fade: float) -> None:
    """
    Build an xfade filtergraph for the video stream and acrossfade for audio.
    Clips are assumed to be normalized (same codec/resolution/fps).
    """
    n = len(clips)
    if n < 2:
        # Single clip: just copy
        shutil.copy(clips[0], output)
        return

    # Get clip durations via ffmpeg's null muxer (avoids ffprobe path issue)
    durations = []
    for c in clips:
        result = subprocess.run(
            [FFMPEG, "-i", str(c), "-f", "null", "-"],
            capture_output=True, text=True,
        )
        # Parse duration from stderr
        for line in result.stderr.splitlines():
            if "Duration:" in line:
                t = line.split("Duration:")[1].split(",")[0].strip()
                hh, mm, ss = t.split(":")
                durations.append(float(hh) * 3600 + float(mm) * 60 + float(ss))
                break

    # Build xfade filter chain
    # For 3 clips with offsets at clip durations - fade duration each
    inputs = []
    for c in clips:
        inputs.extend(["-i", str(c)])

    # Video filter: xfade chain
    v_filters = []
    a_filters = []
    cumulative = 0.0
    last_v = "[0:v]"
    last_a = "[0:a]"
    for i in range(1, n):
        cumulative += durations[i - 1] - fade
        v_filters.append(
            f"{last_v}[{i}:v]xfade=transition=fade:duration={fade}:offset={cumulative}[v{i}]"
        )
        a_filters.append(
            f"{last_a}[{i}:a]acrossfade=d={fade}[a{i}]"
        )
        last_v = f"[v{i}]"
        last_a = f"[a{i}]"

    filter_complex = ";".join(v_filters + a_filters)
    cmd = [FFMPEG, "-y"] + inputs + [
        "-filter_complex", filter_complex,
        "-map", last_v, "-map", last_a,
        "-c:v", "libx264", "-c:a", "aac",
        "-pix_fmt", "yuv420p",
        str(output),
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("clips", nargs="+", help="Input MP4 clip paths")
    p.add_argument("--output", required=True, help="Output MP4 path")
    p.add_argument("--crossfade", type=float, default=0.0,
                   help="Crossfade duration in seconds (e.g. 0.5)")
    p.add_argument("--reencode", action="store_true", help="Force re-encode")
    p.add_argument("--normalize-streams", action="store_true",
                   help="Normalize each clip first (drop poster, harmonize codecs)")
    args = p.parse_args()

    cfg = load_config()
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    # Stage every input into the snap-readable staging dir
    run_id = uuid.uuid4().hex[:8]
    staging = Path(cfg["GROK_STAGING"]) / f"stitch-{run_id}"
    staging.mkdir(parents=True, exist_ok=True)

    staged_clips = []
    for c in args.clips:
        src = Path(c).expanduser().resolve()
        if not src.exists():
            print(f"ERROR: clip not found: {src}", file=sys.stderr)
            sys.exit(1)
        staged = stage_for_ffmpeg(src, staging)
        if args.normalize_streams:
            staged = normalize_clip(staged, staging)
        staged_clips.append(staged)

    print(f"Staged {len(staged_clips)} clips in {staging}")

    # Stitch
    staged_output = staging / "output.mp4"
    if args.crossfade > 0:
        if not args.normalize_streams:
            # Crossfade requires uniform codec/timebase
            staged_clips = [normalize_clip(c, staging) for c in staged_clips]
        concat_crossfade(staged_clips, staging, staged_output, args.crossfade)
        method = f"crossfade {args.crossfade}s"
    elif args.reencode:
        concat_reencode(staged_clips, staging, staged_output)
        method = "re-encode"
    else:
        if concat_copy(staged_clips, staging, staged_output):
            method = "stream copy"
        else:
            print("Stream copy failed (codec mismatch); falling back to re-encode")
            concat_reencode(staged_clips, staging, staged_output)
            method = "re-encode (fallback)"

    # Move final to user-specified output
    shutil.copy(staged_output, output)
    print(f"Stitched {len(staged_clips)} clips via {method} -> {output} ({output.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
