---
name: grok-imagine
description: Generate or edit images and videos via the xAI Grok Imagine API. Covers text-to-image, image edits (single + multi-reference + mask), text-to-video, image-to-video, reference-to-video, video edits, and video extends. Includes hyperframe chaining for video longer than 15 seconds, four documented patterns for character consistency across cuts, and graphic fall-back compositing for text-heavy images. Use whenever a caller needs to actually produce assets via Grok Imagine. Pair with shot-list authoring tools and property-specific style skills as appropriate. Triggers: Grok Imagine, grok-imagine-image, grok-imagine-video, xAI image, xAI video, character consistency, image-to-video, video extend, hyperframe, multi-clip video, video stitching, generate image with Grok, generate video with Grok.
---

# Grok Imagine API

Execute image and video generation against xAI. The skill is the **execution layer** — call the API, poll, stitch, log costs. Pair with whatever shot-list authoring, brand-constraint, and voice/tone tooling you prefer.

| Field | Value |
|-------|-------|
| Image gen endpoint | `POST https://api.x.ai/v1/images/generations` |
| Image edit endpoint | `POST https://api.x.ai/v1/images/edits` |
| Video gen endpoint | `POST https://api.x.ai/v1/videos/generations` |
| Video edit endpoint | `POST https://api.x.ai/v1/videos/edits` |
| Video extend endpoint | `POST https://api.x.ai/v1/videos/extensions` |
| Video poll endpoint | `GET  https://api.x.ai/v1/videos/{request_id}` |
| Auth header | `Authorization: Bearer $XAI_API_KEY` |
| Docs | https://docs.x.ai/developers/model-capabilities/images/generation |
| Docs MCP (no auth) | https://docs.x.ai/api/mcp |

> **Maintenance note:** xAI ships rapidly. Run the edge test suite (`tests/test-edges.sh`) every 60 days to catch breaking changes. Last verified: May 2026 against `grok-imagine-image`, `grok-imagine-image-pro`, `grok-imagine-video`.

---

## Configuration — set these once, never hardcode

The skill reads defaults from environment variables. Copy `.config.example` to `~/.grok-imagine.env`, edit, then `source ~/.grok-imagine.env` (or load it however you load envs). Every default is overridable per call. See `README.md` for the full configuration guide.

```bash
# Required
XAI_API_KEY=xai-...                                  # from console.x.ai

# Image defaults (overridable per call)
GROK_IMG_MODEL=grok-imagine-image                    # or grok-imagine-image-pro
GROK_IMG_RESOLUTION=1k                               # 1k or 2k
GROK_IMG_ASPECT_RATIO=auto                           # 1:1, 16:9, 9:16, 4:3, 3:4, 3:2, 2:3, 1:2, 2:1, 9:19.5, 19.5:9, 9:20, 20:9, auto
GROK_IMG_RESPONSE_FORMAT=url                         # or b64_json
GROK_IMG_N=1                                         # 1-10

# Video defaults (overridable per call)
GROK_VID_MODEL=grok-imagine-video
GROK_VID_RESOLUTION=720p                             # 480p (cheaper, faster) or 720p (production)
GROK_VID_DURATION=8                                  # 1-15 seconds
GROK_VID_ASPECT_RATIO=16:9                           # 1:1, 16:9, 9:16, 4:3, 3:4, 3:2, 2:3
GROK_VID_POLL_INTERVAL=5                             # seconds between status checks
GROK_VID_POLL_TIMEOUT=600                            # max wait before timeout

# Output discipline
GROK_OUTPUT_ROOT=~/grok-imagine-output   # where final assets land
GROK_STAGING=~/tmp/grok-imagine-staging  # intermediate work; ffmpeg-snap accessible
GROK_COST_LOG=~/log/grok-imagine-cost.log
```

---

## Model selection

| Scenario | Model | Why |
|----------|-------|-----|
| Standard images, drafts, iteration | `grok-imagine-image` | $0.02/image, 8000-char prompt limit, fast |
| Premium quality anchors, hero shots, keyframes | `grok-imagine-image-pro` | $0.07/image, 10000-char prompt limit, higher fidelity |
| All video work | `grok-imagine-video` | Only video model; $0.05/sec at 480p, $0.07/sec at 720p |

Image-pro is 3.5× the cost of standard — use it for keyframes that anchor a sequence (R2V references, hyperframe waypoints), not for routine generation.

---

## Pricing — known rates as of May 2026

All costs return in `usage.cost_in_usd_ticks` where `1 USD = 10^10 ticks`. Convert: `cost_usd = cost_in_usd_ticks / 1e10`.

| Operation | Cost |
|-----------|------|
| Image generation (`grok-imagine-image`) | $0.020 / image |
| Image generation (`grok-imagine-image-pro`) | $0.070 / image |
| Image edit (single input) | ~$0.022 / image ($0.02 base + $0.002 per input) |
| Image edit (two inputs) | ~$0.024 / image ($0.02 base + $0.002 × 2 inputs) |
| Video generation, 480p | $0.05 / second of output |
| Video generation, 720p | $0.07 / second of output |
| Video I2V/R2V additional | ~$0.002 per input image |
| Video edit / extend input | ~$0.01 per input video |

Verified live, May 2026. Recheck via `tests/test-edges.sh` if costs look wrong in the cost log.

---

## Endpoints — quick reference

For full request/response shapes, see `references/api-shapes.md`.

### Text-to-image — minimum

```bash
curl -X POST https://api.x.ai/v1/images/generations \
  -H "Authorization: Bearer $XAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "grok-imagine-image", "prompt": "A cat in a tree"}'
```

### Image edit — single input image

```bash
curl -X POST https://api.x.ai/v1/images/edits \
  -H "Authorization: Bearer $XAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "grok-imagine-image",
    "prompt": "Render this as a pencil sketch",
    "image": {"url": "https://..."}
  }'
```

### Image edit — multi-reference

Up to 5 input images. Refer to them as `<IMAGE_0>`, `<IMAGE_1>`, etc. in the prompt.

```bash
curl -X POST https://api.x.ai/v1/images/edits \
  -H "Authorization: Bearer $XAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "grok-imagine-image",
    "prompt": "Show <IMAGE_0> sitting on the bench in <IMAGE_1>",
    "images": [
      {"url": "https://character.jpg"},
      {"url": "https://bench-scene.jpg"}
    ]
  }'
```

### Text-to-video — submit, then poll

```bash
# Submit
RESP=$(curl -s -X POST https://api.x.ai/v1/videos/generations \
  -H "Authorization: Bearer $XAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "grok-imagine-video",
    "prompt": "A serene lake at sunrise, mist on the water",
    "duration": 8,
    "aspect_ratio": "16:9",
    "resolution": "720p"
  }')
REQ_ID=$(echo "$RESP" | jq -r '.request_id')

# Poll
while :; do
  R=$(curl -s -H "Authorization: Bearer $XAI_API_KEY" "https://api.x.ai/v1/videos/$REQ_ID")
  STATUS=$(echo "$R" | jq -r '.status')
  case "$STATUS" in
    done) echo "$R" | jq -r '.video.url'; break ;;
    failed|expired) echo "FAILED: $R"; break ;;
    pending) sleep 5 ;;
  esac
done
```

### Image-to-video (I2V)

```json
{
  "model": "grok-imagine-video",
  "prompt": "She walks slowly forward toward the camera",
  "image": {"url": "https://keyframe.jpg"},
  "duration": 8,
  "aspect_ratio": "16:9",
  "resolution": "720p"
}
```

### Reference-to-video (R2V)

Different from I2V. The image is a **style/identity reference**, not the literal first frame. Stronger character lock across multiple separate calls than I2V.

```json
{
  "model": "grok-imagine-video",
  "prompt": "She turns to look over her shoulder at the camera",
  "reference_images": [{"url": "https://character-reference.jpg"}],
  "duration": 5,
  "aspect_ratio": "16:9",
  "resolution": "720p"
}
```

### Video edit

```json
{
  "model": "grok-imagine-video",
  "prompt": "Give the woman a silver necklace",
  "video": {"url": "https://input.mp4"}
}
```

### Video extend (1-10 seconds added to end)

```json
{
  "model": "grok-imagine-video",
  "prompt": "The camera slowly zooms out to reveal the city skyline",
  "video": {"url": "https://input.mp4"},
  "duration": 6
}
```

---

## Character consistency — four documented patterns

**Verified May 2026** across 4 test conditions ($1.20 test run, results in `references/known-quirks.md`). Character consistency on Grok Imagine is production-ready when the right pattern is matched to the use case.

| Pattern | Lock strength | Use when |
|---------|---------------|----------|
| **R2V** (`reference_images: [{url}]`) | Strongest cross-call lock | Multiple separate video clips of the same character; documentary cuts |
| **I2V chain** (`image: {url}` per call) | Strong sequential lock | Continuous narrative across cuts; hyperframe-length pieces |
| **Multi-image edit** (`<IMAGE_0>`, `<IMAGE_1>`) | Strong identity + scene compositing | "This person, that pose / that setting" |
| **n=4 batch** (`n: 4` in one request) | Strong within-request, slight drift on outliers | Variation menus, "show me four versions" |

**Decision flow:**
- Single anchor image → **R2V** for short character sequences (2-4 clips)
- Continuous narrative across cuts → **I2V chain** with `hyperframe.py`
- Place character in a different scene → **multi-image edit** with explicit `<IMAGE_0>` identity reference
- Variation exploration → **n=4 batch**

For deep details, see `references/character-consistency.md`.

---

## Hyperframe — video longer than 15 seconds

Grok Imagine caps any single clip at 15 seconds. For 30-second, 60-second, or longer pieces, the skill provides `scripts/hyperframe.py` which:

1. Generates keyframes (image-pro) for each beat using R2V or shared anchor
2. Bridges between keyframes using I2V (each clip's last frame → next clip's first frame)
3. Stitches with ffmpeg in `$GROK_STAGING` (per the snap-ffmpeg path restriction codified in session memory)
4. Writes a manifest with every keyframe, every clip, every prompt, every cost

See `references/hyperframe-patterns.md` for the full pattern. See `examples/05-hyperframe-30s.md` for a worked example.

---

## Graphic fall-back — text-heavy images

Imagine renders short text well (signs, menus, posters) but degrades on body copy. For text-heavy outputs (legal disclaimers, infographics, dense typography), do **not** ask Imagine to render the text. Instead:

1. Generate the background only (Imagine prompt strips text mentions)
2. Composite text in HTML+CSS (font/size/leading/color fully controlled)
3. Export at retina via headless Chromium (Puppeteer or Playwright)

Mirrors `openai-image`'s Text-Heavy Composites pattern. See `references/graphic-fallback-patterns.md` and `examples/06-graphic-fallback-card.md`.

---

## Cost tracking

Every API call writes a row to `$GROK_COST_LOG`:

```
2026-05-01T22:07:14Z | image_generation | grok-imagine-image | n=1 1k 16:9 | 200000000 | $0.0200 | abc123
2026-05-01T22:08:35Z | video_generation | grok-imagine-video | 480p 5s 16:9 | 2520000000 | $0.2520 | def456
```

`scripts/cost_summary.py` rolls this up: today, this week, by operation, by model. Run before every billing review.

---

## Output staging

Every operation writes to `$GROK_OUTPUT_ROOT/YYYY-MM-DD-HHMMSS-{op}-{slug}/` with:

- The asset (`.jpg`, `.mp4`)
- `request.json` — exact request payload sent
- `response.json` — full response body (URL, cost, moderation)
- `prompt.txt` — the prompt as plain text for grep-ability
- `manifest.json` — for hyperframe runs, full chain manifest

Reproducibility on day 90 from any output folder.

---

## Output URLs are temporary

xAI's image and video URLs come from `imgen.x.ai` and `vidgen.x.ai`. **Download them promptly.** They live for at least an hour in practice (verified live, May 2026), but xAI does not guarantee retention. The skill always downloads to `$GROK_OUTPUT_ROOT` before returning.

If the asset is needed for a downstream API call (I2V from a fresh keyframe, multi-image edit referencing a freshly-generated image), pass the xAI URL directly while it's still hot. For long-running pipelines where assets sit between operations for more than an hour, download and re-host to your own storage or pass as base64 data URIs.

---

## Known quirks

For full details with reproducible test cases, see `references/known-quirks.md`.

- **Image edit endpoint is JSON, NOT multipart.** OpenAI SDK's `images.edit()` will not work. Use the xAI SDK, raw REST, or the scripts in this skill.
- **Python's default `urllib` User-Agent gets 403'd by Cloudflare** when fetching `imgen.x.ai` URLs. Use `curl`, `requests` with a real User-Agent, or pass `User-Agent` explicitly. The skill's helpers handle this.
- **Generated MP4s contain three streams**: H.264 video, AAC audio, and an embedded MJPEG poster (thumbnail). Downstream ffmpeg work that assumes "stream 0 = video, stream 1 = audio" is fine, but `-map 0` without filtering will pull the poster too.
- **`ffprobe` on a server with snap-installed ffmpeg is at `/snap/bin/ffmpeg.ffprobe`, not `/snap/bin/ffprobe`.** Or use `-sseof -0.5` to seek from end without probing duration.
- **Snap ffmpeg has both READ and WRITE restrictions.** Cannot read files under `/mnt/claude-workspace/`; cannot write outputs to paths outside the snap allowlist (e.g. `/tmp/`). The skill's `first_frame()` and `last_frame()` helpers automatically route through `$GROK_STAGING` when the destination is non-snap-writable, then copy to the requested location. Direct ffmpeg calls in your own code must do the same.
- **`grok-imagine-image-pro` returns URLs from a different CDN than standard.** Same Cloudflare UA-block applies. Skill helpers normalize this.
- **`/v1/agents` returns 403** with message "agents endpoint is not enabled for this team." This is the **Voice Agent API** (an IVR/speech-to-speech system), not a general agent endpoint, and is gated per-team. Not relevant to image/video work. Standard agentic loops use `/v1/responses` with Remote MCP Tools instead — see `references/api-shapes.md`.

---

## Pairing with other skills

| Need | Pair with |
|------|-----------|
| Author shot lists / structured video prompts | a structured video-prompt authoring tool |
| Text-heavy image composites (HTML overlay) | this skill's graphic fall-back + headless Chromium (Puppeteer or Playwright) |
| Long-form video assembly with non-Imagine sources | [Remotion](https://remotion.dev) or another programmatic video framework |
| Branded constraints across many videos | a property-specific style skill of your own |

The recommended pattern: brand/property constraints → structured shot list → `grok-imagine` (execute, stitch, deliver). Voice and copy work happens in parallel.

---

## Scripts

All in `scripts/`. Each has `--help`. All read `~/.grok-imagine.env` if it exists, then `~/.env`, then accept overrides via flags.

| Script | Purpose |
|--------|---------|
| `grok_client.py` | Shared client. Imported by everything; never invoked directly. |
| `generate_image.py` | T2I |
| `edit_image.py` | I2I, multi-reference, mask |
| `generate_video.py` | T2V, I2V, R2V |
| `edit_video.py` | Video edit |
| `extend_video.py` | Video extend (1-10s) |
| `hyperframe.py` | Multi-clip pieces longer than 15s |
| `stitch.py` | ffmpeg concat with staging discipline |
| `cost_summary.py` | Roll up the cost log |

---

## Tests

`tests/test-edges.sh` exercises every documented parameter and every known quirk. Run quarterly or on demand:

```bash
bash tests/test-edges.sh
```

Output goes to `/tmp/grok-imagine-tests/` — one JSON response per test. Pass/fail summary at the end.

Estimated cost per full run: ~$0.50 (mostly image gen; one short video for poll-loop verification).
