# Example 04: Image-to-video (I2V)

Animate a still image. The image conditions the start of the generated motion — the clip "begins" with something close to your input image and develops from there.

## Use case

- Bring a generated keyframe to life
- Animate a photo or illustration
- Create the first segment of a continuous narrative (the foundation of hyperframe chains)
- Produce a clip that *starts* at a known visual state

## Critical distinction: I2V is conditioning, not pixel-copying

The input image becomes the **starting point of the motion**, not literally frame zero. The model interprets the input — it gets very close, but it's not pixel-identical. Across one cut this is invisible; across many cuts in a long chain, drift accumulates. (See `references/character-consistency.md` for the four-pattern test results.)

If you need the clip to *literally begin* with the exact pixels of the input image, you have to layer the input as frame 0 in post (ffmpeg). The skill doesn't do that automatically because in 95% of cases I2V conditioning is what you actually want.

## Command

```bash
python3 scripts/generate_video.py \
  "She turns her head slowly toward the camera and smiles softly. \
Audio: distant cafe chatter, gentle breeze." \
  --image ~/work/keyframe.jpg \
  --duration 8 \
  --resolution 720p \
  --aspect-ratio 16:9 \
  --label keyframe-smile \
  --extract-frames
```

## What happens

1. Local file is auto-encoded as base64 data URI (`data:image/jpeg;base64,...`)
2. Posts to `/v1/videos/generations` with `image: {"url": "data:..."}`
3. Mode is detected as I2V because `image` is present and `reference_images` is absent
4. Polls until done, downloads the MP4
5. With `--extract-frames`, also extracts `first.jpg` and `last.jpg` next to the MP4

## Expected cost

`$0.07/sec × 8s + ~$0.002 input = $0.562` for 720p.

## Why `--extract-frames` matters

If you're going to chain this clip into another I2V call, you need its last frame. The skill uses the snap-friendly `-sseof -0.5` ffmpeg seek to grab the last frame without depending on `ffprobe` (which is at the non-obvious path `/snap/bin/ffmpeg.ffprobe` on a server with snap-installed ffmpeg — see `references/known-quirks.md`).

```bash
# Chain: clip A's last frame becomes clip B's input
python3 scripts/generate_video.py \
  "She stands up from the bench and walks toward the fountain. \
Audio: distant cafe chatter, footsteps on cobblestone." \
  --image ~/grok-imagine-output/{...}-i2v-keyframe-smile/last.jpg \
  --duration 8 \
  --resolution 720p \
  --label clip-b-walk \
  --extract-frames
```

This is the **I2V chain pattern** — the foundation of `hyperframe.py` (Example 05).

## I2V vs R2V — which to use

| Goal | Mode | Why |
|---|---|---|
| Continue a continuous scene/action | I2V | Last frame of previous clip carries through the cut |
| Show the same character in a new scene | R2V | Fresh scene generated; reference locks identity |
| Place a character in a specific starting pose | I2V | Image conditions the starting frame |
| Generate variation on a style | R2V | Reference is style guide, clip composes freshly |

## Common pitfalls

- Using R2V (`--reference-image`) when you wanted I2V (`--image`) — the clip won't start at your input image; it'll start at a freshly-invented composition that matches the reference's style
- Chaining more than 6-8 I2V hops without re-anchoring — identity drift accumulates. `hyperframe.py` re-anchors with R2V every 6 hops by default
- Mixing `--image` and `--reference-image` — script rejects the combination
- 480p input keyframe used for 720p I2V — the model upscales internally; for best identity transfer, match input to target resolution
