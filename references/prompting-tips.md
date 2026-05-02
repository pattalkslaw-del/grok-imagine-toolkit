# Prompting Grok Imagine

What works on `grok-imagine-image` and `grok-imagine-video` specifically. Different prompt patterns work on different image models — what's documented here was verified live against xAI's models, not generic AI image lore.

For shot lists and structured video prompts, use whatever planning tool you prefer. This file covers prompting techniques that apply regardless of who or what authors the prompt.

---

## General principles

### Specificity beats vagueness, always

"A tank" → a tank.
"An M1 Abrams tank silhouetted against a dawn desert sky, photorealistic, dust on the horizon" → that exact tank in that exact lighting. Grok Imagine rewards prompt detail.

Rule of thumb: if a competing photographer would ask "what kind?" before taking the shot, the prompt is too vague.

### Anchor the surface for text

Text inside images works when the surface is named: chalkboard, neon storefront, paper menu, brick wall, embossed metal sign. The model decides typography from the surface.

```
hand-lettered chalkboard reading "TODAY: lobster roll $24"
```

The model resolves chalk lettering from "chalkboard."

### Quote text exactly

Anything in straight double quotes is treated as literal text:

```
A vintage tin sign with the words "EAT MORE BEEF" in red serif type
```

Don't paraphrase. Quote.

### Camera language

Grok Imagine responds to specific camera/lens language:

- `eye-level shot`, `low angle`, `overhead`, `dutch angle`
- `35mm lens`, `85mm portrait lens`, `wide angle`, `macro`
- `shallow depth of field`, `deep focus`
- `golden hour lighting`, `overcast diffused light`, `harsh midday sun`

These work better than artistic terms like "cinematic" or "epic" — describe the photographic conditions, not the vibe.

### Avoid hype adjectives

"Stunning, breathtaking, ultra-detailed, masterpiece" is noise. The model is already trying to make a good image. These tokens dilute the actual content.

---

## For images specifically

### Multi-element layouts

For posters, infographics, or app mockups with multiple labeled elements, structure the prompt as JSON-like keys:

```
{
  "type": "social media poster",
  "header": "PRODUCT LAUNCH EVENT",
  "subhead": "Free online, register today",
  "footer": "Register at example.com/event",
  "layout": "centered, navy and cream palette, serif headline",
  "imagery": "stylized illustration of an open book with a quill pen"
}
```

Grok Imagine maps the keys to layout regions better than it parses the same content as prose. Use this for any image where placement matters.

### Style transfer

`grok-imagine-image` handles a wide range of styles. Either as part of the prompt or in an edit:

- `oil painting in the style of impressionism`
- `pencil sketch with detailed shading`
- `pop art with bold colors and halftone dots`
- `anime, soft cel-shading`
- `watercolor with soft edges and visible paper texture`
- `1970s film still, warm grain, slight vignette`

Be more specific than "make it artistic" — name the medium.

### What grok-imagine-image handles well

- Text in images (best-in-class as of Imagine's release)
- Photorealism, product photography, editorial
- Style transfer (any specific style; less reliable for "vague mood")
- Complex multi-element layouts
- Identity preservation across n=4 batch outputs
- Identity preservation in single-image edits

### What grok-imagine-image handles poorly

- Long paragraphs of body text → use the graphic fall-back pattern instead
- Strict pixel preservation across edits — it interprets, doesn't copy
- Hyper-specific brand logos or copyrighted characters (refuses or distorts)
- Mathematical/scientific diagrams with precise relationships

---

## For video specifically

### One primary action per second of clip

A 6-second clip holds about 6 beats. A 15-second clip holds about 15. More than that and motion collapses into incoherence.

Bad: "A man walks into the cafe, orders coffee, sits down, opens his laptop, types for a moment, looks up, smiles at someone, takes a sip, then closes the laptop."

Good (8s clip): "A man walks into the cafe and orders coffee at the counter."

### Sequential, not concurrent

Grok resolves "first this, then this, then this" better than "this and this and this all at once."

Bad: "She walks while reading a book and drinking coffee and looking around."

Good: "She walks slowly forward. She glances down at the book in her left hand. Her right hand brings the coffee cup to her lips."

### Camera moves: one per shot

Bad: "Slow push in with a pan left."

Good: "Slow push in." (Or, in a different shot, "Pan left.")

### Audio belongs in the prompt

Grok Imagine generates synchronized audio from the same prompt that generates video. Describe the audio explicitly:

- Diegetic cue: register beep, drive-thru speaker crackle, car door slamming, footsteps on cobblestone
- Ambient bed: parking-lot drone, fluorescent hum, distant cafe chatter, gentle breeze, ocean waves at distance

Without audio direction the model picks something — usually fine, sometimes generic. With direction the audio matches the action.

### Subject + Action + Camera + Lighting + Audio

In each shot block, that order works best:

```
A woman in a copper-red braid stands by a stone fountain.
She turns her head slowly to look over her right shoulder.
The camera is at eye level, three meters back.
Late afternoon golden hour, warm side-light from frame right.
Distant cafe chatter, a fountain trickle, soft breeze.
```

### Resolution choice for iteration

- Iterate at **480p**: $0.05/sec, ~20-second wall-clock for 5-second clips. Cheap and fast.
- Final at **720p**: $0.07/sec, ~40-60 second wall-clock for 5-second clips. Cleaner output.

Grok Imagine's 720p is genuinely better than its 480p — not just resolution. Texture, lighting, and motion coherence all step up. Worth the markup for production work.

### Duration sweet spots

| Duration | Use case |
|----------|----------|
| 1-3 sec | Single-action GIF replacement, transitions, B-roll |
| 5 sec | Default for iteration; quick beats |
| 8 sec | Default for production; room for arc |
| 10-12 sec | Full scene with setup-develop-resolve |
| 15 sec (max) | Capping clip; chain via hyperframe for longer |

The model holds 8 seconds well. 15-second clips occasionally lose coherence in the middle; reserve for clips where the full 15 is genuinely needed.

---

## Authoring multi-clip pieces

For any video request that needs more than one clip, plan it before generating:
1. A shot-by-shot timeline (one beat per clip, 5-15s each)
2. A master effects inventory (what's in shot, what changes between shots)
3. An effects density map (which beats carry the heavy lifting)
4. An energy arc (where the piece rises, peaks, resolves)

The output of that planning becomes the `beats.json` input to this skill's `hyperframe.py`. See `examples/05-hyperframe-30s.md` for the schema.

---

## Edits — preserve vs reinterpret

When editing an image, be explicit about what stays the same. The model defaults to interpretation, not preservation.

Bad: "Make her smile."

Good: "She is now smiling. Same face, same hair, same jacket, same plaza setting. Only the expression changes."

For tightest preservation across an edit, use the multi-image pattern with explicit identity reference:

```json
{
  "prompt": "Show <IMAGE_0> with a slight smile. Preserve all other features exactly: face structure, hair, freckles, jacket, t-shirt, pose. Only the mouth changes.",
  "images": [{"url": "https://anchor.jpg"}]
}
```

The `<IMAGE_0>` reference + explicit "preserve" language gives the strongest identity lock available in single-call edits.

---

## When prompts get filtered

If a generation comes back with `respect_moderation: false` (videos) or 400/policy errors (images), the prompt triggered xAI's content filter. Common causes:

- Real named public figures
- Branded IP (Disney, Marvel, named athletes)
- Anything sexual or suggestive
- Graphic violence
- Children in unsafe scenarios

The skill helpers raise an explicit `ModerationFiltered` exception when this happens — they don't return an empty result. Adjust the prompt and re-submit.

If a benign prompt repeatedly filters (e.g. "Civil War era soldier" gets caught for "violence"), reword around the trigger word: "Union infantry uniform, 1863 reenactor portrait, not in combat." The filter looks at words, not intent.
