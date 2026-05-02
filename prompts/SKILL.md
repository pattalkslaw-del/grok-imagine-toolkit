---
name: video-prompt-builder
description: >-
  Build shot-by-shot prompts for Grok Imagine video generation. Use whenever
  the user wants to create a video prompt, plan a shot sequence, or turn a
  described scene into a structured generation-ready prompt. Trigger phrases
  include "video prompt," "shot list," "plan a video," "Grok video," "write
  me a prompt for [scene]," or any description of what should happen on
  screen in a short clip. This is the authoring layer; the execution layer
  is the parent grok-imagine toolkit.
---

# Video Prompt Builder, Grok Imagine

Turn a scene description into a shot-by-shot prompt structured for `grok-imagine-video`. Output is plain text the user (or an automated pipeline) can pass to `scripts/generate_video.py` in the parent toolkit.

This skill is the **authoring layer** that pairs with the parent `grok-imagine` toolkit's **execution layer**. Property skills (drunk-raccoon, plt-video, ptl-video, nlf-video, history-video) sit on top of this skill and lock character, voice, wardrobe, setting, and do-not-do lists for a specific creative property. Property skills are not part of this open-source toolkit; build your own when you have recurring brand constraints.

## Step 0: Route to a property skill if one applies

If the calling environment has registered property skills, hand off when a property keyword appears in the brief. Each property skill owns the constraints for that property and then invokes this skill with those constraints locked. If no property is registered or none matches, proceed with this skill directly.

## Grok Imagine technical constraints

- **Model:** `grok-imagine-video`
- **Endpoint:** `POST https://api.x.ai/v1/videos/generations`; poll `GET https://api.x.ai/v1/videos/{request_id}`
- **Duration:** integer seconds, 1 to 15 per clip
- **Aspect ratios:** `1:1`, `16:9`, `9:16`, `4:3`, `3:4`, `3:2`, `2:3`
- **Resolution:** `720p` or `480p`
- **Audio:** native; the model generates synchronized audio (ambient, SFX, dialogue, music) from the same prompt. Describe audio in the prompt; do not leave it implicit.
- **Modes:** text-to-video, image-to-video (one input image), reference-to-video (style/identity reference), video-to-video edit (input video max 8.7 seconds), video extend
- **Cost:** $0.05/sec at 480p, $0.07/sec at 720p; plus $0.002 per input image or $0.01 per input video. Verified May 2026. Recheck via the parent toolkit's edge test suite.
- **Auth:** `XAI_API_KEY`; see the parent toolkit's `.config.example` for the loader.

For deeper details on each endpoint and parameter, see `../references/api-shapes.md` in the parent toolkit. For character consistency across multiple clips, see `../references/character-consistency.md`.

## Prompting lessons from live use

1. **Describe sequential actions one at a time.** "He reaches in. Then he pulls out a fry. Then he eats it." beats "he reaches in and pulls out a fry and eats it." Grok resolves sequence better than concurrency.
2. **One primary action per second of clip.** A 6-second clip holds about 6 beats; a 15-second clip holds about 15. More than that collapses motion into incoherence.
3. **Subject + action + camera + lighting** in that order inside each shot block. Grok follows this structure better than free prose.
4. **Audio belongs in the prompt, not implied.** Name the diegetic cue (register beep, drive-thru speaker crackle, car alarm) and the ambient bed (parking-lot drone, fluorescent hum).
5. **One camera move per shot.** "Slow push in" or "pan left"; not both.
6. **Resolution trade-off:** 720p at $0.07/sec produces cleaner output but takes 30 to 60 seconds to generate. 480p at $0.05/sec iterates faster. Test at 480p, final at 720p.

## Input expectations

The user brief can include any combination of: subject, setting, mood, target duration, aspect ratio, specific effects or camera moves, reference to existing clips. If the brief is too thin to build from, ask one focused clarifying question. Make creative decisions where the user has not specified and note them at the end.

## Output structure

Always output all four sections in this order.

### Section 1: Shot-by-shot timeline

Each shot gets a block:

```
SHOT [N] ([timestamp]) [Shot name]
- SUBJECT/ACTION: [what happens, one primary action]
- CAMERA: [angle + one movement]
- LIGHTING: [source + quality]
- AUDIO: [ambient bed + any diegetic cue]
- EFFECT: [primary effect; stack only if intentional]
- TRANSITION: [how this shot exits into the next]
```

Shot length: 1 to 4 seconds default; longer holds only when the brief calls for them. Name effects precisely: "speed ramp (deceleration)" not "speed ramp"; "digital zoom (scale-in)" not "zoom." Describe the visual result, not the editing-software technique. Flag the most distinctive shot as `SIGNATURE SHOT`.

### Section 2: Master effects inventory

Numbered list of every distinct effect used, with count, shots it appears in, and one-line role description. Groups: speed manipulation, camera movement, digital effects, transitions, compositing, optical effects.

### Section 3: Effects density map

Break the clip into 3-to-6-second segments, rate each:

- `HIGH`: 4+ effects stacked or rapid-fire
- `MEDIUM`: 2 to 3 effects
- `LOW`: 1 effect or clean footage

Format: `[time range] = [DENSITY] ([effects list], [count] in [duration])`

### Section 4: Energy arc

Describe the clip energy structure as an arc. For clips of 6 seconds or less, a two-beat arc (setup, payoff). For 8 to 15 seconds, a three-beat arc (open, develop, resolve). For multi-clip sequences, scale accordingly.

## Creative principles

1. **Contrast drives impact.** Alternate high-density and low-density moments.
2. **Signature moments matter.** Every clip should have at least one hero effect or hero beat, called out explicitly.
3. **Transitions are shots.** Whip pans, bloom flashes, motion-blur smears are creative moments, not connective tissue.
4. **Specificity beats vagueness.** "Frame rotates clockwise about 15 degrees" beats "camera tilts." "About 20% speed" beats "slow motion."
5. **Energy resolves.** The final moment should feel intentional, not like the effects budget ran out.

## Tone

Write like director shot notes. Bullets inside shot blocks. Concise but complete. No hype adjectives (stunning, breathtaking, epic); describe what happens on screen and let the visual speak.

## Duration calibration

- 1 to 6 sec: 2 to 4 shots, one signature beat
- 7 to 10 sec: 5 to 8 shots, room for contrast
- 11 to 15 sec: 8 to 12 shots, full arc with 1 or 2 signature beats

Default to 8 seconds if the user does not specify; a reliable sweet spot for Grok Imagine in the middle of the pricing band.

## Reference

Read `references/effects-breakdown-reference.txt` before generating to calibrate detail level. The reference demonstrates the shot-block format, the density ratings, and the three-act arc on a 21-second kinetic edit study.

## Handoff to the execution layer

Once the shot list is written, the parent toolkit executes:

```bash
# Single clip from a shot list:
python3 ../scripts/generate_video.py --prompt "$(cat shot-list.txt)" --duration 8 --resolution 720p

# Multi-clip narrative longer than 15 seconds:
python3 ../scripts/hyperframe.py --shot-list shot-list.json
```

Cost-tracked via the parent toolkit's `cost_summary.py`.
