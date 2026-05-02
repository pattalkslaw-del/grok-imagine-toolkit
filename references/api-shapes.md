# Grok Imagine API — locked endpoint shapes

Verified live against xAI as of May 2026. Re-run `tests/test-edges.sh` if anything below appears wrong in the cost log or in observed responses.

Base: `https://api.x.ai/v1`
Auth: `Authorization: Bearer $XAI_API_KEY`
Content-Type for all POSTs: `application/json` (NOT `multipart/form-data` for image edits — different from OpenAI)

---

## POST /v1/images/generations

### Request body

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `model` | string | yes | `grok-imagine-image` or `grok-imagine-image-pro` |
| `prompt` | string | yes | Up to 8000 chars (standard) / 10000 chars (pro) |
| `n` | integer | no | 1-10. Default 1. |
| `aspect_ratio` | string | no | `1:1`, `3:4`, `4:3`, `9:16`, `16:9`, `2:3`, `3:2`, `9:19.5`, `19.5:9`, `9:20`, `20:9`, `1:2`, `2:1`, `auto`. Default model-chosen. |
| `resolution` | string | no | `1k` or `2k`. Default 1k. |
| `quality` | string | no | `low`, `medium`, `high`. Documented but effect not always observable. |
| `response_format` | string | no | `url` (default) or `b64_json` |
| `user` | string | no | End-user identifier for abuse monitoring |

### Response body

```json
{
  "data": [
    {
      "url": "https://imgen.x.ai/xai-imgen/xai-tmp-imgen-{uuid}.jpeg",
      "mime_type": "image/jpeg",
      "revised_prompt": ""
    }
  ],
  "usage": {
    "cost_in_usd_ticks": 200000000
  }
}
```

`revised_prompt` is deprecated (always empty). `url` field absent when `response_format=b64_json` (then `b64_json` is populated). MIME type is always `image/jpeg` for outputs as of May 2026.

### "1k" actually produces

At `aspect_ratio: 16:9, resolution: 1k` you get **1408×768** JPEG. At 2k, expect proportionally larger. Verify with `tests/test-edges.sh` if exact pixel dimensions matter to a downstream pipeline.

---

## POST /v1/images/edits

JSON body. NOT multipart. This is the most common copy-paste-from-OpenAI mistake.

### Request body

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `model` | string | yes | Same as gen |
| `prompt` | string | yes | The edit instruction |
| `image` | object | one of `image`/`images` | `{"url": "..."}`. URL or `data:image/...;base64,...` |
| `images` | array of objects | one of `image`/`images` | Up to 5 images. Refer in prompt as `<IMAGE_0>`, `<IMAGE_1>`, etc. |
| `mask` | object | no | `{"url": "..."}`. White = edit, black = preserve. |
| `n` | integer | no | 1-10 |
| `aspect_ratio` | string | no | Same options as gen. With single input, aspect inherits the input. With multi-input, defaults to first image's aspect; override with `aspect_ratio`. |
| `resolution` | string | no | `1k` or `2k` |
| `response_format` | string | no | `url` or `b64_json` |

### Response body

Same shape as gen. Cost is base ($0.02) plus per-input-image fee (~$0.002 per input).

### Multi-image reference syntax

When passing multiple images, use angle-bracketed indexed tags in the prompt. They are positional — `<IMAGE_0>` is the first item in the `images` array, `<IMAGE_1>` is the second.

```json
{
  "prompt": "Show the woman from <IMAGE_0> sitting on the bench in <IMAGE_1>. Preserve her face, hair, and clothing exactly.",
  "images": [
    {"url": "https://character.jpg"},
    {"url": "https://bench-scene.jpg"}
  ]
}
```

The model is good at identity-locking from `<IMAGE_n>` when the prompt explicitly says "preserve" or "from `<IMAGE_n>`". Without that direction it may average features.

---

## POST /v1/videos/generations

Asynchronous. Returns a `request_id` immediately; poll `GET /v1/videos/{request_id}` until status is `done`.

### Request body

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `model` | string | yes | `grok-imagine-video` |
| `prompt` | string | yes for T2V/R2V; optional for I2V | Describe action, camera, audio together |
| `image` | object | for I2V | `{"url": "..."}`. Becomes start frame. |
| `reference_images` | array of objects | for R2V | `[{"url": "..."}, ...]`. Style/identity reference, NOT first frame. |
| `duration` | integer | no | 1-15. Default 8. Also accepts `seconds` alias. Accepts numeric or string. |
| `aspect_ratio` | string | no | `1:1`, `16:9`, `9:16`, `4:3`, `3:4`, `3:2`, `2:3` |
| `resolution` | string | no | `480p` or `720p` |
| `size` | string | no | `848x480`, `1696x960`, `1280x720`, `1920x1080`. Pick `resolution` OR `size`, not both. |
| `user` | string | no | End-user identifier |

### Modes — T2V vs I2V vs R2V

These are not separate endpoints. The mode is determined by which optional field is present:

| Mode | What's present | What it means |
|------|---------------|---------------|
| **T2V** (text-to-video) | `prompt` only | Standard text generation |
| **I2V** (image-to-video) | `prompt` + `image` | Image conditions the start of motion (NOT pixel-identical to frame 0) |
| **R2V** (reference-to-video) | `prompt` + `reference_images` | Image is style/identity reference; new scene generated |

Sending both `image` and `reference_images` is undefined behavior — pick one mode per call.

### Response body (submission)

```json
{
  "request_id": "f57ebc82-0ba2-9295-8a90-92a7ba838470"
}
```

That's it. No cost, no URL, no status — those come from polling.

---

## GET /v1/videos/{request_id}

Poll until `status` reaches a terminal state (`done`, `failed`, `expired`).

### Response body — pending

```json
{
  "status": "pending",
  "progress": 39,
  "model": "grok-imagine-video"
}
```

### Response body — done

```json
{
  "status": "done",
  "progress": 100,
  "video": {
    "url": "https://vidgen.x.ai/xai-vidgen-bucket/xai-video-{uuid}.mp4",
    "duration": 5,
    "respect_moderation": true
  },
  "model": "grok-imagine-video",
  "usage": {
    "cost_in_usd_ticks": 2500000000
  }
}
```

`respect_moderation: false` means the video was filtered post-generation — `url` will be empty in that case. Skill helpers raise an exception when `respect_moderation` is false rather than returning an empty URL.

### Response body — failed

```json
{
  "status": "failed",
  "progress": 0,
  "error": {
    "code": "invalid_argument",
    "message": "..."
  }
}
```

Error codes: `invalid_argument`, `permission_denied`, `failed_precondition`, `internal_error`. Authentication errors and model-not-found errors are returned synchronously as HTTP errors and never appear here.

### Polling cadence

- 5 seconds between polls is sufficient — any faster wastes round trips
- 5-second 480p clips: typically done in ~20 seconds wall-clock
- 8-second 720p clips: typically done in ~40-60 seconds
- 15-second 720p clips: typically done in ~90 seconds
- Set `GROK_VID_POLL_TIMEOUT=600` (10 minutes) as the safety ceiling

---

## POST /v1/videos/edits

Asynchronous, same poll pattern. Edit an existing video.

### Request body

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `model` | string | yes | `grok-imagine-video` |
| `prompt` | string | yes | The edit instruction |
| `video` | object | yes | `{"url": "..."}`. URL or `data:video/mp4;base64,...`. Must be `.mp4` with H.265, H.264, AV1, etc. |

Per docs: input video must be ≤ 8.7 seconds. Skill helpers truncate longer inputs in `$GROK_STAGING` before submission.

---

## POST /v1/videos/extensions

Asynchronous. Adds 1-10 seconds to the end of an existing video.

### Request body

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `model` | string | yes | `grok-imagine-video` |
| `prompt` | string | yes | What happens next |
| `video` | object | yes | `{"url": "..."}`. Same format constraints as edits. |
| `duration` | integer | no | 1-10 seconds. Default 6. |

The output is the **extension only**, not concatenated with the input. Stitch with `scripts/stitch.py` to combine input + extension.

---

## POST /v1/responses (agentic surface)

For tasks that need agent-style orchestration (the consumer Imagine Agent at grok.com runs on something like this), use the Responses API with Remote MCP Tools. Full docs: https://docs.x.ai/developers/tools/remote-mcp

### Minimum

```json
{
  "model": "grok-4.3",
  "input": [
    {"role": "user", "content": "Plan a 30-second video about ..."}
  ],
  "tools": [
    {
      "type": "mcp",
      "server_url": "https://docs.x.ai/api/mcp",
      "server_label": "xai-docs"
    }
  ]
}
```

### Quirks

- `allowed_tools` parameter from OpenAI's spec **is not supported** by xAI. xAI uses `allowed_tool_names` (in the SDK) but the OpenAI Responses-API field is rejected.
- `headers` parameter from OpenAI's spec is `extra_headers` in xAI SDK; in raw REST it works as `headers`.
- `require_approval` and `connector_id` are **not supported**.

This skill does not currently wrap `/v1/responses`. The skill's `hyperframe.py` is a deterministic pipeline, not an agent loop. If a future caller wants agent-driven planning of a video, that's a separate skill or a new module here.

---

## GET /v1/models, /v1/language-models, /v1/image-generation-models, /v1/video-generation-models

Read-only introspection. No cost. Returns currently-available models, prompt-length limits, pricing data, and capabilities. Useful for `tests/test-edges.sh` to detect model deprecations or new variants.

```bash
curl -s -H "Authorization: Bearer $XAI_API_KEY" \
  https://api.x.ai/v1/image-generation-models | jq '.models[] | .id'
```

---

## GET /v1/api-key

Returns ACL scopes, team ID, key status. Used by tests to confirm the key is active before running the suite.

```json
{
  "redacted_api_key": "xai-...XXXX",
  "user_id": "...",
  "team_id": "...",
  "acls": ["api-key:endpoint:*", "api-key:model:*", ""],
  "team_blocked": false,
  "api_key_blocked": false,
  "api_key_disabled": false
}
```

A key with `api-key:endpoint:*` and `api-key:model:*` has wildcard access to all endpoints and all models the team is enabled for. Per-endpoint enablement (e.g. Voice Agents) is a team-level flag, not an API-key permission.
