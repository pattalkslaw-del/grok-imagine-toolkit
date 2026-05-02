#!/usr/bin/env python3
"""
generate_video.py — CLI for video generation (T2V / I2V / R2V).

Mode is auto-detected:
    --image           -> I2V
    --reference-image -> R2V
    neither           -> T2V (prompt required)

USAGE:
    generate_video.py "<prompt>" [options]
    generate_video.py "<prompt>" --image PATH_OR_URL [options]
    generate_video.py "<prompt>" --reference-image PATH_OR_URL [...] [options]

OPTIONS:
    --image PATH_OR_URL             I2V: image becomes start frame conditioning
    --reference-image PATH_OR_URL   R2V: image is style/identity reference (repeatable)
    --duration N                    1-15 seconds, default from config (8)
    --aspect-ratio AR               1:1, 16:9, 9:16, 4:3, 3:4, 3:2, 2:3, default 16:9
    --resolution {480p,720p}        default from config (720p)
    --label LABEL
    --output-dir PATH
    --no-save                       skip download; print URL only
    --no-poll                       submit only, return request_id, don't wait

EXAMPLES:
    generate_video.py "A serene lake at sunrise, mist on water"
    generate_video.py "She walks slowly forward" --image keyframe.jpg --duration 5 --resolution 480p --label test
    generate_video.py "She turns over her shoulder" --reference-image anchor.jpg --label r2v-test
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from grok_client import (
    load_config, generate_video, save_video_response,
    make_output_dir, write_artifact_metadata, first_frame, last_frame,
    stage_for_ffmpeg, encode_data_uri,
    GrokImagineError, ModerationFiltered,
)


def to_image_obj(path_or_url: str) -> dict:
    if path_or_url.startswith(("http://", "https://", "data:")):
        return {"url": path_or_url}
    p = Path(path_or_url).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(p)
    mime = "image/jpeg"
    if p.suffix.lower() == ".png":
        mime = "image/png"
    return {"url": encode_data_uri(p, mime=mime)}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("prompt", nargs="?", help="Video prompt (required for T2V/R2V; optional for I2V)")
    p.add_argument("--image", help="I2V: input image (path or URL)")
    p.add_argument("--reference-image", action="append", help="R2V: reference image (repeatable)")
    p.add_argument("--duration", type=int)
    p.add_argument("--aspect-ratio")
    p.add_argument("--resolution", choices=["480p", "720p"])
    p.add_argument("--label", default="")
    p.add_argument("--output-dir")
    p.add_argument("--no-save", action="store_true")
    p.add_argument("--no-poll", action="store_true")
    p.add_argument("--extract-frames", action="store_true",
                   help="Extract first and last frames as JPEG next to the video")
    args = p.parse_args()

    if args.image and args.reference_image:
        p.error("Use --image (I2V) OR --reference-image (R2V), not both.")
    if not args.prompt and not args.image:
        p.error("Pass a prompt (T2V/R2V) or --image (I2V).")

    image = to_image_obj(args.image) if args.image else None
    reference_images = [to_image_obj(s) for s in args.reference_image] if args.reference_image else None

    cfg = load_config()
    if args.output_dir:
        cfg["GROK_OUTPUT_ROOT"] = args.output_dir

    mode = "i2v" if image else ("r2v" if reference_images else "t2v")
    print(f"Mode: {mode.upper()}")

    try:
        resp = generate_video(
            prompt=args.prompt or "",
            image=image,
            reference_images=reference_images,
            duration=args.duration,
            aspect_ratio=args.aspect_ratio,
            resolution=args.resolution,
            cfg=cfg,
            poll=not args.no_poll,
        )
    except ModerationFiltered as e:
        print(f"MODERATION FILTERED: {e}", file=sys.stderr)
        sys.exit(2)
    except GrokImagineError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.no_poll:
        print(f"request_id: {resp.get('request_id')}")
        print("Use the GET /v1/videos/{request_id} endpoint to poll status.")
        return

    cost = resp.get("usage", {}).get("cost_in_usd_ticks", 0) / 1e10
    print(f"Cost: ${cost:.4f}")

    if args.no_save:
        print(f"Video URL: {resp.get('video', {}).get('url', '?')}")
        return

    out = make_output_dir(cfg, op=mode, label=args.label or mode)
    video_path = save_video_response(resp, out, label="video")
    write_artifact_metadata(out, request_body={"prompt": args.prompt, "mode": mode}, response_body=resp, prompt=args.prompt or "")
    print(f"Saved video to: {video_path}")

    if args.extract_frames:
        # Stage to ffmpeg-readable path first
        staging = Path(cfg["GROK_STAGING"]) / out.name
        staged = stage_for_ffmpeg(video_path, staging)
        first_frame(staged, out / "first.jpg")
        last_frame(staged, out / "last.jpg")
        print(f"Frames: {out / 'first.jpg'}, {out / 'last.jpg'}")


if __name__ == "__main__":
    main()
