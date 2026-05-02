# Example 05: Hyperframe — 30-second multi-clip piece

A continuous 30-second video stitched from four 8-second clips, with character lock maintained through I2V chaining and an R2V anchor.

## Use case

Anything longer than 15 seconds. Grok Imagine caps single clips at 15s; the hyperframe pattern composes multiple clips into one piece. This example is 30 seconds; the pattern scales to several minutes (with re-anchoring every 6 clips to prevent drift).

## The shot list as JSON

The skill takes a `beats.json` file describing the piece. Author this manually for short pieces; for longer or more elaborate pieces, build the shot list with whatever planning tool you prefer and convert it to the JSON shape shown below.

```json
{
  "anchor_prompt": "A woman in her thirties with copper-red braided hair tied loose, dark olive field jacket over a white t-shirt and dark jeans, standing in a small European plaza on cobblestones, late afternoon golden-hour light, photorealistic editorial portrait, 16:9 framing",
  "ambient": "soft cafe chatter at a distance, gentle breeze, footsteps on cobblestone",
  "beats": [
    {
      "prompt": "She walks slowly forward toward the camera. Eye-level shot, three meters back. The camera holds steady as she approaches.",
      "duration": 8
    },
    {
      "prompt": "She stops and turns her head to look at a stone fountain on her right. The camera holds; her gaze moves.",
      "duration": 8
    },
    {
      "prompt": "She crosses to the fountain and sits on its low stone edge, looking down at the water. Slow steady pace.",
      "duration": 8
    },
    {
      "prompt": "She looks up at the camera and smiles softly. Close-medium shot. The light catches her face.",
      "duration": 6
    }
  ]
}
```

Save as `~/work/plaza-walk.json`.

## Command

```bash
python3 scripts/hyperframe.py \
  --beats ~/work/plaza-walk.json \
  --label plaza-walk \
  --resolution 720p \
  --aspect-ratio 16:9 \
  --crossfade 0.5
```

## What happens

1. **Cost preflight.** The script estimates `1 anchor (image-pro) + 4 video clips (720p)` = `$0.07 + 4 × $0.56 = $2.31` and asks for confirmation.
2. **Anchor.** Generates the establishing image with `grok-imagine-image-pro` from `anchor_prompt`. Saves as `anchor.jpg`.
3. **Beat 1 (R2V).** First clip uses R2V from the anchor image. The clip starts with a fresh composition that matches the anchor's identity and style.
4. **Beats 2-4 (I2V chain).** Each subsequent clip uses I2V from the previous clip's last frame. Identity carries through the cuts; pose, framing, and incidental detail flow continuously.
5. **Re-anchor (none for 4 beats).** With `--reanchor-every 6` (default), no re-anchor needed at this length. For longer pieces, every 6th beat would generate a fresh R2V from the anchor to refresh identity.
6. **Frame extraction.** After each clip, `last.jpg` is extracted as the input for the next.
7. **Stitch.** Calls `stitch.py` with `--crossfade 0.5` to assemble the four clips with half-second crossfades.
8. **Manifest.** Writes `manifest.json` with every prompt, every cost, every request_id, every artifact path. Reproducible from this file alone.

## Output

```
~/grok-imagine-output/2026-05-02-{HHMMSS}-hyperframe-plaza-walk/
├── anchor.jpg
├── clip-01.first.jpg
├── clip-01.last.jpg
├── clip-01.mp4
├── clip-02.first.jpg
├── clip-02.last.jpg
├── clip-02.mp4
├── clip-03.first.jpg
├── clip-03.last.jpg
├── clip-03.mp4
├── clip-04.first.jpg
├── clip-04.last.jpg
├── clip-04.mp4
├── manifest.json
└── output.mp4    <- the stitched 30-second piece
```

## Expected cost

| Component | Cost |
|---|---|
| 1 × image-pro anchor | $0.070 |
| 1 × R2V 8s 720p | $0.562 |
| 3 × I2V 8s/8s/6s 720p | $1.682 |
| **Total** | **$2.31** |

## Expected wall-clock

- Anchor: ~10 seconds
- Each video clip: ~40-60 seconds (720p 8s)
- Stitching: ~5 seconds
- **Total: ~4 minutes serial**

For 60-second or longer pieces with parallel R2V re-anchors, the runtime ratio improves significantly. See `references/hyperframe-patterns.md` for the concurrency analysis.

## Resuming an interrupted run

If anything fails partway through (network blip, moderation filter on one beat, manual interrupt), resume from the existing output dir:

```bash
python3 scripts/hyperframe.py \
  --beats ~/work/plaza-walk.json \
  --resume ~/grok-imagine-output/{...}-hyperframe-plaza-walk/
```

The script reads the manifest, identifies completed clips, and continues from the next pending beat.

## Audio strategy

Two paths, picked at the prompt-authoring stage:

### Option A: ambient bed in every prompt (easy)

The `ambient` field in beats.json gets appended as `Audio: {ambient}.` to every clip's prompt. This produces reasonable audio continuity across cuts without extra work.

### Option B: silent generate, dub later (polished)

For pieces where editorial audio control matters (voiceover-driven narratives, music beds, branded sound design), it's cheaper and faster to:

1. Generate clips silent — there's no `--mute` flag in the API, but you can ffmpeg `-an` on the output to strip audio
2. Stitch silent clips
3. Add voiceover and music beds in a single post pass with the audio tool of your choice

For most production work, Option B is what wins. Imagine audio is fine for first drafts; finished pieces almost always benefit from intentional sound design.

## Common pitfalls

- **Vague beat prompts.** "She walks around the plaza" produces a clip that wanders. "She walks slowly forward toward the camera; the camera holds three meters back" produces an 8-second beat with clear structure
- **Skipping the anchor.** Tempting to start straight with I2V from a stock photo, but generating an anchor with image-pro gives you a reproducible identity and full control. For `$0.07` extra, take the anchor
- **Not reviewing the manifest.** If a piece comes out wrong, the manifest tells you which beat failed and why. Read it before regenerating
- **Asking for crossfades on a piece with hard scene changes.** Crossfades are for continuous narrative; if your beats are episodic ("Day 1", "Day 2", "Day 3"), use hard cuts (`--crossfade 0`)
