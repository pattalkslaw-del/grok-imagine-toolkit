# Pricing — Grok Imagine, May 2026

xAI returns the exact cost of every request in `usage.cost_in_usd_ticks`. The skill logs this verbatim to `$GROK_COST_LOG`. Reconcile against your xAI Console billing page if anything disagrees.

## The tick unit

```
1 USD = 10,000,000,000 ticks (10^10)
1 tick = $0.0000000001
```

To convert: `dollars = ticks / 1e10`. Examples:
- `200000000` ticks = $0.02
- `220000000` ticks = $0.022
- `700000000` ticks = $0.07
- `2500000000` ticks = $0.25
- `2520000000` ticks = $0.252

## Verified rates (May 2026)

### Image generation

| Model | Per-image | Notes |
|-------|-----------|-------|
| `grok-imagine-image` | $0.020 | 8000-char prompt limit |
| `grok-imagine-image-pro` | $0.070 | 10000-char prompt limit, higher fidelity |

Verified live: a single `grok-imagine-image` call returned `cost_in_usd_ticks: 200000000` exactly.

### Image editing

| Operation | Cost | Math |
|-----------|------|------|
| Edit with 1 input image | $0.022 | $0.020 base + $0.002 per input |
| Edit with 2 input images | $0.024 | $0.020 base + $0.004 (2 × $0.002) |
| Edit with 5 input images (max) | $0.030 | $0.020 base + $0.010 (5 × $0.002) |

### Video generation

Per-second of OUTPUT video:

| Resolution | Per-second | 5-sec clip | 8-sec clip | 15-sec clip |
|------------|-----------|------------|------------|-------------|
| 480p | $0.05 | $0.25 | $0.40 | $0.75 |
| 720p | $0.07 | $0.35 | $0.56 | $1.05 |

I2V/R2V add ~$0.002 per input image. Edit/extend add ~$0.01 per input video.

Verified live: 5-second 480p T2V returned `cost_in_usd_ticks: 2500000000` ($0.250 exactly). 5-second 480p I2V returned `2520000000` ($0.252 — base + ~$0.002 per the rate table).

## Batch API and image/video generation

xAI's Batch API offers 20-50% off token-based models for asynchronous processing. **Image and video generation are NOT discounted in batch mode.** They run through the batch infrastructure but bill at standard rates. Per the xAI docs page on batch.

## Worked cost examples

### Single hero image
```
1 × image-pro 1k                    = $0.070
```

### 4-variation menu
```
4 × image standard 1k (n=4)         = $0.080  (single request, n=4)
```

### Hyperframe 30-second piece
```
4 keyframes (image-pro)             = $0.280  (4 × $0.070)
4 × 8-sec I2V clips (720p)          = $2.240  (4 × $0.560)
                                    = $2.520
```

### Hyperframe 60-second piece
```
8 keyframes (image-pro)             = $0.560
8 × 8-sec I2V clips (720p)          = $4.480
                                    = $5.040
```

Iterate at 480p for ~30% savings; lock final at 720p.

### Iteration discipline

The cheapest path to any final output:
1. Story-board with **n=4 image standard** ($0.08 per attempt) until composition lands
2. Lock anchor with one **image-pro** call ($0.07)
3. Test motion with **5-second 480p T2V or I2V** ($0.25 per attempt)
4. Final at **8-second 720p** ($0.56 per attempt)

A typical 30-second hyperframe piece, with 2-3 iteration attempts at each stage:
```
Storyboard:    3 × $0.08  = $0.24
Anchors:       4 × $0.07  = $0.28
Motion tests:  6 × $0.25  = $1.50  (1.5 attempts per beat × 4 beats)
Final clips:   4 × $0.56  = $2.24
                          = $4.26 total for a polished 30-second video
```

Compare to commissioning a 30-second motion piece from a freelancer ($500-$2,000 in 2026 market rates) and Grok Imagine's economics make sense even with iteration.

## When the cost log disagrees with a billing dashboard

The cost log is per-request. xAI's console aggregates by team and may include monthly minimums, retainers, or subscription components not visible in per-request pricing. Reconciliation between `$GROK_COST_LOG` and console should match to within a few percent on raw API usage; anything beyond that means look at console for non-API line items.
