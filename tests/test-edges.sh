#!/usr/bin/env bash
# tests/test-edges.sh — Edge test suite for Grok Imagine API
#
# Re-run this quarterly or whenever something looks off in production. Tests
# every documented parameter and every known quirk from references/known-quirks.md.
#
# USAGE:
#   bash tests/test-edges.sh [--no-video] [--no-edit] [--quick]
#
# OPTIONS:
#   --no-video    skip video tests (saves ~$0.30, much faster)
#   --no-edit     skip image edit tests (saves ~$0.05)
#   --quick       skip all paid tests; only static/auth/config checks
#
# Estimated full-run cost: ~$0.50
#   - 1 auth/config check (free)
#   - 1 standard image gen (~$0.02)
#   - 1 image-pro gen (~$0.07)
#   - 1 image edit single (~$0.022)
#   - 1 image edit multi (~$0.024)
#   - 1 short T2V 480p (~$0.05)
#   - 1 short I2V 480p (~$0.052)
#   - 1 short R2V 480p (~$0.052)
#
# Output goes to /tmp/grok-imagine-tests/ — one JSON response per test.
# Pass/fail summary printed at the end.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$SCRIPT_DIR/scripts"
OUTDIR="${OUTDIR:-/tmp/grok-imagine-tests}"
mkdir -p "$OUTDIR"

NO_VIDEO=0
NO_EDIT=0
QUICK=0
for arg in "$@"; do
  case "$arg" in
    --no-video) NO_VIDEO=1 ;;
    --no-edit)  NO_EDIT=1 ;;
    --quick)    QUICK=1; NO_VIDEO=1; NO_EDIT=1 ;;
    --help|-h)
      sed -n '3,/^set/p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
  esac
done

PASS=0
FAIL=0
SKIP=0

ok()   { echo "  PASS  $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL  $1"; FAIL=$((FAIL + 1)); }
skip() { echo "  SKIP  $1"; SKIP=$((SKIP + 1)); }

# -----------------------------------------------------------------------------
# Test 1: auth + config
# -----------------------------------------------------------------------------
echo "=== Test 1: auth + config ==="
if python3 "$SCRIPTS/grok_client.py" > "$OUTDIR/01-auth.txt" 2>&1; then
  ok "auth /v1/api-key"
else
  fail "auth /v1/api-key"
  cat "$OUTDIR/01-auth.txt"
fi

# -----------------------------------------------------------------------------
# Test 2: model introspection (free)
# -----------------------------------------------------------------------------
echo ""
echo "=== Test 2: model introspection ==="
KEY="${XAI_API_KEY:-$(grep '^XAI_API_KEY' ~/.env 2>/dev/null | cut -d= -f2-)}"
if [ -z "$KEY" ]; then
  skip "model introspection (no XAI_API_KEY)"
else
  curl -sf -H "Authorization: Bearer $KEY" \
    https://api.x.ai/v1/image-generation-models > "$OUTDIR/02-img-models.json"
  if grep -q "grok-imagine-image" "$OUTDIR/02-img-models.json"; then
    ok "image-generation-models lists grok-imagine-image"
  else
    fail "image-generation-models response shape changed"
  fi

  curl -sf -H "Authorization: Bearer $KEY" \
    https://api.x.ai/v1/video-generation-models > "$OUTDIR/02-vid-models.json"
  if grep -q "grok-imagine-video" "$OUTDIR/02-vid-models.json"; then
    ok "video-generation-models lists grok-imagine-video"
  else
    fail "video-generation-models response shape changed"
  fi
fi

if [ "$QUICK" = "1" ]; then
  echo ""
  echo "=== --quick mode: skipping paid tests ==="
  echo ""
  echo "Summary: $PASS pass, $FAIL fail, $SKIP skip"
  [ "$FAIL" -eq 0 ] && exit 0 || exit 1
fi

# -----------------------------------------------------------------------------
# Test 3: image generation - standard model
# -----------------------------------------------------------------------------
echo ""
echo "=== Test 3: image generation (standard) ==="
if python3 "$SCRIPTS/generate_image.py" \
    "A simple geometric test pattern: red triangle, white background, minimalist" \
    --model grok-imagine-image \
    --resolution 1k \
    --aspect-ratio 1:1 \
    --label test-img-standard \
    --output-dir "$OUTDIR" \
    > "$OUTDIR/03-img-standard.txt" 2>&1; then
  if grep -q "Cost: \$0.02" "$OUTDIR/03-img-standard.txt"; then
    ok "image gen standard ($0.02)"
  else
    fail "image gen standard cost mismatch"
    cat "$OUTDIR/03-img-standard.txt"
  fi
else
  fail "image gen standard failed"
  cat "$OUTDIR/03-img-standard.txt"
fi

# -----------------------------------------------------------------------------
# Test 4: image generation - pro model
# -----------------------------------------------------------------------------
echo ""
echo "=== Test 4: image generation (pro) ==="
if python3 "$SCRIPTS/generate_image.py" \
    "Test pattern: blue circle, cream background, Bauhaus style" \
    --model grok-imagine-image-pro \
    --resolution 1k \
    --aspect-ratio 1:1 \
    --label test-img-pro \
    --output-dir "$OUTDIR" \
    > "$OUTDIR/04-img-pro.txt" 2>&1; then
  if grep -q "Cost: \$0.07" "$OUTDIR/04-img-pro.txt"; then
    ok "image gen pro ($0.07)"
  else
    fail "image gen pro cost mismatch (expected \$0.07)"
    cat "$OUTDIR/04-img-pro.txt"
  fi
else
  fail "image gen pro failed"
fi

# -----------------------------------------------------------------------------
# Test 5: image edit - single input
# -----------------------------------------------------------------------------
if [ "$NO_EDIT" = "0" ]; then
  echo ""
  echo "=== Test 5: image edit (single) ==="
  # Use the standard image we just generated
  STD_IMG=$(find "$OUTDIR" -name "image*.jpg" -path "*test-img-standard*" | head -1)
  if [ -z "$STD_IMG" ]; then
    skip "image edit single (no source image from Test 3)"
  else
    if python3 "$SCRIPTS/edit_image.py" \
        "Render this as a pencil sketch with crosshatching" \
        --image "$STD_IMG" \
        --label test-edit-single \
        --output-dir "$OUTDIR" \
        > "$OUTDIR/05-edit-single.txt" 2>&1; then
      # Cost should be ~$0.022 (base + 1 input)
      if grep -qE "Cost: \\\$0\.02[0-9]" "$OUTDIR/05-edit-single.txt"; then
        ok "image edit single (~\$0.022)"
      else
        fail "image edit single cost mismatch"
        cat "$OUTDIR/05-edit-single.txt"
      fi
    else
      fail "image edit single failed (likely JSON-vs-multipart regression)"
      cat "$OUTDIR/05-edit-single.txt"
    fi
  fi
else
  echo "=== Test 5: image edit single (skipped) ==="
  skip "image edit single (--no-edit)"
fi

# -----------------------------------------------------------------------------
# Test 6: image edit - multi-input <IMAGE_n> syntax
# -----------------------------------------------------------------------------
if [ "$NO_EDIT" = "0" ]; then
  echo ""
  echo "=== Test 6: image edit (multi-image <IMAGE_0>/<IMAGE_1>) ==="
  STD_IMG=$(find "$OUTDIR" -name "image*.jpg" -path "*test-img-standard*" | head -1)
  PRO_IMG=$(find "$OUTDIR" -name "image*.jpg" -path "*test-img-pro*" | head -1)
  if [ -z "$STD_IMG" ] || [ -z "$PRO_IMG" ]; then
    skip "image edit multi (need both Test 3 and Test 4 outputs)"
  else
    if python3 "$SCRIPTS/edit_image.py" \
        "Combine the shape from <IMAGE_0> with the color palette from <IMAGE_1>" \
        --images "$STD_IMG" \
        --images "$PRO_IMG" \
        --label test-edit-multi \
        --output-dir "$OUTDIR" \
        > "$OUTDIR/06-edit-multi.txt" 2>&1; then
      if grep -qE "Cost: \\\$0\.02[0-9]" "$OUTDIR/06-edit-multi.txt"; then
        ok "image edit multi (~\$0.024)"
      else
        fail "image edit multi cost mismatch"
        cat "$OUTDIR/06-edit-multi.txt"
      fi
    else
      fail "image edit multi failed"
      cat "$OUTDIR/06-edit-multi.txt"
    fi
  fi
else
  skip "image edit multi (--no-edit)"
fi

# -----------------------------------------------------------------------------
# Test 7: video generation - T2V (cheapest possible)
# -----------------------------------------------------------------------------
if [ "$NO_VIDEO" = "0" ]; then
  echo ""
  echo "=== Test 7: video gen T2V (5s 480p, ~\$0.25) ==="
  if python3 "$SCRIPTS/generate_video.py" \
      "A small flame flickering against a dark background, slow motion" \
      --duration 5 \
      --resolution 480p \
      --aspect-ratio 16:9 \
      --label test-t2v \
      --output-dir "$OUTDIR" \
      > "$OUTDIR/07-t2v.txt" 2>&1; then
    if grep -q "Cost: \$0.25" "$OUTDIR/07-t2v.txt"; then
      ok "video T2V (\$0.25)"
    else
      fail "video T2V cost mismatch"
      cat "$OUTDIR/07-t2v.txt"
    fi
  else
    fail "video T2V failed"
    cat "$OUTDIR/07-t2v.txt"
  fi
else
  skip "video T2V (--no-video)"
fi

# -----------------------------------------------------------------------------
# Test 8: video generation - I2V from Test 3 image
# -----------------------------------------------------------------------------
if [ "$NO_VIDEO" = "0" ]; then
  echo ""
  echo "=== Test 8: video gen I2V (5s 480p, ~\$0.252) ==="
  STD_IMG=$(find "$OUTDIR" -name "image*.jpg" -path "*test-img-standard*" | head -1)
  if [ -z "$STD_IMG" ]; then
    skip "video I2V (no source image)"
  else
    if python3 "$SCRIPTS/generate_video.py" \
        "Slow gentle pan from left to right" \
        --image "$STD_IMG" \
        --duration 5 \
        --resolution 480p \
        --label test-i2v \
        --output-dir "$OUTDIR" \
        --extract-frames \
        > "$OUTDIR/08-i2v.txt" 2>&1; then
      ok "video I2V (frames extracted)"
      # Verify both frames were extracted (tests last_frame -sseof workaround)
      I2V_DIR=$(dirname "$(find "$OUTDIR" -name "video.mp4" -path "*test-i2v*" | head -1)")
      if [ -f "$I2V_DIR/first.jpg" ] && [ -f "$I2V_DIR/last.jpg" ]; then
        ok "frame extraction (-sseof workaround)"
      else
        fail "frame extraction missing first.jpg or last.jpg"
      fi
    else
      fail "video I2V failed"
      cat "$OUTDIR/08-i2v.txt"
    fi
  fi
else
  skip "video I2V (--no-video)"
fi

# -----------------------------------------------------------------------------
# Test 9: video generation - R2V
# -----------------------------------------------------------------------------
if [ "$NO_VIDEO" = "0" ]; then
  echo ""
  echo "=== Test 9: video gen R2V (5s 480p, ~\$0.252) ==="
  PRO_IMG=$(find "$OUTDIR" -name "image*.jpg" -path "*test-img-pro*" | head -1)
  if [ -z "$PRO_IMG" ]; then
    skip "video R2V (no source image)"
  else
    if python3 "$SCRIPTS/generate_video.py" \
        "A new scene featuring this style, soft camera movement" \
        --reference-image "$PRO_IMG" \
        --duration 5 \
        --resolution 480p \
        --label test-r2v \
        --output-dir "$OUTDIR" \
        > "$OUTDIR/09-r2v.txt" 2>&1; then
      ok "video R2V"
    else
      fail "video R2V failed"
      cat "$OUTDIR/09-r2v.txt"
    fi
  fi
else
  skip "video R2V (--no-video)"
fi

# -----------------------------------------------------------------------------
# Test 10: stitch the I2V and R2V clips
# -----------------------------------------------------------------------------
if [ "$NO_VIDEO" = "0" ]; then
  echo ""
  echo "=== Test 10: stitch (validates ffmpeg + staging discipline) ==="
  I2V_MP4=$(find "$OUTDIR" -name "video.mp4" -path "*test-i2v*" | head -1)
  R2V_MP4=$(find "$OUTDIR" -name "video.mp4" -path "*test-r2v*" | head -1)
  if [ -z "$I2V_MP4" ] || [ -z "$R2V_MP4" ]; then
    skip "stitch (need both Test 8 and Test 9 outputs)"
  else
    if python3 "$SCRIPTS/stitch.py" \
        "$I2V_MP4" "$R2V_MP4" \
        --output "$OUTDIR/stitched.mp4" \
        > "$OUTDIR/10-stitch.txt" 2>&1; then
      if [ -s "$OUTDIR/stitched.mp4" ]; then
        SIZE=$(stat -c%s "$OUTDIR/stitched.mp4")
        ok "stitch (output ${SIZE} bytes)"
      else
        fail "stitch ran but output empty/missing"
      fi
    else
      fail "stitch failed"
      cat "$OUTDIR/10-stitch.txt"
    fi
  fi
else
  skip "stitch (--no-video)"
fi

# -----------------------------------------------------------------------------
# Test 11: cost summary parses log correctly
# -----------------------------------------------------------------------------
echo ""
echo "=== Test 11: cost summary parser ==="
if python3 "$SCRIPTS/cost_summary.py" --json > "$OUTDIR/11-cost-summary.json" 2>&1; then
  if grep -q '"total_usd"' "$OUTDIR/11-cost-summary.json"; then
    ok "cost summary parses log"
  else
    fail "cost summary output shape unexpected"
    cat "$OUTDIR/11-cost-summary.json"
  fi
else
  fail "cost summary failed to run"
fi

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo ""
echo "================================================================"
echo "Summary: $PASS pass, $FAIL fail, $SKIP skip"
echo "Test outputs in: $OUTDIR"
echo "Cost log: $(grep -c '^' "${GROK_COST_LOG:-$HOME/log/grok-imagine-cost.log}" 2>/dev/null || echo 0) total entries"
echo "================================================================"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
