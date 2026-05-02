# Character consistency on Grok Imagine

Tested live, May 2026, against `grok-imagine-image`, `grok-imagine-image-pro`, and `grok-imagine-video`. Test budget: $1.20. Test outputs preserved locally during verification.

**Bottom line: character consistency is production-ready when the right pattern is matched to the use case.** The four documented patterns below are not interchangeable — each has a distinct lock strength and a distinct best-fit use case.

---

## The four patterns, ranked by lock strength

### 1. Same-call batch (`n=4`) — strongest within a single request

```json
{
  "model": "grok-imagine-image",
  "prompt": "A woman in her thirties with copper-red braided hair, dark olive field jacket, white t-shirt, sunlit cobblestone plaza. Show four poses of the same woman.",
  "n": 4
}
```

The model produces four images that share architectural-level identity within a single inference. Most variations are recognizably the same person; outliers occasionally drift on facial proportions.

**When to use:** variation menus, "show me four versions to pick from," single-shot exploration.
**Limitation:** identity does not carry across separate API calls — only within the one request that generated the batch.

### 2. R2V (`reference_images`) — strongest cross-call lock for video

```json
{
  "model": "grok-imagine-video",
  "prompt": "She walks slowly forward toward the camera",
  "reference_images": [{"url": "https://anchor.jpg"}],
  "duration": 5
}
```

Pass the same `reference_images` array across multiple separate `/v1/videos/generations` calls. Each call generates a fresh scene, but the character matches the reference image's identity, hair, and clothing.

Verified: two separate R2V calls with the same reference produced clips where the character was unmistakably the same person across both.

**When to use:** documentary-style cuts of the same character across distinct scenes; multi-shot sequences where each shot is a different action.

**Limitation:** R2V does not start the clip from the reference image's pose. The reference is a style/identity guide, not a first frame. If you need the clip to *start* at a specific pose, use I2V instead.

### 3. I2V chain — strongest for continuous narrative

```python
clip_a = generate_video(image_url=keyframe_url, prompt="She walks forward...")
last_frame = extract_last_frame(clip_a.video_url)
clip_b = generate_video(image_url=last_frame_data_uri, prompt="She sits on a bench...")
```

The keyframe becomes the first frame conditioning of clip A. Clip A's last frame becomes the first frame conditioning of clip B. Identity carries through the cut because each clip's start was conditioned on the previous clip's end.

**Caveat learned in testing:** I2V is conditioning, not pixel-copying. Clip A's first frame is *interpreted* from the keyframe, not literally identical to it. The character starts very close to the keyframe but with sub-pixel-level differences. Across one cut this is invisible. Across many cuts in a chain, drift accumulates — the skill caps hyperframe chains at 6-8 segments before re-anchoring with R2V.

**When to use:** continuous narrative across cuts; hyperframe-length pieces; "the same person doing one thing, then the next thing."

### 4. Multi-image edit (`<IMAGE_0>`, `<IMAGE_1>`)

```json
{
  "model": "grok-imagine-image",
  "prompt": "Show the woman from <IMAGE_0> in the setting of <IMAGE_1>. Preserve her face, hair, jacket exactly.",
  "images": [
    {"url": "https://character-anchor.jpg"},
    {"url": "https://different-scene.jpg"}
  ]
}
```

Strong identity lock when the prompt explicitly says "preserve" and references the identity image by tag. The non-identity image can be a setting, a pose, a wardrobe — anything you want the character composited into.

**When to use:** "this person, that scene." Compositing a known character into a different setting, posture, or wardrobe.

**Caveat from testing:** if `<IMAGE_1>` doesn't contain a clear pose (e.g. it's an empty scene), the model uses it as a setting reference, not a pose reference. To force pose transfer, `<IMAGE_1>` must contain a person in the target pose.

---

## Decision flow

```
  Single anchor + 2-4 separate clips of same character?  →  R2V
  Continuous narrative, multi-cut, same character?       →  I2V chain (hyperframe.py)
  Place known character in a different scene/pose?       →  Multi-image edit
  Need a menu of variations to pick from?                →  n=4 batch
```

When in doubt: R2V for short sequences, I2V chain for long ones.

---

## Limits and failure modes

### Drift accumulates in long I2V chains

Each I2V hop interprets rather than copies. After 6-8 hops, identity may noticeably drift. The skill's `hyperframe.py` re-anchors every 6 hops by injecting an R2V refresh — generates a fresh keyframe via R2V using the original anchor, then continues the I2V chain from there. Configurable via `--reanchor-every N` flag, default 6.

### Background and incidental detail drift faster than character

Even when the woman's face holds, the plaza behind her shifts: trees move, fountain moves, foreground figures change. This is normal and usually invisible during playback. If background continuity matters, lock the background separately:
1. Generate a "set" image with R2V using a different reference for the location
2. Composite character into set with multi-image edit
3. Animate the composite with I2V

This is two-stage and roughly doubles cost, but gives Hollywood-grade location continuity.

### n=4 batch drifts on outliers

A typical n=4 batch has 3 of 4 reading as the same person and 1 outlier with slightly different facial proportions. If you need every variation to be ironclad, run n=4 and discard outliers, or batch via R2V (each variation is a separate call with the same reference).

### Cross-resolution identity

Identity holds across resolution changes (1k anchor used as I2V input for 720p video) but the model upscales the reference internally. For best identity transfer, anchor and target should use compatible resolutions: 1k anchor for 480p video, 2k anchor for 720p video.

### Things that actively break consistency

- Mixing T2V and I2V/R2V in the same sequence — identity will not carry from a T2V clip to a subsequent I2V clip even with the same prompt
- Changing aspect ratio mid-chain (e.g. 16:9 anchor, then 9:16 clip) — recomposes the frame and shifts identity
- Editing the anchor before re-using it — every edit is an interpretation; if the anchor needs an edit, re-anchor with a fresh R2V call

---

## Test methodology — for re-verification

The four-test suite in `tests/test-edges.sh` re-runs all four patterns whenever you run the suite. Compare against the May 2026 reference outputs preserved in `tests/reference-outputs/` (when present). If new model versions degrade consistency, the test will surface it.

Cost per re-run: ~$1.20.

---

## When Grok Imagine isn't the right tool for character work

Honest disclosure: for character-driven narrative video where identity must lock with zero drift across many minutes, Grok Imagine is competitive but not best-in-class. As of May 2026, tools optimized for cameo/character lock include:
- **Runway Gen-3 Reference** — strong identity lock, more expensive
- **MiniMax char-consistent video** — purpose-built for this
- **OpenAI Sora cameo** — ironclad lock, limited access

Grok Imagine is the right call when:
- Total piece is under 60 seconds
- Character drift of a few percent across cuts is tolerable
- Cost matters (Imagine is significantly cheaper than the alternatives)
- Speed matters (Imagine generates faster than Runway or Sora)
- The character is a generated identity (not a real person)

For minute-plus character pieces or pieces where the same identity must hold across hours of cut footage, mention the alternatives to the user and let them decide.
