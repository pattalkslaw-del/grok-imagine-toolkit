# grok-imagine

[![CI](https://github.com/pattalkslaw-del/grok-imagine-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/pattalkslaw-del/grok-imagine-toolkit/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![xAI Grok Imagine](https://img.shields.io/badge/xAI-Grok%20Imagine-black.svg)](https://docs.x.ai/developers/model-capabilities/images/generation)

Skill for the xAI Grok Imagine API — image and video generation, editing, extending, and multi-clip orchestration.

This README is for **end users** of the skill (humans configuring it for their own use). For Claude's operational guide to the skill, read `SKILL.md`. For deep API reference, read the files in `references/`.

## Install / configure

The skill is shell scripts and Python; no install step. Make sure you have:

- Python 3.10+
- `requests` (recommended; falls back to `urllib` if absent)
- `curl` (for downloading assets — required because xAI's CDN blocks Python's default User-Agent)
- `ffmpeg` (snap or apt; tested with snap on Ubuntu 24)

Then set up your environment:

```bash
# Copy the example config
cp .config.example ~/.grok-imagine.env

# Edit it to set your API key
nano ~/.grok-imagine.env

# Source it (or auto-source from your shell profile)
source ~/.grok-imagine.env
```

The skill loads config in this priority order (highest wins):

1. Process environment (CLI exports)
2. `~/.grok-imagine.env` (skill-specific)
3. `~/.env` (general secrets)
4. Built-in defaults

You can also pass any value as a CLI flag for one-off overrides. Flags always win.

## Required configuration

| Variable | Required | What it is |
|----------|----------|-----------|
| `XAI_API_KEY` | Yes | Your xAI API key (starts with `xai-`). Get from https://console.x.ai. |

That's it for required config. Everything else has a sensible default.

## Optional configuration

### Image defaults

| Variable | Default | Options |
|----------|---------|---------|
| `GROK_IMG_MODEL` | `grok-imagine-image` | `grok-imagine-image` (cheap, $0.02), `grok-imagine-image-pro` (premium, $0.07) |
| `GROK_IMG_RESOLUTION` | `1k` | `1k`, `2k` |
| `GROK_IMG_ASPECT_RATIO` | `auto` | `1:1`, `16:9`, `9:16`, `4:3`, `3:4`, `3:2`, `2:3`, `1:2`, `2:1`, `9:19.5`, `19.5:9`, `9:20`, `20:9`, `auto` |
| `GROK_IMG_RESPONSE_FORMAT` | `url` | `url`, `b64_json` |
| `GROK_IMG_N` | `1` | 1-10 |

### Video defaults

| Variable | Default | Options |
|----------|---------|---------|
| `GROK_VID_MODEL` | `grok-imagine-video` | (only one model) |
| `GROK_VID_RESOLUTION` | `720p` | `480p` (cheaper, faster), `720p` (production) |
| `GROK_VID_DURATION` | `8` | 1-15 seconds per clip |
| `GROK_VID_ASPECT_RATIO` | `16:9` | `1:1`, `16:9`, `9:16`, `4:3`, `3:4`, `3:2`, `2:3` |
| `GROK_VID_POLL_INTERVAL` | `5` | seconds between status checks |
| `GROK_VID_POLL_TIMEOUT` | `600` | max seconds to wait before timeout |

### Output paths

| Variable | Default | Notes |
|----------|---------|-------|
| `GROK_OUTPUT_ROOT` | `~/grok-imagine-output` | Where finished assets are staged |
| `GROK_STAGING` | `~/tmp/grok-imagine-staging` | Intermediate ffmpeg work; must be readable by snap-ffmpeg |
| `GROK_COST_LOG` | `~/log/grok-imagine-cost.log` | Per-call cost log |

If you're on a server with snap-installed ffmpeg with snap-ffmpeg, leave `GROK_STAGING` under `~/`. If you're on a system with apt-ffmpeg, you can point it anywhere.

## Running the scripts

All scripts in `scripts/` are direct CLIs with `--help`:

```bash
python3 scripts/generate_image.py --help
python3 scripts/generate_video.py --help
python3 scripts/hyperframe.py --help
```

Common workflows are in `examples/`:

| Example | Use case |
|---------|----------|
| `examples/01-single-image.md` | One prompt, one image |
| `examples/02-multi-image-merge.md` | Compose a character into a scene |
| `examples/03-text-to-video.md` | Text-to-video |
| `examples/04-image-to-video.md` | Animate a still image |
| `examples/05-hyperframe-30s.md` | 30-second multi-clip continuous narrative |
| `examples/06-graphic-fallback-card.md` | Text-heavy social card via HTML+Chromium |
| `examples/07-style-locked-sequence.md` | Same character across four separate clips |

## Running the test suite

The test suite exercises every documented parameter and every known quirk:

```bash
# Full suite (~$0.50)
bash tests/test-edges.sh

# Skip video tests (~$0.13)
bash tests/test-edges.sh --no-video

# Free auth/config check only
bash tests/test-edges.sh --quick
```

Outputs go to `/tmp/grok-imagine-tests/`. Pass/fail summary at the end.

Re-run the full suite quarterly or whenever something looks wrong in production. xAI ships rapidly; the test suite is your safety net for breaking changes.

## Cost tracking

Every API call logs a row to `$GROK_COST_LOG`. Roll it up with:

```bash
# Total spend
python3 scripts/cost_summary.py

# By operation
python3 scripts/cost_summary.py --by operation

# This month
python3 scripts/cost_summary.py --since 2026-05-01

# JSON for automation
python3 scripts/cost_summary.py --json
```

Reconcile against your xAI Console billing page monthly. If anything disagrees beyond a few percent, look for non-API line items in the console (subscriptions, retainers).

## Reference docs

- `references/api-shapes.md` — every endpoint, every parameter, every response field. Pure facts.
- `references/pricing.md` — verified rates, tick math, worked examples
- `references/prompting-tips.md` — what prompt patterns work on Grok Imagine specifically
- `references/character-consistency.md` — the four documented patterns (R2V / I2V chain / multi-image edit / n=4 batch) with strength rankings and decision flow
- `references/hyperframe-patterns.md` — multi-clip orchestration deep dive
- `references/graphic-fallback-patterns.md` — when to use HTML+Chromium instead of fighting the model
- `references/known-quirks.md` — every gotcha discovered in live testing, with workarounds

## Two layers, one repo

The toolkit ships with both layers needed to go from idea to rendered video:

| Layer | Lives in | What it does |
|---|---|---|
| **Authoring** | `prompts/SKILL.md` | Turns a scene description into a structured shot list with effects, density map, and energy arc. Loaded as a skill by Claude or used as a prompt template by any LLM. |
| **Execution** | `scripts/`, `references/`, `examples/` | Calls the xAI API, polls, downloads, stitches, logs costs. Generates images and video from a prompt or shot list. |

The two layers are decoupled on purpose. You can use the authoring layer alone (paste output into any Grok Imagine call), or use the execution layer alone (drive it from your own prompt source). The handoff is plain text: a shot list goes into `scripts/generate_video.py` or `scripts/hyperframe.py`.

```
your brief  ->  prompts/SKILL.md (shot list)  ->  scripts/generate_video.py  ->  rendered clip + cost log
```

For brand/character constraints across many videos, build a small property skill that wraps `prompts/SKILL.md` with locked character vocabulary and do-not-do lists, then hands the constrained brief to the authoring layer. That part is intentionally outside this repo because it's specific to your creative property.

## Pairing with other tools

| Need | Pair with |
|---|---|
| Long-form video assembly with non-Imagine sources (stock, screen recordings, voiceover) | [Remotion](https://remotion.dev) |
| Text-heavy image composites the model handles poorly | Headless Chromium (Puppeteer or Playwright) plus `references/graphic-fallback-patterns.md` |
| Brand voice for accompanying copy, captions, and metadata | Your own writing-voice tooling, kept separate so you can change models for one without touching the other |

## Troubleshooting

### "401 Unauthorized"

Your `XAI_API_KEY` isn't set or isn't valid. Test with:

```bash
python3 scripts/grok_client.py
```

Should print your team ID and ACL scopes.

### "403 Forbidden" downloading an asset

Cloudflare blocked the User-Agent. The skill uses `curl` for all downloads to avoid this. If you see this from the skill's helpers, file a bug — the helpers should handle it.

### "Snap ffmpeg cannot read this path"

Move the input to `$GROK_STAGING` (default `~/tmp/grok-imagine-staging`). The skill's helpers do this automatically; if you're calling ffmpeg directly, stage first.

### "Video generation failed: invalid_argument"

Common causes:
- Aspect ratio not supported (check `references/api-shapes.md`)
- Duration outside 1-15 (or 1-10 for extensions)
- Both `image` and `reference_images` passed (mutually exclusive)
- Input video for edit/extend is not `.mp4`

### "Moderation filtered"

The prompt or output triggered xAI's content filter. The skill raises `ModerationFiltered` with the request_id and prompt so you can iterate. See the moderation section in `references/known-quirks.md`.

### Costs disagree with billing dashboard

The cost log is per-request. xAI's console may include subscription components or monthly minimums. Reconcile to within a few percent on raw API usage. Anything beyond that means non-API line items.

## License

Released under the MIT License. Pull requests, issues, and feedback welcome.
