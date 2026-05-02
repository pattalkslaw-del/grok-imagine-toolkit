# Hyperframe — video longer than 15 seconds

Grok Imagine caps any single clip at 15 seconds. The hyperframe pattern composes multiple clips into one piece by chaining I2V calls and stitching with ffmpeg. This document is the deep reference for `scripts/hyperframe.py`.

---

## The pattern in three sentences

1. Generate keyframe images for each beat of the piece (one keyframe per 5-15 second segment).
2. Generate I2V clips that bridge between keyframes — each clip's input is the previous beat's keyframe (or the previous clip's last frame); the prompt drives action toward the next beat.
3. Stitch the clips with ffmpeg into a single output, with optional crossfades or hard cuts as the editor chooses.

---

## Why I2V chain rather than R2V across the chain

Both work. The difference matters:

- **R2V across the chain:** every clip is generated with the same `reference_images: [anchor]`. Strong identity lock. But each clip's *first frame* is freshly invented from the prompt, so cuts have visible jumps in pose, framing, and incidental detail.
- **I2V chain:** every clip's first frame is conditioned on the previous clip's end. Pose, framing, and detail carry through cuts. Identity drifts slightly faster than R2V, so re-anchor every 6-8 hops.

**The hybrid pattern (default in `hyperframe.py`) uses both:**
1. R2V for the establishing shot (locks identity early)
2. I2V chain for the bulk of the piece (carries continuity through cuts)
3. R2V re-anchor every 6 hops (refreshes identity before drift becomes visible)

---

## Anatomy of a 30-second hyperframe piece

```
TIME    OPERATION                                 INPUT             OUTPUT
0-8s    R2V from anchor                           anchor.jpg        clip1.mp4
8-16s   I2V from clip1 last frame                 clip1.last.jpg    clip2.mp4
16-24s  I2V from clip2 last frame                 clip2.last.jpg    clip3.mp4
24-30s  I2V from clip3 last frame (6-sec clip)    clip3.last.jpg    clip4.mp4
        Stitch: clip1 + clip2 + clip3 + clip4 → output.mp4
```

Three I2V hops from anchor — well within the 6-hop drift threshold. No re-anchor needed at this length.

For 60-second pieces, plan a re-anchor at the 32-second mark:

```
TIME      OPERATION
0-8s      R2V from anchor                  → clip1.mp4
8-16s     I2V from clip1 last              → clip2.mp4
16-24s    I2V from clip2 last              → clip3.mp4
24-32s    I2V from clip3 last              → clip4.mp4   (4 hops; near drift threshold)
32-40s    R2V re-anchor from anchor        → clip5.mp4   (REFRESH IDENTITY)
40-48s    I2V from clip5 last              → clip6.mp4
48-56s    I2V from clip6 last              → clip7.mp4
56-60s    I2V from clip7 last (4-sec clip) → clip8.mp4
          Stitch: all 8 clips → output.mp4
```

---

## Concurrency

Each video gen takes 20-90 seconds wall-clock. A serial 60-second piece (8 clips) takes 8 × 60s = ~8 minutes wall-clock.

**However:** R2V calls from the same anchor are independent of each other and can run concurrently. I2V chain calls are sequential by definition (each needs the previous result).

The optimal pipeline:
1. **Phase 1, parallel:** R2V the establishing shot AND any re-anchor shots (clips 1, 5, 9 in a 90-second piece). All can fire at once via `asyncio.gather`.
2. **Phase 2, partially parallel:** Each segment between R2V anchors is a sequential I2V chain. Different segments run in parallel.

For an 8-clip 60-second piece with one re-anchor at clip 5:
- Serial: ~8 minutes
- Optimal: ~5 minutes (clip1 and clip5 parallel; clips 2-3-4 chain serial; clips 6-7-8 chain serial; the two segments run in parallel after their anchors complete)

`hyperframe.py --concurrent` enables this. Skip it for predictable cost-per-minute pacing; turn it on when wall-clock matters.

---

## Audio in hyperframe

Each clip's audio is generated independently from its prompt. Without explicit audio direction across all clips, expect audio discontinuity at every cut.

**Two options:**

### Option A: Consistent ambient bed in every prompt

Every clip's prompt includes the same ambient bed (e.g. "soft cafe chatter, distant footsteps on cobblestone, gentle breeze"). The model generates similar audio for each clip; the cut audio is reasonably consistent.

This is the default in `hyperframe.py` — the skill prompts the user (or the property skill) for an `ambient_bed` parameter and prepends it to every clip's prompt.

### Option B: Strip audio, dub later

Generate clips with `--mute` (post-process: strip audio with ffmpeg). Stitch silent clips. Add voiceover, music, and SFX in a single post pass with whatever TTS, narration, and audio tooling you prefer.

For polished pieces, Option B usually wins. The cost of generating Imagine audio that gets thrown away is negligible (audio is included in the per-second video price), but the editorial control is much higher.

---

## Stitching

`scripts/stitch.py` handles ffmpeg concat with the staging discipline codified in session memory:

1. Copies all clips to `$GROK_STAGING/{run_id}/` (snap-ffmpeg can read this path; can NOT read `/mnt/claude-workspace/`)
2. Writes a concat list file
3. Runs `ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp4`
4. If clip codecs don't match (sometimes happens between separate Imagine generations), falls back to re-encode: `-c:v libx264 -c:a aac`
5. Copies final to `$GROK_OUTPUT_ROOT/{run_id}/output.mp4`

### Crossfade option

Default is hard cut. Enable crossfade with `--crossfade DURATION` (in seconds; 0.3-0.5 is standard for prose-like pieces):

```
ffmpeg -i clip1.mp4 -i clip2.mp4 -filter_complex \
  "[0:v]fade=t=out:st=4.5:d=0.5[v0]; \
   [1:v]fade=t=in:st=0:d=0.5[v1]; \
   [v0][v1]concat=n=2:v=1:a=0[v]" \
  -map "[v]" out.mp4
```

The skill builds this filtergraph dynamically based on the number of clips. Audio is concat-only (no crossfade on audio) since Imagine audio at clip boundaries is already short.

---

## Manifest

Every hyperframe run writes a `manifest.json` to its output folder:

```json
{
  "run_id": "2026-05-02-153012-plaza-walk",
  "started_at": "2026-05-02T15:30:12Z",
  "finished_at": "2026-05-02T15:38:47Z",
  "anchor_image": "anchor.jpg",
  "anchor_prompt": "...",
  "anchor_cost_ticks": 700000000,
  "clips": [
    {
      "n": 1,
      "type": "R2V",
      "input_image": "anchor.jpg",
      "prompt": "She walks slowly forward...",
      "duration": 8,
      "resolution": "720p",
      "request_id": "...",
      "output_url": "https://vidgen.x.ai/...",
      "local_path": "clip1.mp4",
      "first_frame": "clip1.first.jpg",
      "last_frame": "clip1.last.jpg",
      "cost_ticks": 5600000000,
      "respect_moderation": true
    },
    {"n": 2, "type": "I2V", "input_image": "clip1.last.jpg", "...": "..."},
    "..."
  ],
  "stitch": {
    "method": "concat",
    "crossfade_duration": 0.5,
    "output_path": "output.mp4",
    "duration": 30.0
  },
  "total_cost_ticks": 25200000000,
  "total_cost_usd": 2.52
}
```

A future caller can:
- Reproduce any individual clip
- Audit total cost
- Re-run a single beat without re-rendering the whole piece
- Trace any quality issue back to the prompt that caused it
- Show the cost-per-second to a client/stakeholder

---

## Cost discipline for hyperframe runs

A 30-second 720p piece runs ~$2.50. A 60-second runs ~$5.00. A 5-minute runs ~$25.

The skill prints a cost estimate before kicking off any hyperframe run >$1.00 and asks for confirmation:

```
hyperframe.py: Estimated cost for this run is $4.27.
  - 5 keyframes (image-pro): $0.35
  - 7 clips × 8s × 720p: $3.92
Continue? [y/N]
```

Skip the prompt with `--no-confirm` for automated pipelines.

---

## When the anchor changes mid-run

You can interrupt a hyperframe run, swap the anchor, and resume. The skill writes the manifest after every clip, so:

```bash
# First half with anchor1
hyperframe.py --anchor-image anchor1.jpg --beats beats1.json --output ./run1

# Inspect run1, decide to swap anchor for the second half
hyperframe.py --resume ./run1 --anchor-image anchor2.jpg --beats beats2.json
```

The resume reads the existing manifest, picks up where it left off, treats the new anchor as a hard re-anchor (R2V from anchor2.jpg), and continues the chain.

---

## Failure modes and recovery

### One clip fails moderation in the middle

`hyperframe.py` detects `respect_moderation: false` and offers three options:
1. **Re-prompt:** edit the failed clip's prompt and retry
2. **Skip:** mark the beat empty, stitch around it (creates a hard cut)
3. **Abort:** keep what's done, abandon the rest

### Polling timeout

Default `GROK_VID_POLL_TIMEOUT=600` seconds (10 minutes). If a clip hits timeout, the skill saves the request_id and tries one final poll on resume. xAI sometimes completes long-queued requests after the standard window.

### CDN URL expires before stitch

Defensive download — every clip is pulled to `$GROK_STAGING` immediately after generation. Stitching reads from local files, never from the temporary URL. URLs survive at least an hour in practice but the skill doesn't depend on it.

---

## Hyperframe runs are reproducible from the manifest

A future session can reconstruct exactly what happened from `manifest.json` alone — every prompt, every cost, every input. Check the manifest into git or archive it next to the output if the work matters.
