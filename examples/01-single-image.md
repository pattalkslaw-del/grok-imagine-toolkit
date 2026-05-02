# Example 01: Single image generation

The simplest possible use of the skill — one prompt, one image.

## Use case

You need a hero image, an illustration, a chalkboard sign, an editorial photo. One subject, one shot.

## Command

```bash
python3 scripts/generate_image.py \
  "A hand-lettered chalkboard menu reading 'TODAY: lobster roll \$24' against a brick cafe wall, warm afternoon light, photorealistic" \
  --resolution 1k \
  --aspect-ratio 4:3 \
  --label cafe-chalkboard
```

## What happens

1. Posts to `/v1/images/generations` with the prompt, model `grok-imagine-image`, and the args above
2. Receives a JSON response with `data[0].url` and `usage.cost_in_usd_ticks`
3. Downloads the image via curl (Cloudflare blocks Python's default UA)
4. Writes a stamped folder to `$GROK_OUTPUT_ROOT/2026-05-02-{HHMMSS}-t2i-cafe-chalkboard/` containing:
   - `image.jpg` — the asset
   - `request.json` — exact request body
   - `response.json` — full response (URL, cost, moderation)
   - `prompt.txt` — the prompt as plain text
5. Appends a row to `$GROK_COST_LOG`

## Expected cost

`$0.020` for a single standard image. Pro model: `$0.070`.

## When to bump to image-pro

- Hero images for a website or campaign
- Anchor frames for video sequences (R2V references, hyperframe waypoints)
- Anything where 3.5x the cost is justified by the difference in fidelity

```bash
python3 scripts/generate_image.py \
  "A hand-lettered chalkboard menu..." \
  --model grok-imagine-image-pro \
  --resolution 2k \
  --aspect-ratio 4:3 \
  --label cafe-chalkboard-hero
```

`$0.070` per image. 2k resolution. Notably better text rendering and lighting.

## When to use n=4

Variation menus. "Show me four versions of this so I can pick."

```bash
python3 scripts/generate_image.py \
  "A hand-lettered chalkboard menu..." \
  --n 4 \
  --label cafe-variations
```

`$0.080` total for four images in one request. The four images share architectural identity but vary in pose, framing, and detail. Pick the best, throw away the rest, or feed your favorite back through I2V/R2V for animation.

## Common pitfalls

- **Forgot to escape the `$`** in shell prompts containing prices: `\$24` not `$24`
- **Aspect ratio mismatch** — check `references/api-shapes.md` for the full list of supported ratios. Anything outside the list silently falls back to `auto`
- **Asking for body text in the image** — keep image text to short signs, labels, headlines. For body copy, use the graphic fall-back pattern (Example 06)
