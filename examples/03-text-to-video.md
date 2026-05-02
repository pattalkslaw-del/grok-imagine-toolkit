# Example 03: Text-to-video (T2V)

A single video clip from a prompt only. No anchor image, no reference. The simplest video case.

## Use case

You need 5-15 seconds of video from a description. No specific character to lock; the look and identity are whatever the model produces. Good for environmental b-roll, abstract motion, atmospheric beats.

## Command

```bash
python3 scripts/generate_video.py \
  "A serene lake at sunrise with mist curling on the water. \
A small wooden rowboat tied to a weathered dock in the foreground. \
The camera slowly pushes forward toward the boat. \
Audio: gentle water lapping, distant bird calls, faint breeze." \
  --duration 8 \
  --resolution 720p \
  --aspect-ratio 16:9 \
  --label sunrise-lake
```

## What happens

1. Posts to `/v1/videos/generations` with the prompt (T2V mode is auto-detected: no `--image`, no `--reference-image`)
2. Receives `{"request_id": "..."}` immediately
3. Polls `GET /v1/videos/{request_id}` every 5 seconds
4. When `status: done`, parses `video.url` and `usage.cost_in_usd_ticks`
5. Downloads the MP4 via curl
6. Stages output and writes metadata

## Expected cost

`$0.07/sec × 8s = $0.56` for 720p.
`$0.05/sec × 8s = $0.40` for 480p.

## Expected wall-clock

8-second 720p clips finish in 40-60 seconds. The script polls every 5s; the default timeout is 600 seconds (10 minutes), well clear of any normal generation.

## When to iterate at 480p first

If you're not sure the prompt will produce what you want, iterate at 480p. Each attempt is `$0.40` instead of `$0.56`. Lock the prompt at 480p, then do the final at 720p.

```bash
# Iteration
python3 scripts/generate_video.py "..." --resolution 480p --label sunrise-lake-iter1
python3 scripts/generate_video.py "..." --resolution 480p --label sunrise-lake-iter2
# Final
python3 scripts/generate_video.py "..." --resolution 720p --label sunrise-lake-final
```

## Audio direction

Grok Imagine generates synchronized audio from the same prompt. **Direct it explicitly.** Without an audio cue, the model picks something — usually adequate, sometimes generic.

| Without audio direction | With audio direction |
|---|---|
| "A serene lake at sunrise" | "A serene lake at sunrise. Audio: gentle water lapping, distant bird calls" |

The skill's `references/prompting-tips.md` covers the Subject + Action + Camera + Lighting + Audio pattern in detail.

## Frame extraction

If you plan to chain this clip into a sequence (use it as the input for an I2V continuation), pass `--extract-frames`:

```bash
python3 scripts/generate_video.py "..." --resolution 720p --label sunrise-lake-final --extract-frames
```

This writes `first.jpg` and `last.jpg` next to the MP4, ready to feed into the next call.

## Submit-only mode (don't poll)

If you want to fire-and-forget multiple T2V calls and poll later (or in parallel from a different script), use `--no-poll`:

```bash
python3 scripts/generate_video.py "..." --no-poll
# Returns immediately with: request_id: 9c7e...
```

You can then poll manually:

```bash
curl -H "Authorization: Bearer $XAI_API_KEY" "https://api.x.ai/v1/videos/9c7e..."
```

## Common pitfalls

- Forgetting to raise the prompt's audio language — clip plays with generic audio
- Asking for too many actions in one clip — Grok handles ~1 action per second of clip well; "she walks in, orders coffee, sits down, opens her laptop" is too many beats for 8 seconds. Break it into multiple clips and chain via Example 04
- Using 16:9 aspect with `--resolution 480p` — produces 848×480, which is technically 16:9 but feels squarer than expected. Use 720p for 16:9 if framing matters
