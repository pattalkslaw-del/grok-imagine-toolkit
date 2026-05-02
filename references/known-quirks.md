# Known quirks — Grok Imagine API

Verified live as of May 2026. Each item has a one-line statement of fact, then a code-level diagnosis or workaround. If something here looks wrong against current behavior, run `tests/test-edges.sh` and update.

---

## Image edits use JSON, not multipart

xAI's `/v1/images/edits` accepts `application/json` only. The OpenAI SDK's `images.edit()` method sends `multipart/form-data` and silently fails or returns a wrong-endpoint error.

**Diagnosis:** OpenAI clients work for `images.generate()` because that endpoint accepts JSON on both providers. They fail on `images.edit()` because xAI broke compatibility there.

**Workaround:** Use the xAI SDK, raw REST via `requests`, or the scripts in this skill. Never the OpenAI SDK for edits.

```python
# WORKS: xAI native
import xai_sdk
client = xai_sdk.Client()
client.image.sample(prompt="...", image_url="...")

# WORKS: raw REST
requests.post("https://api.x.ai/v1/images/edits", json={...})

# DOES NOT WORK: OpenAI SDK
from openai import OpenAI
OpenAI(base_url="https://api.x.ai/v1").images.edit(...)  # multipart, fails
```

---

## Python's default `urllib` User-Agent gets 403'd by Cloudflare

Fetching `imgen.x.ai` and `vidgen.x.ai` URLs with `urllib.request.urlopen` (default UA `Python-urllib/3.x`) returns 403 from Cloudflare. The image/video itself is publicly accessible — Cloudflare blocks the UA, not the request.

**Workaround:** Use one of:
- `curl` (subprocess)
- `requests` with default User-Agent (it sends `python-requests/X.Y.Z` which Cloudflare allows)
- `urllib` with explicit User-Agent header

```python
# DOES NOT WORK
urllib.request.urlretrieve(url, dest)

# WORKS
subprocess.run(["curl", "-s", "-f", "-L", "-o", dest, url], check=True)

# WORKS
requests.get(url, stream=True).raw.read()  # default UA accepted

# WORKS
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
urllib.request.urlopen(req).read()
```

The skill's helpers in `scripts/grok_client.py` use curl by default.

---

## Generated MP4s contain three streams

Every Grok Imagine video output has:
- Stream 0: H.264 video
- Stream 1: AAC audio
- Stream 2: MJPEG poster (embedded thumbnail)

Most ffmpeg operations work fine because stream 0 and stream 1 are picked by default. But:

- `ffmpeg -i input.mp4 -map 0 ...` will pull the poster stream too — usually harmless but bloats output
- Concat-encode operations sometimes warn about the third stream
- Some downstream tools (older video editors, mobile players) get confused by the poster

**Workaround:** When in doubt, explicitly map only the streams you want:

```bash
ffmpeg -i input.mp4 -map 0:v:0 -map 0:a:0 -c copy clean.mp4
```

The skill's `stitch.py` does this normalization automatically.

---

## ffprobe path is non-obvious on snap ffmpeg

Ubuntu snap-installed ffmpeg is from the snap package (`/snap/bin/ffmpeg`). The companion ffprobe is at `/snap/bin/ffmpeg.ffprobe`, NOT `/snap/bin/ffprobe`.

```bash
# DOES NOT EXIST on a server with snap-installed ffmpeg
/snap/bin/ffprobe

# CORRECT
/snap/bin/ffmpeg.ffprobe
```

**Better workaround when possible:** avoid ffprobe entirely. Use `-sseof` to seek from end:

```bash
# Get last frame without knowing duration
ffmpeg -y -sseof -0.5 -i input.mp4 -frames:v 1 -q:v 2 last.jpg
```

The skill's `grok_client.py` uses `-sseof -0.5` for last-frame extraction, no ffprobe needed.

---

## Snap ffmpeg has both READ and WRITE restrictions

The snap confinement on a server with snap-installed ffmpeg has two distinct restrictions, both verified in live testing:

**READ:** Snap ffmpeg cannot read files under `/mnt/claude-workspace/` (and certain other paths outside the snap allowlist). Codified in session memory.

**WRITE:** Snap ffmpeg cannot write to `/tmp/`, `/mnt/claude-workspace/`, or other paths outside the user's home tree. It CAN read from `/tmp/` but writing returns `Input/output error`. Discovered when frame-extraction tests wrote to `/tmp/grok-imagine-tests/` and ffmpeg failed with "Could not open file."

**Workaround:** All scripts route through `$GROK_STAGING` (default `~/tmp/grok-imagine-staging/`, always under `$HOME`) for any ffmpeg work. Inputs are copied from non-readable paths into staging first; outputs are written to staging then copied to the user's requested destination after.

The shared client provides:
- `stage_for_ffmpeg(src, staging_dir)` — copies a non-readable input into staging
- `_snap_writable(path)` — returns whether ffmpeg can write directly to a path
- `_ffmpeg_extract(...)` — wrapper that automatically routes through staging when the destination is non-snap-writable. Used by `first_frame()` and `last_frame()`.

This means scripts can call `first_frame(video, /tmp/anywhere.jpg)` and it just works; the helper detects the non-writable destination and stages transparently.

---

## `image-pro` returns URLs from a different CDN

Standard `grok-imagine-image` returns from `imgen.x.ai`. `grok-imagine-image-pro` may return from a Cloudflare R2 bucket or a different CDN edge. Both subject to the same UA-block. Both work with curl. The skill normalizes via the same download path.

---

## URLs are temporary but live longer than docs suggest

The xAI docs say "URLs are temporary, download promptly." In practice, `imgen.x.ai` URLs survive for at least an hour (verified live, May 2026). Long enough that you can safely pass a freshly-generated URL to a downstream call without re-hosting.

**Defensive practice:** download immediately anyway. The skill always pulls to `$GROK_STAGING` after generation. Downstream API calls reference the original URL only if they happen within the same session run.

---

## Multi-image edit uses positional `<IMAGE_n>` syntax

When passing multiple images via the `images` array (image edits, max 5), reference them in the prompt as `<IMAGE_0>`, `<IMAGE_1>`, etc. — strictly positional, zero-indexed.

The model is much better at locking identity from `<IMAGE_n>` references when the prompt explicitly says "preserve" or "from `<IMAGE_n>`":

```
GOOD:  "Show the woman from <IMAGE_0> in the pose of <IMAGE_1>. Preserve all features from <IMAGE_0> exactly."

WEAKER: "Combine these two images."
```

---

## I2V interprets, doesn't pixel-copy

`image: {"url": "..."}` in a video request conditions the **start** of the generated motion. The first frame of the resulting clip is *very close* to the input image but not pixel-identical. After several I2V hops in a chain, drift accumulates.

**Limit:** keep I2V chains to 6-8 hops before re-anchoring with R2V. The skill's `hyperframe.py` does this automatically when `--reanchor-every` is set (default 6).

---

## R2V is not I2V

`reference_images: [...]` in a video request is a **style/identity reference**, not a first-frame conditioning. The clip starts from a freshly-generated frame; the reference image guides the look of the character/scene/style.

| You want | Use |
|----------|-----|
| The clip to LITERALLY START at this image | `image: {"url": ...}` (I2V) |
| The clip's character/style to MATCH this image | `reference_images: [{"url": ...}]` (R2V) |

Sending both `image` and `reference_images` in the same call is undefined behavior — the skill rejects this combination.

---

## Audio is generated per clip, no continuity guarantee across cuts

Each video gen produces independent audio. Stitching multiple clips creates audible discontinuity at every cut.

**Workaround options (see `references/hyperframe-patterns.md` for detail):**
1. Include the same ambient bed in every clip's prompt — "soft cafe chatter, distant footsteps, gentle breeze" repeated across all prompts
2. Strip generated audio with ffmpeg, dub voiceover and music in post

The skill's `hyperframe.py` accepts a single `--ambient` flag that injects consistent audio language into every prompt.

---

## `respect_moderation: false` returns empty URL

When a video fails moderation post-generation, the response has `"respect_moderation": false` and an empty/missing `url` field — but `status: done` and a non-zero `cost_in_usd_ticks`. **You pay for filtered content.**

The skill's helpers raise an explicit `ModerationFiltered` exception (not just a missing-URL error) when this happens, with the request_id, prompt, and cost so you can adjust and retry.

---

## /v1/agents is the Voice Agent API, not a general agent endpoint

If you hit `/v1/agents` directly, you'll get 403 with message `"agents endpoint is not enabled for this team"`. Despite the generic-sounding path, this endpoint backs the **Voice Agent API** (a speech-to-speech IVR system; not relevant to image/video work). It's gated per-team.

For agentic loops in general (planning, multi-step orchestration), use `/v1/responses` with Remote MCP Tools — that surface IS open and is what `grok.com/imagine/agent` runs on top of. See `references/api-shapes.md` for the request shape.

---

## Cost is in ticks, not dollars

Every response returns `usage.cost_in_usd_ticks`. 1 USD = 10^10 ticks. Convert: `dollars = ticks / 1e10`.

The skill always logs both raw ticks (for integer precision) and the dollar conversion (for human readability). Don't try to convert prematurely — keep ticks integer until the final log line.

---

## URLs in responses can change format

xAI sometimes returns image URLs with paths like `/xai-imgen/xai-tmp-imgen-{uuid}.jpeg` and sometimes with paths like `/xai-imgen/{uuid}.jpeg`. Both are valid. Don't write code that depends on the URL format.

The skill's helpers treat the URL as opaque — pass through whatever xAI returned.

---

## Re-running this verification

`tests/test-edges.sh` exercises every quirk above with a known-input test that should produce a known-output result. Run quarterly or when something looks off in production.
