#!/usr/bin/env python3
"""
edit_video.py — CLI for video editing.

USAGE:
    edit_video.py "<prompt>" --video PATH_OR_URL [options]

OPTIONS:
    --video PATH_OR_URL     input video (must be .mp4, ≤ 8.7s)
    --label LABEL
    --output-dir PATH
    --no-save
    --no-poll

EXAMPLE:
    edit_video.py "Give the woman a silver necklace" --video ./input.mp4 --label necklace-edit
"""
import argparse
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from grok_client import (
    load_config, edit_video, save_video_response,
    make_output_dir, write_artifact_metadata,
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
    p.add_argument("--label", default="")
    p.add_argument("--output-dir")
    p.add_argument("--no-save", action="store_true")
    p.add_argument("--no-poll", action="store_true")
    args = p.parse_args()

    video = to_video_obj(args.video)

    cfg = load_config()
    if args.output_dir:
        cfg["GROK_OUTPUT_ROOT"] = args.output_dir

    try:
        resp = edit_video(prompt=args.prompt, video=video, cfg=cfg, poll=not args.no_poll)
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
        print(f"Edited video URL: {resp.get('video', {}).get('url', '?')}")
        return

    out = make_output_dir(cfg, op="vedit", label=args.label or "video-edit")
    saved = save_video_response(resp, out, label="edited")
    write_artifact_metadata(out, request_body={"prompt": args.prompt}, response_body=resp, prompt=args.prompt)
    print(f"Saved edited video to: {saved}")


if __name__ == "__main__":
    main()
