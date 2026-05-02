"""
grok_client.py — shared client for Grok Imagine API.

All scripts in this skill import from here. Never invoke this file directly.

Responsibilities:
- Load config from ~/.grok-imagine.env, ~/.env, or environment vars
- Provide auth, retry, and timeout for every endpoint
- Run the async polling loop for video operations
- Log every cost to $GROK_COST_LOG with full context
- Stage outputs to $GROK_OUTPUT_ROOT/{run_id}/ with manifest
- Raise typed exceptions for moderation, rate-limit, server errors

Patterns:
- The client is sync by default. For concurrent video gen, use async_call().
- All downloads use curl (Cloudflare blocks Python's urllib UA on imgen/vidgen URLs).
- ffmpeg work uses $GROK_STAGING (snap-ffmpeg can't read /mnt/claude-workspace/).
"""

from __future__ import annotations

import base64
import json
import os
import shutil as _shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Literal
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "GROK_IMG_MODEL": "grok-imagine-image",
    "GROK_IMG_RESOLUTION": "1k",
    "GROK_IMG_ASPECT_RATIO": "auto",
    "GROK_IMG_RESPONSE_FORMAT": "url",
    "GROK_IMG_N": "1",
    "GROK_VID_MODEL": "grok-imagine-video",
    "GROK_VID_RESOLUTION": "720p",
    "GROK_VID_DURATION": "8",
    "GROK_VID_ASPECT_RATIO": "16:9",
    "GROK_VID_POLL_INTERVAL": "5",
    "GROK_VID_POLL_TIMEOUT": "600",
    "GROK_OUTPUT_ROOT": str(Path.home() / "grok-imagine-output"),
    "GROK_STAGING": str(Path.home() / "tmp" / "grok-imagine-staging"),
    "GROK_COST_LOG": str(Path.home() / "log" / "grok-imagine-cost.log"),
}


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        # Strip surrounding quotes if present
        v = v.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        out[k.strip()] = v
    return out


def load_config() -> dict[str, str]:
    """
    Load config in priority order:
      1. Process environment (highest)
      2. ~/.grok-imagine.env (skill-specific)
      3. ~/.env (general secrets)
      4. DEFAULT_CONFIG (lowest)
    """
    cfg = dict(DEFAULT_CONFIG)
    home = Path.home()
    cfg.update(_load_env_file(home / ".env"))
    cfg.update(_load_env_file(home / ".grok-imagine.env"))
    for k, v in os.environ.items():
        if k.startswith("GROK_") or k == "XAI_API_KEY":
            cfg[k] = v
    return cfg


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class GrokImagineError(Exception):
    """Base exception."""


class AuthError(GrokImagineError):
    """Bad or missing API key."""


class RateLimitError(GrokImagineError):
    """xAI returned 429."""


class ModerationFiltered(GrokImagineError):
    """Content filtered post-generation. respect_moderation=false."""

    def __init__(self, request_id: str, prompt: str, cost_ticks: int):
        super().__init__(
            f"Content filtered (request_id={request_id}, cost ${cost_ticks/1e10:.4f}). "
            f"Prompt: {prompt[:200]}..."
        )
        self.request_id = request_id
        self.prompt = prompt
        self.cost_ticks = cost_ticks


class VideoGenFailed(GrokImagineError):
    """status=failed from poll."""

    def __init__(self, request_id: str, error: dict):
        super().__init__(f"Video generation failed (request_id={request_id}): {error}")
        self.request_id = request_id
        self.error = error


class PollTimeout(GrokImagineError):
    """Video poll exceeded GROK_VID_POLL_TIMEOUT."""


# ---------------------------------------------------------------------------
# Cost logging
# ---------------------------------------------------------------------------

@dataclass
class CostEntry:
    timestamp: str
    operation: str
    model: str
    params_summary: str
    cost_ticks: int
    request_id: str

    @property
    def cost_usd(self) -> float:
        return self.cost_ticks / 1e10

    def to_logline(self) -> str:
        return (
            f"{self.timestamp} | {self.operation} | {self.model} | "
            f"{self.params_summary} | {self.cost_ticks} | "
            f"${self.cost_usd:.4f} | {self.request_id}"
        )


def log_cost(cfg: dict, entry: CostEntry) -> None:
    log_path = Path(cfg["GROK_COST_LOG"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as f:
        f.write(entry.to_logline() + "\n")


# ---------------------------------------------------------------------------
# HTTP layer (uses requests if available, else urllib)
# ---------------------------------------------------------------------------

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False
    import urllib.request as _urllib_request
    import urllib.error as _urllib_error


BASE = "https://api.x.ai/v1"


def _request(method: str, endpoint: str, api_key: str, *, body: Optional[dict] = None, timeout: int = 120) -> dict:
    """Single shared HTTP request fn. Returns parsed JSON or raises."""
    url = BASE + endpoint
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    if _HAS_REQUESTS:
        if method == "GET":
            r = _requests.get(url, headers=headers, timeout=timeout)
        else:
            r = _requests.request(
                method, url, headers=headers,
                json=body, timeout=timeout,
            )
        if r.status_code == 401:
            raise AuthError(f"401 Unauthorized: {r.text[:200]}")
        if r.status_code == 429:
            raise RateLimitError(f"429 Rate limited: {r.text[:200]}")
        if r.status_code >= 400:
            raise GrokImagineError(f"HTTP {r.status_code}: {r.text[:500]}")
        return r.json()

    # urllib fallback
    data = json.dumps(body).encode() if body is not None else None
    req = _urllib_request.Request(url, data=data, headers=headers, method=method)
    try:
        with _urllib_request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except _urllib_error.HTTPError as e:
        if e.code == 401:
            raise AuthError(f"401 Unauthorized: {e.read()[:200]}")
        if e.code == 429:
            raise RateLimitError(f"429 Rate limited: {e.read()[:200]}")
        raise GrokImagineError(f"HTTP {e.code}: {e.read()[:500]}")


# ---------------------------------------------------------------------------
# Download helpers (curl, because Python urllib UA is blocked by Cloudflare)
# ---------------------------------------------------------------------------

def download(url: str, dest: Path) -> Path:
    """Download a URL to dest using curl (Cloudflare blocks Python UA)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["curl", "-s", "-f", "-L", "--max-time", "120", "-o", str(dest), url],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise GrokImagineError(f"Download failed for {url}: {result.stderr[:200]}")
    return dest


def encode_data_uri(image_path: Path, mime: str = "image/jpeg") -> str:
    """Encode a local image as a base64 data URI suitable for image/video API inputs."""
    b = image_path.read_bytes()
    return f"data:{mime};base64,{base64.b64encode(b).decode()}"


# ---------------------------------------------------------------------------
# Frame extraction (ffmpeg with snap-friendly path)
# ---------------------------------------------------------------------------

FFMPEG = os.environ.get("GROK_FFMPEG") or _shutil.which("ffmpeg") or "/snap/bin/ffmpeg"


def _snap_writable(path: Path) -> bool:
    """True if snap-ffmpeg can write to this path.

    snap-ffmpeg can write under $HOME and a few other places, but NOT to /tmp,
    /mnt/claude-workspace, or other restricted paths. When in doubt, route through
    $GROK_STAGING (always under $HOME) and copy to the final destination after.
    """
    home = Path.home().resolve()
    try:
        resolved = path.resolve()
    except Exception:
        return False
    try:
        resolved.relative_to(home)
        return True
    except ValueError:
        return False


def _ffmpeg_extract(video_path: Path, output_path: Path, args: list) -> Path:
    """Run ffmpeg with snap-write awareness. Stages output if dest is non-writable."""
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if _snap_writable(output_path):
        subprocess.run(
            [FFMPEG, "-y", *args, str(output_path)],
            capture_output=True, check=True,
        )
        return output_path

    # Stage to ~/tmp, then copy to final destination
    cfg = load_config()
    staging_root = Path(cfg["GROK_STAGING"]).resolve()
    staging_root.mkdir(parents=True, exist_ok=True)
    staged_out = staging_root / f"frame-{uuid.uuid4().hex[:8]}-{output_path.name}"
    subprocess.run(
        [FFMPEG, "-y", *args, str(staged_out)],
        capture_output=True, check=True,
    )
    subprocess.run(["cp", str(staged_out), str(output_path)], check=True)
    staged_out.unlink(missing_ok=True)
    return output_path


def first_frame(video_path: Path, output_path: Path) -> Path:
    """Extract first frame as JPEG. Routes through staging if dest is non-snap-writable."""
    return _ffmpeg_extract(
        video_path, output_path,
        ["-i", str(video_path), "-frames:v", "1", "-q:v", "2"],
    )


def last_frame(video_path: Path, output_path: Path) -> Path:
    """Extract last frame using -sseof seek. Routes through staging if needed."""
    return _ffmpeg_extract(
        video_path, output_path,
        ["-sseof", "-0.5", "-i", str(video_path), "-frames:v", "1", "-q:v", "2"],
    )


def stage_for_ffmpeg(src: Path, staging_dir: Path) -> Path:
    """Copy src into staging_dir (snap-readable) and return staged path."""
    staging_dir.mkdir(parents=True, exist_ok=True)
    dest = staging_dir / src.name
    if src.resolve() != dest.resolve():
        subprocess.run(["cp", str(src), str(dest)], check=True)
    return dest


# ---------------------------------------------------------------------------
# Output staging
# ---------------------------------------------------------------------------

def _slug(text: str, max_len: int = 32) -> str:
    """Filesystem-safe slug for output folder names."""
    cleaned = "".join(c if c.isalnum() else "-" for c in text.lower())
    cleaned = "-".join(p for p in cleaned.split("-") if p)
    return cleaned[:max_len]


def make_output_dir(cfg: dict, op: str, label: str = "") -> Path:
    """Create a timestamped output dir. Returns its path."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    slug = _slug(label) if label else uuid.uuid4().hex[:8]
    name = f"{ts}-{op}-{slug}"
    path = Path(cfg["GROK_OUTPUT_ROOT"]) / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_artifact_metadata(out_dir: Path, request_body: dict, response_body: dict, prompt: str) -> None:
    """Write request.json, response.json, prompt.txt next to the asset."""
    (out_dir / "request.json").write_text(json.dumps(request_body, indent=2))
    (out_dir / "response.json").write_text(json.dumps(response_body, indent=2))
    (out_dir / "prompt.txt").write_text(prompt)


# ---------------------------------------------------------------------------
# Image API
# ---------------------------------------------------------------------------

def generate_image(
    prompt: str,
    *,
    model: Optional[str] = None,
    n: Optional[int] = None,
    aspect_ratio: Optional[str] = None,
    resolution: Optional[str] = None,
    response_format: Optional[str] = None,
    cfg: Optional[dict] = None,
    api_key: Optional[str] = None,
) -> dict:
    """POST /v1/images/generations. Returns response body."""
    cfg = cfg or load_config()
    api_key = api_key or cfg.get("XAI_API_KEY")
    if not api_key:
        raise AuthError("XAI_API_KEY not set")

    body = {
        "model": model or cfg["GROK_IMG_MODEL"],
        "prompt": prompt,
        "n": int(n if n is not None else cfg["GROK_IMG_N"]),
        "aspect_ratio": aspect_ratio or cfg["GROK_IMG_ASPECT_RATIO"],
        "resolution": resolution or cfg["GROK_IMG_RESOLUTION"],
        "response_format": response_format or cfg["GROK_IMG_RESPONSE_FORMAT"],
    }
    resp = _request("POST", "/images/generations", api_key, body=body)
    cost_ticks = resp.get("usage", {}).get("cost_in_usd_ticks", 0)
    log_cost(cfg, CostEntry(
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        operation="image_generation",
        model=body["model"],
        params_summary=f'n={body["n"]} {body["resolution"]} {body["aspect_ratio"]}',
        cost_ticks=cost_ticks,
        request_id="-",
    ))
    return resp


def edit_image(
    prompt: str,
    *,
    image: Optional[dict] = None,
    images: Optional[list[dict]] = None,
    mask: Optional[dict] = None,
    model: Optional[str] = None,
    n: Optional[int] = None,
    aspect_ratio: Optional[str] = None,
    resolution: Optional[str] = None,
    response_format: Optional[str] = None,
    cfg: Optional[dict] = None,
    api_key: Optional[str] = None,
) -> dict:
    """POST /v1/images/edits. Pass `image` for single, `images` for multi (max 5)."""
    if image and images:
        raise ValueError("Pass `image` (single) OR `images` (multi), not both.")
    if not image and not images:
        raise ValueError("Pass `image` or `images`.")

    cfg = cfg or load_config()
    api_key = api_key or cfg.get("XAI_API_KEY")
    if not api_key:
        raise AuthError("XAI_API_KEY not set")

    body: dict[str, Any] = {
        "model": model or cfg["GROK_IMG_MODEL"],
        "prompt": prompt,
        "n": int(n if n is not None else cfg["GROK_IMG_N"]),
        "resolution": resolution or cfg["GROK_IMG_RESOLUTION"],
        "response_format": response_format or cfg["GROK_IMG_RESPONSE_FORMAT"],
    }
    if image:
        body["image"] = image
    if images:
        body["images"] = images
    if mask:
        body["mask"] = mask
    if aspect_ratio:
        body["aspect_ratio"] = aspect_ratio

    resp = _request("POST", "/images/edits", api_key, body=body)
    cost_ticks = resp.get("usage", {}).get("cost_in_usd_ticks", 0)
    n_inputs = (1 if image else 0) + (len(images) if images else 0)
    log_cost(cfg, CostEntry(
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        operation="image_edit",
        model=body["model"],
        params_summary=f"inputs={n_inputs} {body['resolution']}",
        cost_ticks=cost_ticks,
        request_id="-",
    ))
    return resp


# ---------------------------------------------------------------------------
# Video API
# ---------------------------------------------------------------------------

VideoMode = Literal["t2v", "i2v", "r2v"]


def generate_video(
    prompt: Optional[str] = None,
    *,
    image: Optional[dict] = None,
    reference_images: Optional[list[dict]] = None,
    model: Optional[str] = None,
    duration: Optional[int] = None,
    aspect_ratio: Optional[str] = None,
    resolution: Optional[str] = None,
    cfg: Optional[dict] = None,
    api_key: Optional[str] = None,
    poll: bool = True,
    poll_interval: Optional[int] = None,
    poll_timeout: Optional[int] = None,
) -> dict:
    """
    POST /v1/videos/generations + poll until done.

    Mode is determined by which optional argument is set:
      - image only -> I2V
      - reference_images only -> R2V
      - neither -> T2V (prompt required)

    Returns the final 'done' response body (with .video.url, .usage, etc.).
    If poll=False, returns the submission response (with .request_id only).
    """
    if image and reference_images:
        raise ValueError("Pass `image` (I2V) OR `reference_images` (R2V), not both.")
    if not image and not reference_images and not prompt:
        raise ValueError("Pass `prompt` for T2V, `image` for I2V, or `reference_images` for R2V.")

    cfg = cfg or load_config()
    api_key = api_key or cfg.get("XAI_API_KEY")
    if not api_key:
        raise AuthError("XAI_API_KEY not set")

    body: dict[str, Any] = {
        "model": model or cfg["GROK_VID_MODEL"],
        "duration": int(duration if duration is not None else cfg["GROK_VID_DURATION"]),
        "aspect_ratio": aspect_ratio or cfg["GROK_VID_ASPECT_RATIO"],
        "resolution": resolution or cfg["GROK_VID_RESOLUTION"],
    }
    if prompt:
        body["prompt"] = prompt
    if image:
        body["image"] = image
    if reference_images:
        body["reference_images"] = reference_images

    submit_resp = _request("POST", "/videos/generations", api_key, body=body)
    request_id = submit_resp.get("request_id")
    if not request_id:
        raise GrokImagineError(f"No request_id in response: {submit_resp}")

    if not poll:
        return submit_resp

    return _poll_video(
        request_id=request_id,
        prompt=prompt or "",
        cfg=cfg,
        api_key=api_key,
        poll_interval=poll_interval,
        poll_timeout=poll_timeout,
        operation="video_generation" if not (image or reference_images)
                  else ("video_i2v" if image else "video_r2v"),
        params_summary=f"{body['resolution']} {body['duration']}s {body['aspect_ratio']}",
        model=body["model"],
    )


def edit_video(
    prompt: str,
    video: dict,
    *,
    model: Optional[str] = None,
    cfg: Optional[dict] = None,
    api_key: Optional[str] = None,
    poll: bool = True,
    poll_interval: Optional[int] = None,
    poll_timeout: Optional[int] = None,
) -> dict:
    """POST /v1/videos/edits + poll."""
    cfg = cfg or load_config()
    api_key = api_key or cfg.get("XAI_API_KEY")
    if not api_key:
        raise AuthError("XAI_API_KEY not set")

    body = {
        "model": model or cfg["GROK_VID_MODEL"],
        "prompt": prompt,
        "video": video,
    }
    submit_resp = _request("POST", "/videos/edits", api_key, body=body)
    request_id = submit_resp.get("request_id")
    if not request_id:
        raise GrokImagineError(f"No request_id in response: {submit_resp}")
    if not poll:
        return submit_resp

    return _poll_video(
        request_id=request_id, prompt=prompt, cfg=cfg, api_key=api_key,
        poll_interval=poll_interval, poll_timeout=poll_timeout,
        operation="video_edit", params_summary="edit",
        model=body["model"],
    )


def extend_video(
    prompt: str,
    video: dict,
    *,
    duration: int = 6,
    model: Optional[str] = None,
    cfg: Optional[dict] = None,
    api_key: Optional[str] = None,
    poll: bool = True,
    poll_interval: Optional[int] = None,
    poll_timeout: Optional[int] = None,
) -> dict:
    """POST /v1/videos/extensions + poll. duration is the EXTENSION length (1-10s)."""
    if not 1 <= duration <= 10:
        raise ValueError("duration must be 1-10 seconds")

    cfg = cfg or load_config()
    api_key = api_key or cfg.get("XAI_API_KEY")
    if not api_key:
        raise AuthError("XAI_API_KEY not set")

    body = {
        "model": model or cfg["GROK_VID_MODEL"],
        "prompt": prompt,
        "video": video,
        "duration": duration,
    }
    submit_resp = _request("POST", "/videos/extensions", api_key, body=body)
    request_id = submit_resp.get("request_id")
    if not request_id:
        raise GrokImagineError(f"No request_id in response: {submit_resp}")
    if not poll:
        return submit_resp

    return _poll_video(
        request_id=request_id, prompt=prompt, cfg=cfg, api_key=api_key,
        poll_interval=poll_interval, poll_timeout=poll_timeout,
        operation="video_extend", params_summary=f"+{duration}s",
        model=body["model"],
    )


def _poll_video(
    *,
    request_id: str,
    prompt: str,
    cfg: dict,
    api_key: str,
    poll_interval: Optional[int],
    poll_timeout: Optional[int],
    operation: str,
    params_summary: str,
    model: str,
) -> dict:
    """Poll until done. Returns final response. Raises on failure or timeout."""
    interval = int(poll_interval if poll_interval is not None else cfg["GROK_VID_POLL_INTERVAL"])
    timeout = int(poll_timeout if poll_timeout is not None else cfg["GROK_VID_POLL_TIMEOUT"])

    waited = 0
    while waited < timeout:
        time.sleep(interval)
        waited += interval
        result = _request("GET", f"/videos/{request_id}", api_key, timeout=30)
        status = result.get("status", "?")
        if status == "done":
            cost_ticks = result.get("usage", {}).get("cost_in_usd_ticks", 0)
            log_cost(cfg, CostEntry(
                timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                operation=operation,
                model=model,
                params_summary=params_summary,
                cost_ticks=cost_ticks,
                request_id=request_id,
            ))
            video = result.get("video", {})
            if not video.get("respect_moderation", True):
                raise ModerationFiltered(request_id, prompt, cost_ticks)
            return result
        if status == "failed":
            raise VideoGenFailed(request_id, result.get("error", {}))
        if status == "expired":
            raise GrokImagineError(f"Video expired: {request_id}")
    raise PollTimeout(f"Video {request_id} did not complete within {timeout}s")


# ---------------------------------------------------------------------------
# Convenience: get-and-save in one call
# ---------------------------------------------------------------------------

def save_image_response(resp: dict, out_dir: Path, label: str = "image") -> list[Path]:
    """Download all images from an image-gen or image-edit response into out_dir."""
    saved: list[Path] = []
    for i, item in enumerate(resp.get("data", [])):
        suffix = f"-{i+1}" if len(resp["data"]) > 1 else ""
        if item.get("url"):
            ext = ".jpg"  # xAI returns JPEG as of May 2026
            dest = out_dir / f"{label}{suffix}{ext}"
            download(item["url"], dest)
            saved.append(dest)
        elif item.get("b64_json"):
            ext = ".jpg"
            dest = out_dir / f"{label}{suffix}{ext}"
            dest.write_bytes(base64.b64decode(item["b64_json"]))
            saved.append(dest)
    return saved


def save_video_response(resp: dict, out_dir: Path, label: str = "video") -> Path:
    """Download the video from a done video response."""
    url = resp.get("video", {}).get("url")
    if not url:
        raise GrokImagineError(f"No video URL in response: {resp}")
    dest = out_dir / f"{label}.mp4"
    download(url, dest)
    return dest


# ---------------------------------------------------------------------------
# Self-test (smoke check)
# ---------------------------------------------------------------------------

def whoami() -> dict:
    """Return /v1/api-key info — confirms the key works without spending."""
    cfg = load_config()
    key = cfg.get("XAI_API_KEY")
    if not key:
        raise AuthError("XAI_API_KEY not set")
    return _request("GET", "/api-key", key, timeout=30)


if __name__ == "__main__":
    # Smoke test: hit /v1/api-key
    info = whoami()
    print(f"OK — connected as team {info.get('team_id')} with key {info.get('redacted_api_key')}")
    print(f"ACLs: {info.get('acls')}")
