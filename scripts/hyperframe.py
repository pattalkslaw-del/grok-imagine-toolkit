#!/usr/bin/env python3
"""
hyperframe.py — Orchestrate multi-clip video pieces longer than 15 seconds.

The pattern: anchor image (R2V or generated) -> I2V chain -> stitch.
Re-anchors with R2V every N hops to prevent identity drift.

USAGE:
    hyperframe.py --beats BEATS.json [options]

BEATS.json format:
    {
      "anchor_image": "/path/to/anchor.jpg",  // optional: existing image
      "anchor_prompt": "...",                  // generated if anchor_image absent
      "ambient": "soft cafe chatter, distant breeze",  // optional: appended to every prompt
      "beats": [
        {"prompt": "She walks slowly forward toward the camera", "duration": 8},
        {"prompt": "She stops and turns to look at the fountain", "duration": 8},
        {"prompt": "She sits on a bench by the fountain", "duration": 8},
        {"prompt": "She looks up and smiles softly", "duration": 6}
      ]
    }

OPTIONS:
    --beats PATH                JSON file (see schema above)
    --output-dir PATH           override $GROK_OUTPUT_ROOT
    --label LABEL               output folder slug
    --resolution {480p,720p}    default from config
    --aspect-ratio AR           default from config
    --reanchor-every N          re-anchor with R2V every N hops, default 6
    --crossfade N               crossfade in seconds (e.g. 0.5)
    --no-confirm                skip cost confirmation prompt
    --resume PATH               resume an interrupted run from its output dir

EXAMPLES:
    hyperframe.py --beats plaza-walk.json --label plaza-walk --crossfade 0.5
    hyperframe.py --beats long-piece.json --reanchor-every 4 --no-confirm
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from grok_client import (
    load_config, generate_image, generate_video,
    save_image_response, save_video_response,
    make_output_dir, first_frame, last_frame, stage_for_ffmpeg, encode_data_uri,
    GrokImagineError, ModerationFiltered, FFMPEG, download,
)


def estimate_cost(beats: list[dict], resolution: str, anchor_needed: bool, reanchor_every: int) -> float:
    """Pre-flight cost estimate."""
    n_beats = len(beats)
    n_anchors = (1 if anchor_needed else 0) + max(0, (n_beats - 1) // reanchor_every)
    anchor_cost = n_anchors * 0.07  # image-pro
    rate = 0.07 if resolution == "720p" else 0.05
    video_cost = sum(b.get("duration", 8) * rate for b in beats)
    return anchor_cost + video_cost


def confirm_cost(estimated: float, no_confirm: bool) -> bool:
    if no_confirm:
        return True
    print(f"\nEstimated cost for this hyperframe run: ${estimated:.4f}")
    print(f"Continue? [y/N] ", end="", flush=True)
    ans = sys.stdin.readline().strip().lower()
    return ans in ("y", "yes")


def gen_anchor(prompt: str, cfg: dict, out_dir: Path, label: str = "anchor") -> tuple[Path, dict]:
    """Generate an anchor image with grok-imagine-image-pro. Returns local path + response."""
    print(f"  Generating anchor (image-pro): {prompt[:80]}...")
    resp = generate_image(
        prompt=prompt,
        model="grok-imagine-image-pro",
        n=1,
        resolution="1k",
        aspect_ratio=cfg["GROK_VID_ASPECT_RATIO"],
        cfg=cfg,
    )
    saved = save_image_response(resp, out_dir, label=label)
    cost = resp["usage"]["cost_in_usd_ticks"] / 1e10
    print(f"    -> {saved[0]} (${cost:.4f})")
    return saved[0], resp


def gen_clip_r2v(prompt: str, anchor_path: Path, duration: int, cfg: dict, args) -> dict:
    """Generate a video clip using R2V (anchor as reference)."""
    print(f"  R2V clip (duration={duration}s): {prompt[:80]}...")
    return generate_video(
        prompt=prompt,
        reference_images=[{"url": encode_data_uri(anchor_path)}],
        duration=duration,
        aspect_ratio=args.aspect_ratio or cfg["GROK_VID_ASPECT_RATIO"],
        resolution=args.resolution or cfg["GROK_VID_RESOLUTION"],
        cfg=cfg,
    )


def gen_clip_i2v(prompt: str, input_image_path: Path, duration: int, cfg: dict, args) -> dict:
    """Generate a video clip using I2V (input image as start frame conditioning)."""
    print(f"  I2V clip (duration={duration}s): {prompt[:80]}...")
    return generate_video(
        prompt=prompt,
        image={"url": encode_data_uri(input_image_path)},
        duration=duration,
        aspect_ratio=args.aspect_ratio or cfg["GROK_VID_ASPECT_RATIO"],
        resolution=args.resolution or cfg["GROK_VID_RESOLUTION"],
        cfg=cfg,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--beats", required=True, help="Beats JSON file")
    p.add_argument("--output-dir")
    p.add_argument("--label", default="hyperframe")
    p.add_argument("--resolution", choices=["480p", "720p"])
    p.add_argument("--aspect-ratio")
    p.add_argument("--reanchor-every", type=int, default=6)
    p.add_argument("--crossfade", type=float, default=0.0)
    p.add_argument("--no-confirm", action="store_true")
    p.add_argument("--resume", help="Resume from existing output dir's manifest.json")
    args = p.parse_args()

    cfg = load_config()
    if args.output_dir:
        cfg["GROK_OUTPUT_ROOT"] = args.output_dir

    spec = json.loads(Path(args.beats).read_text())
    beats = spec["beats"]
    ambient = spec.get("ambient", "")
    anchor_image = spec.get("anchor_image")
    anchor_prompt = spec.get("anchor_prompt")
    if not anchor_image and not anchor_prompt:
        sys.exit("ERROR: beats JSON must include either anchor_image or anchor_prompt")

    resolution = args.resolution or cfg["GROK_VID_RESOLUTION"]

    if args.resume:
        out = Path(args.resume).expanduser().resolve()
        manifest_path = out / "manifest.json"
        if not manifest_path.exists():
            sys.exit(f"ERROR: no manifest at {manifest_path}")
        manifest = json.loads(manifest_path.read_text())
        print(f"Resuming run {manifest['run_id']} from {out}")
        completed = len([c for c in manifest.get("clips", []) if c.get("status") == "done"])
        print(f"  {completed}/{len(beats)} clips already complete")
    else:
        # Pre-flight cost estimate
        estimated = estimate_cost(beats, resolution, anchor_needed=not anchor_image, reanchor_every=args.reanchor_every)
        if not confirm_cost(estimated, args.no_confirm):
            sys.exit("Aborted by user")

        out = make_output_dir(cfg, op="hyperframe", label=args.label)
        manifest = {
            "run_id": out.name,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "beats_spec": spec,
            "config": {
                "resolution": resolution,
                "aspect_ratio": args.aspect_ratio or cfg["GROK_VID_ASPECT_RATIO"],
                "reanchor_every": args.reanchor_every,
            },
            "clips": [],
            "total_cost_ticks": 0,
        }

    # Acquire / generate anchor
    if anchor_image:
        anchor_local = Path(anchor_image).expanduser().resolve()
        if not anchor_local.exists():
            sys.exit(f"ERROR: anchor_image not found: {anchor_local}")
        # Copy to output dir for traceability
        anchor_dest = out / "anchor.jpg"
        if not anchor_dest.exists():
            shutil.copy(anchor_local, anchor_dest)
        anchor_local = anchor_dest
        manifest.setdefault("anchor", {"source": "provided", "path": str(anchor_local)})
    else:
        if "anchor" not in manifest:
            anchor_local, anchor_resp = gen_anchor(anchor_prompt, cfg, out, label="anchor")
            manifest["anchor"] = {
                "source": "generated",
                "prompt": anchor_prompt,
                "path": str(anchor_local),
                "cost_ticks": anchor_resp["usage"]["cost_in_usd_ticks"],
            }
            manifest["total_cost_ticks"] += anchor_resp["usage"]["cost_in_usd_ticks"]
        else:
            anchor_local = Path(manifest["anchor"]["path"])

    # Save manifest after anchor
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # Iterate beats
    last_input_image = None  # the image to use for the next I2V (last frame of previous clip)
    for i, beat in enumerate(beats):
        # Skip already-completed clips when resuming
        if i < len(manifest.get("clips", [])) and manifest["clips"][i].get("status") == "done":
            print(f"[beat {i+1}/{len(beats)}] already done, skipping")
            # Still need to track last_input_image for the next I2V
            last_path = manifest["clips"][i].get("last_frame")
            if last_path:
                last_input_image = Path(last_path)
            continue

        prompt = beat["prompt"]
        if ambient:
            prompt = f"{prompt}. Audio: {ambient}."
        duration = beat.get("duration", int(cfg["GROK_VID_DURATION"]))

        # Decide mode: R2V on first beat, I2V chain after, R2V re-anchor every N
        is_first = (i == 0)
        is_reanchor = (i > 0) and (i % args.reanchor_every == 0)
        mode = "R2V" if (is_first or is_reanchor) else "I2V"

        print(f"\n[beat {i+1}/{len(beats)}] {mode}")
        try:
            if mode == "R2V":
                resp = gen_clip_r2v(prompt, anchor_local, duration, cfg, args)
            else:
                # I2V from previous clip's last frame
                if not last_input_image or not last_input_image.exists():
                    print(f"  WARN: no previous last-frame; falling back to R2V from anchor")
                    resp = gen_clip_r2v(prompt, anchor_local, duration, cfg, args)
                    mode = "R2V"
                else:
                    resp = gen_clip_i2v(prompt, last_input_image, duration, cfg, args)
        except ModerationFiltered as e:
            print(f"  MODERATION FILTERED: {e}")
            print(f"  Skipping this beat. Edit prompt and resume with --resume {out}")
            manifest.setdefault("clips", []).append({
                "n": i + 1, "mode": mode, "prompt": prompt, "duration": duration,
                "status": "moderation_filtered", "error": str(e),
            })
            (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
            continue

        # Save clip
        clip_path = save_video_response(resp, out, label=f"clip-{i+1:02d}")

        # Stage for ffmpeg, extract frames
        staging = Path(cfg["GROK_STAGING"]) / f"{out.name}-clip{i+1}"
        staged = stage_for_ffmpeg(clip_path, staging)
        first_frame_path = out / f"clip-{i+1:02d}.first.jpg"
        last_frame_path = out / f"clip-{i+1:02d}.last.jpg"
        first_frame(staged, first_frame_path)
        last_frame(staged, last_frame_path)
        last_input_image = last_frame_path

        # Append to manifest
        cost_ticks = resp.get("usage", {}).get("cost_in_usd_ticks", 0)
        manifest.setdefault("clips", []).append({
            "n": i + 1,
            "mode": mode,
            "prompt": prompt,
            "duration": duration,
            "request_id": resp.get("video", {}).get("request_id", "-"),
            "video_path": str(clip_path),
            "first_frame": str(first_frame_path),
            "last_frame": str(last_frame_path),
            "cost_ticks": cost_ticks,
            "respect_moderation": resp.get("video", {}).get("respect_moderation", True),
            "status": "done",
        })
        manifest["total_cost_ticks"] += cost_ticks
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
        print(f"  -> {clip_path} (${cost_ticks/1e10:.4f})")

    # Stitch
    print(f"\nStitching {len([c for c in manifest['clips'] if c.get('status') == 'done'])} clips...")
    done_clips = [Path(c["video_path"]) for c in manifest["clips"] if c.get("status") == "done"]
    output_video = out / "output.mp4"
    stitch_args = [sys.executable, str(Path(__file__).parent / "stitch.py")]
    stitch_args.extend(str(c) for c in done_clips)
    stitch_args.extend(["--output", str(output_video)])
    if args.crossfade > 0:
        stitch_args.extend(["--crossfade", str(args.crossfade)])
    subprocess.run(stitch_args, check=True)

    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    manifest["output_video"] = str(output_video)
    manifest["total_cost_usd"] = round(manifest["total_cost_ticks"] / 1e10, 4)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))

    print(f"\n=== HYPERFRAME RUN COMPLETE ===")
    print(f"Output: {output_video}")
    print(f"Manifest: {out / 'manifest.json'}")
    print(f"Total cost: ${manifest['total_cost_usd']:.4f}")


if __name__ == "__main__":
    main()
