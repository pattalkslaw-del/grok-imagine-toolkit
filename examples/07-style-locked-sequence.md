# Example 07: Style-locked sequence — the same character in four scenes

You have a known character (a generated identity, not a real person). You want to show them in four distinct scenes, each its own short clip, with identity holding across all four. This is the **R2V cross-call pattern** — the strongest character lock available across separate API calls.

Compare to Example 05 (hyperframe), which produces a *continuous* multi-clip piece via I2V chain. This example produces *separate* clips that share a character but are otherwise independent.

## Use case

- An "about us" page with the same firm partner shown in four contexts (office, courtroom, signing documents, walking into a building)
- A documentary-style series of vignettes featuring the same protagonist
- An ad campaign with multiple short cuts of the same brand character
- A product demo where the same person uses the product in different settings

## The pattern

1. Generate one anchor image with `grok-imagine-image-pro` — this is the visual identity
2. For each scene, run a separate R2V video gen with the anchor as `--reference-image`
3. Each clip is independent (different scene, different action) but the character matches the anchor across all four

## Step 1: anchor

```bash
python3 scripts/generate_image.py \
  "A man in his fifties, salt-and-pepper hair cut short, dark navy suit, light blue dress shirt, no tie, standing in a neutral interior setting. Warm professional editorial portrait. Photorealistic. 16:9 framing." \
  --model grok-imagine-image-pro \
  --resolution 1k \
  --aspect-ratio 16:9 \
  --label professional-portrait-anchor
```

`$0.070`. Output: `~/grok-imagine-output/{...}-t2i-professional-portrait-anchor/image.jpg`.

Inspect the result. If it's not what you want, regenerate. The anchor sets identity for everything downstream — getting it right at this step saves money later.

## Step 2: four clips, all R2V from the same anchor

```bash
ANCHOR=~/grok-imagine-output/{...}-t2i-professional-portrait-anchor/image.jpg

# Scene A: in his office
python3 scripts/generate_video.py \
  "He sits at a wooden desk in his law office, looking down at an open document, then looks up at the camera and gives a small confident nod. Late afternoon golden light through tall windows. Audio: faint city ambience, gentle paper rustle." \
  --reference-image "$ANCHOR" \
  --duration 6 \
  --resolution 720p \
  --aspect-ratio 16:9 \
  --label scene-office

# Scene B: walking into a courthouse
python3 scripts/generate_video.py \
  "He walks up the limestone steps of an old county courthouse, briefcase in hand, looking determined. Camera tracks beside him. Bright morning light. Audio: footsteps on stone, distant city sounds." \
  --reference-image "$ANCHOR" \
  --duration 6 \
  --resolution 720p \
  --aspect-ratio 16:9 \
  --label scene-courthouse

# Scene C: at a conference table
python3 scripts/generate_video.py \
  "He sits across from a client at a polished wooden conference table, gestures gently with his right hand while explaining something. Soft overcast window light. Audio: muted office tones, soft breathing." \
  --reference-image "$ANCHOR" \
  --duration 6 \
  --resolution 720p \
  --aspect-ratio 16:9 \
  --label scene-conference

# Scene D: closing shot
python3 scripts/generate_video.py \
  "He stands with his hands in his pockets, looking out a tall window over a small midwestern town at dusk, contemplative. Warm interior light from behind. Audio: distant evening crickets, soft AC hum." \
  --reference-image "$ANCHOR" \
  --duration 6 \
  --resolution 720p \
  --aspect-ratio 16:9 \
  --label scene-dusk
```

Each clip is `$0.07/sec × 6s + ~$0.002 input = $0.422`. Four clips: `$1.69`. Plus the anchor: **`$1.76` total** for the full sequence.

## Step 3: stitch into a single piece

If you want the four clips assembled into one video (e.g. for a 24-second "about us" piece):

```bash
python3 scripts/stitch.py \
  ~/grok-imagine-output/{...}-r2v-scene-office/video.mp4 \
  ~/grok-imagine-output/{...}-r2v-scene-courthouse/video.mp4 \
  ~/grok-imagine-output/{...}-r2v-scene-conference/video.mp4 \
  ~/grok-imagine-output/{...}-r2v-scene-dusk/video.mp4 \
  --output ~/work/professional-portrait-sequence.mp4 \
  --crossfade 0.4
```

Crossfades work well here because the sequence is meant to feel like a montage. For hard documentary cuts, drop `--crossfade 0`.

## Why R2V cross-call rather than I2V chain

Both can produce "same character in four scenes." The differences:

| Approach | Continuity feel | Identity lock |
|---|---|---|
| **R2V cross-call** (this example) | Episodic, distinct scenes | Strongest cross-call lock; identity holds even when scenes/moods diverge |
| **I2V chain** (Example 05) | Continuous narrative; cuts feel connected | Strong sequential lock; drifts on episodic content because each cut needs a related last frame |

If your scenes are deliberately distinct (different settings, different actions, different moods), R2V is the right call. If your scenes are a continuous story, I2V chain is.

## When to combine R2V + I2V

For longer pieces with both episodic structure AND multi-beat scenes inside each episode: use R2V to start each episode (re-anchor identity) and I2V chain within the episode. `hyperframe.py --reanchor-every N` automates this — the default re-anchors every 6 beats. Tighter re-anchoring (`--reanchor-every 4`) for character-critical work; looser (`--reanchor-every 8`) for atmospheric work.

## Common pitfalls

- **Different aspect ratios across scenes.** The anchor was 16:9, all clips should be 16:9. Mixing aspect ratios degrades identity transfer
- **Using a stock photo as the anchor.** The model identity-locks better on its own generated outputs than on photos of real people. If you start with a stock photo, generate a "stylized portrait of this person" with multi-image edit first, then use that as the R2V anchor for video
- **Reference image at lower resolution than the target video.** 1k anchor for 720p video is fine. 720p source upscaled to 1k anchor for 720p video produces worse results than going 1k from the start
- **Asking for too much variation in the anchor's pose.** The anchor is a *pose-neutral identity reference*. If the anchor is mid-gesture, every R2V clip will inherit that gesture energy. Use a calm, frontal anchor unless you specifically want every scene to start with that pose
