# Example 02: Multi-image merge with `<IMAGE_0>` / `<IMAGE_1>` syntax

Compose a known character into a different scene, pose, or wardrobe. The strongest pattern available for "this person, that setting."

## Use case

You have a character anchor (a generated photo or reference) and you want them placed in a new context — a different room, a different outfit, a different posture. You don't want a vague "averaged" composition; you want the specific identity from your anchor to land in the specific scene from your second reference.

## Command

```bash
python3 scripts/edit_image.py \
  "Show the woman from <IMAGE_0> sitting on the leather chair in <IMAGE_1>. \
Preserve her face, hair, freckles, and clothing exactly from <IMAGE_0>. \
Use the lighting and atmosphere of <IMAGE_1>." \
  --images ~/work/character-anchor.jpg \
  --images ~/work/library-scene.jpg \
  --label character-in-library
```

## What happens

1. Both local files are auto-encoded as base64 data URIs and posted to `/v1/images/edits`
2. The model resolves `<IMAGE_0>` and `<IMAGE_1>` as positional references to the two array entries
3. Cost: `$0.020` base + `$0.002` per input × 2 = `$0.024`
4. Output saved to `$GROK_OUTPUT_ROOT/{timestamp}-edit-character-in-library/edit.jpg`

## Why the prompt language matters

| Prompt phrasing | Result |
|---|---|
| "Combine these two images" | Vague — model averages features. Identity drifts. |
| "Show the woman from `<IMAGE_0>` in `<IMAGE_1>`" | Decent — but doesn't tell the model what to preserve |
| "Show the woman from `<IMAGE_0>` ... Preserve her face, hair, freckles, clothing exactly from `<IMAGE_0>`" | **Strongest** — explicit preservation directive locks identity |

The skill's prompt examples in `references/prompting-tips.md` codify this. When in doubt, name what to preserve and from which `<IMAGE_n>`.

## What `<IMAGE_1>` should look like

Lesson from the live test runs: if `<IMAGE_1>` is supposed to provide a **pose**, it must contain a person in that pose. An empty room used as `<IMAGE_1>` works as a setting reference, not a pose reference.

| You want IMAGE_1 to provide | IMAGE_1 must contain |
|---|---|
| A setting / environment | The empty space (no person needed) |
| A pose | A person in that pose |
| Wardrobe | A garment or person wearing it |
| Lighting style | A scene with that lighting |

## Three-image case

You can pass up to 5 images. Useful for character + pose + setting:

```bash
python3 scripts/edit_image.py \
  "Show the woman from <IMAGE_0> in the pose of <IMAGE_1> in the setting of <IMAGE_2>. \
Preserve face and hair from <IMAGE_0>. Match the body angle of <IMAGE_1>. \
Use the lighting and decor of <IMAGE_2>." \
  --images character.jpg \
  --images pose-reference.jpg \
  --images library-scene.jpg \
  --label character-pose-library
```

Cost: `$0.020 + 3 × $0.002 = $0.026`.

## Common pitfalls

- Mixing `--image` (singular) and `--images` (plural) — they're mutually exclusive. Use one
- More than 5 images — API rejects
- Forgetting the angle brackets — `IMAGE_0` without `<>` won't be recognized as a reference token
- Local file paths that don't exist — script fails fast with `FileNotFoundError`
