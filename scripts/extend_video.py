#!/usr/bin/env python3
"""
extend_video.py — CLI for extending an existing video by 1-10 seconds.

The output is the EXTENSION ONLY, not concatenated with the input. Use stitch.py
to combine the input and the extension.

USAGE:
    extend_video.py "<prompt>" --video PATH_OR_URL [options]

OPTIONS:
    --video PATH_OR_URL     input video (.mp4)
    --duration N            1-10 seconds for the extension, default 6
    --label LABEL
    --output-dir PATH
    --no-save
    --no-poll
    --concat                automatically concat the input + extension into one output (default off)

EXAMPLE:
    extend_video.py "The camera slowly zooms out to reveal the city skyline" --video ./clip.mp4 --duration 6 --concat
"""
import argparse
import base64
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from grok_client import (
    load_config, extend_video, save_video_response,
    make_output_dir, write_artifact_metadata, stage_for_ffmpeg, FFMPEG,
    GrokImagineError, ModerationFiltered,
)


def to_video_obj(path_or_url: str) -> dict:
    if path_or_url.startswith(("http://", "https://", "data:")):
        return {"url": path_or_url}
    p = Path(path_or_url).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(p)
    if p.suffix.lower() != ".mp4":
        raise ValueError("Video must be .mp4 per xAI requirements")
    b = p.read_bytes()
    return {"url": f"data:video/mp4;base64,{base64.b64encode(b).decode()}"}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("prompt")
    p.add_argument("--video", required=True)
    p.add_argument("--duration", type=int, default=6, choices=range(1, 11))
    p.add_argument("--label", default="")
    p.add_argument("--output-dir")
    p.add_argument("--no-save", action="store_true")
    p.add_argument("--no-poll", action="store_true")
    p.add_argument("--concat", action="store_true", help="Concat input + extension into one MP4")
    args = p.parse_args()

    video = to_video_obj(args.video)

    cfg = load_config()
    if args.output_dir:
        cfg["GROK_OUTPUT_ROOT"] = args.output_dir

    try:
        resp = extend_video(
            prompt=args.prompt, video=video, duration=args.duration,
            cfg=cfg, poll=not args.no_poll,
        )
    except ModerationFiltered as e:
        print(f"MODERATION FILTERED: {e}", file=sys.stderr)
        sys.exit(2)
    except GrokImagineError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.no_poll:
        print(f"request_id: {resp.get('request_id')}")
        return

    cost = resp.get("usage", {}).get("cost_in_usd_ticks", 0) / 1e10
    print(f"Cost: ${cost:.4f}")

    if args.no_save:
        print(f"Extension URL: {resp.get('video', {}).get('url', '?')}")
        return

    out = make_output_dir(cfg, op="vextend", label=args.label or "video-extend")
    extension_path = save_video_response(resp, out, label="extension")
    write_artifact_metadata(out, request_body={"prompt": args.prompt, "duration": args.duration}, response_body=resp, prompt=args.prompt)
    print(f"Saved extension to: {extension_path}")

    if args.concat:
        # Stage both input and extension into ffmpeg-readable dir
        staging = Path(cfg["GROK_STAGING"]) / out.name
        staging.mkdir(parents=True, exist_ok=True)
        in_src = Path(args.video).expanduser().resolve()
        in_staged = stage_for_ffmpeg(in_src, staging)
        ext_staged = stage_for_ffmpeg(extension_path, staging)

        list_file = staging / "concat.txt"
        list_file.write_text(f"file '{in_staged}'\nfile '{ext_staged}'\n")

        combined_staged = staging / "combined.mp4"
        # Try stream copy first; fall back to re-encode if codecs mismatch
        try:
            subprocess.run(
                [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
                 "-c", "copy", str(combined_staged)],
                capture_output=True, check=True,
            )
        except subprocess.CalledProcessError:
            subprocess.run(
                [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
                 "-c:v", "libx264", "-c:a", "aac", str(combined_staged)],
                capture_output=True, check=True,
            )

        combined_final = out / "combined.mp4"
        subprocess.run(["cp", str(combined_staged), str(combined_final)], check=True)
        print(f"Combined input + extension: {combined_final}")


if __name__ == "__main__":
    main()
