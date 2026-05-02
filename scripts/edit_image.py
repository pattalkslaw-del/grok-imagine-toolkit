#!/usr/bin/env python3
"""
edit_image.py — CLI for image editing.

USAGE:
    edit_image.py "<prompt>" --image PATH_OR_URL [options]
    edit_image.py "<prompt>" --images PATH_OR_URL --images PATH_OR_URL ... [options]

The --image flag is for single-input edits.
The --images flag (repeatable, max 5) is for multi-image reference. Use <IMAGE_0>, <IMAGE_1>, ... in the prompt.

OPTIONS:
    --image PATH_OR_URL     single input image
    --images PATH_OR_URL    multi-input (repeatable, max 5)
    --mask PATH_OR_URL      optional mask (white = edit, black = preserve)
    --model
    --n N
    --aspect-ratio AR
    --resolution {1k,2k}
    --response-format {url,b64_json}
    --label LABEL
    --output-dir PATH
    --no-save

Local file paths are auto-encoded as base64 data URIs. Remote URLs are passed through.

EXAMPLES:
    edit_image.py "Render this as a pencil sketch" --image ./photo.jpg --label sketch
    edit_image.py "Show <IMAGE_0> in the setting of <IMAGE_1>. Preserve face from IMAGE_0." --images ./char.jpg --images ./scene.jpg --label composite
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from grok_client import (
    load_config, edit_image, save_image_response,
    make_output_dir, write_artifact_metadata, encode_data_uri,
    GrokImagineError,
)


def to_image_obj(path_or_url: str) -> dict:
    """Convert a path or URL to the image-object shape the API expects."""
    if path_or_url.startswith(("http://", "https://", "data:")):
        return {"url": path_or_url}
    p = Path(path_or_url).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(p)
    mime = "image/jpeg"
    if p.suffix.lower() == ".png":
        mime = "image/png"
    elif p.suffix.lower() == ".webp":
        mime = "image/webp"
    return {"url": encode_data_uri(p, mime=mime)}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("prompt")
    p.add_argument("--image", help="Single input image path or URL")
    p.add_argument("--images", action="append", help="Multi-input image path or URL (repeatable, max 5)")
    p.add_argument("--mask", help="Optional mask path or URL")
    p.add_argument("--model")
    p.add_argument("--n", type=int)
    p.add_argument("--aspect-ratio")
    p.add_argument("--resolution", choices=["1k", "2k"])
    p.add_argument("--response-format", choices=["url", "b64_json"])
    p.add_argument("--label", default="")
    p.add_argument("--output-dir")
    p.add_argument("--no-save", action="store_true")
    args = p.parse_args()

    if not args.image and not args.images:
        p.error("Pass --image (single) OR --images (multi).")
    if args.image and args.images:
        p.error("Use --image OR --images, not both.")

    image = to_image_obj(args.image) if args.image else None
    images = [to_image_obj(s) for s in args.images] if args.images else None
    mask = to_image_obj(args.mask) if args.mask else None

    if images and len(images) > 5:
        p.error("Max 5 images for multi-input edit.")

    cfg = load_config()
    if args.output_dir:
        cfg["GROK_OUTPUT_ROOT"] = args.output_dir

    try:
        resp = edit_image(
            prompt=args.prompt, image=image, images=images, mask=mask,
            model=args.model, n=args.n, aspect_ratio=args.aspect_ratio,
            resolution=args.resolution, response_format=args.response_format,
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

    out = make_output_dir(cfg, op="edit", label=args.label or "edit")
    saved = save_image_response(resp, out, label="edit")
    write_artifact_metadata(out, request_body={"prompt": args.prompt, "n_inputs": (1 if image else 0) + (len(images) if images else 0)}, response_body=resp, prompt=args.prompt)
    print(f"Saved {len(saved)} image(s) to: {out}")
    for p_ in saved:
        print(f"  {p_}")


if __name__ == "__main__":
    main()
