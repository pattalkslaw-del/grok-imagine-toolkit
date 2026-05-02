#!/usr/bin/env python3
"""
generate_image.py — CLI for text-to-image generation.

USAGE:
    generate_image.py "<prompt>" [options]

OPTIONS:
    --model {grok-imagine-image,grok-imagine-image-pro}
    --n N                   number of images (1-10), default from config
    --aspect-ratio AR       1:1, 16:9, 9:16, etc., default from config
    --resolution {1k,2k}    default from config (1k)
    --response-format {url,b64_json}    default from config (url)
    --label LABEL           filesystem-friendly slug for output folder
    --output-dir PATH       override $GROK_OUTPUT_ROOT for this call
    --no-save               don't download; just print URLs

EXAMPLES:
    generate_image.py "A diner chalkboard: TODAY $24 lobster roll"
    generate_image.py "Hero product shot of a watch" --model grok-imagine-image-pro --aspect-ratio 16:9 --resolution 2k --label hero-watch
    generate_image.py "Cat in a tree" --n 4 --label cat-variants
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from grok_client import (
    load_config, generate_image, save_image_response,
    make_output_dir, write_artifact_metadata, GrokImagineError,
)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("prompt", help="Text prompt for image generation")
    p.add_argument("--model")
    p.add_argument("--n", type=int)
    p.add_argument("--aspect-ratio")
    p.add_argument("--resolution", choices=["1k", "2k"])
    p.add_argument("--response-format", choices=["url", "b64_json"])
    p.add_argument("--label", default="")
    p.add_argument("--output-dir")
    p.add_argument("--no-save", action="store_true", help="Skip download; print URLs only")
    args = p.parse_args()

    cfg = load_config()
    if args.output_dir:
        cfg["GROK_OUTPUT_ROOT"] = args.output_dir

    try:
        resp = generate_image(
            prompt=args.prompt,
            model=args.model,
            n=args.n,
            aspect_ratio=args.aspect_ratio,
            resolution=args.resolution,
            response_format=args.response_format,
            cfg=cfg,
        )
    except GrokImagineError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    cost = resp.get("usage", {}).get("cost_in_usd_ticks", 0) / 1e10
    print(f"Cost: ${cost:.4f}")

    if args.no_save:
        for i, item in enumerate(resp.get("data", [])):
            print(f"Image {i+1}: {item.get('url') or '(b64 inline)'}")
        return

    out = make_output_dir(cfg, op="t2i", label=args.label or "image")
    saved = save_image_response(resp, out, label="image")
    write_artifact_metadata(out, request_body={"prompt": args.prompt}, response_body=resp, prompt=args.prompt)
    print(f"Saved {len(saved)} image(s) to: {out}")
    for p_ in saved:
        print(f"  {p_}")


if __name__ == "__main__":
    main()
