# Graphic fall-back — text-heavy images

When an image needs more than a short sign or label — body copy, multiple headlines, captions, dense data, legal disclaimers — don't ask Grok Imagine to render the text. The model handles short strings well but degrades on body text (wrapping, spacing, legibility, multi-line layout).

Mirrors `openai-image`'s Text-Heavy Composites pattern. Same justification, same toolchain.

---

## The pattern

1. **Generate the background.** Strip text mentions from the prompt; ask Grok Imagine for the scene, illustration, or photo only.
2. **Composite text in HTML+CSS.** The generated image becomes the CSS background; text is real HTML with full typographic control.
3. **Export to PNG via headless Chromium.** Puppeteer or Playwright renders the page at the target dimensions and captures a screenshot.

---

## Why this beats fighting the model

Grok Imagine's text rendering is best-in-class as of May 2026 for **short** text (signs, chalkboards, menus, posters with up to ~10 words). For longer text:

- Wrapping is unpredictable
- Spacing degrades with line count
- Multi-paragraph copy goes wrong fast
- Editing the text means regenerating the whole image (and getting a different background)
- Localizing for another language means regenerating from scratch

HTML+CSS gives:
- Pixel-perfect typography
- Editable text without regenerating the image
- Templated output for series (newsletter, daily card, weekly poster)
- Localization without regenerating
- Real fonts (any TTF/OTF you have), real spacing, real kerning

The cost trade-off: one extra step (~30 seconds to write the HTML), but the time saved iterating dwarfs that.

---

## Step 1: Background-only generation

Write the prompt as if there's no text at all. The model will render a clean composition without trying to invent text.

```
A modern law office at golden hour, warm interior lighting, tall windows
overlooking a city, leather chair empty in the foreground, books on shelves
behind, professional and inviting tone, photorealistic, shallow depth of field
```

Save to `$GROK_OUTPUT_ROOT/{run_id}/background.jpg`.

If the background needs space for text overlay, prompt for it explicitly:

```
A modern law office at golden hour... empty negative space in the upper-left
third of the frame for text overlay, plain dark wall, no decorative elements
in that region.
```

---

## Step 2: HTML composite

Single-file HTML. Background image referenced via `file://` for local files or `https://` for remote.

```html
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @font-face {
    font-family: 'Trajan';
    src: url('/path/to/Trajan.otf') format('opentype');
  }
  body {
    margin: 0;
    padding: 0;
    width: 1200px;
    height: 630px;
    position: relative;
    background: url('background.jpg') center/cover no-repeat;
    font-family: Georgia, serif;
  }
  .overlay {
    position: absolute;
    top: 60px;
    left: 80px;
    right: 80px;
    color: #fff;
    text-shadow: 0 2px 8px rgba(0, 0, 0, 0.7);
  }
  h1 {
    font-family: 'Trajan', Georgia, serif;
    font-size: 56px;
    line-height: 1.1;
    margin: 0 0 24px;
    letter-spacing: 0.02em;
  }
  p {
    font-size: 22px;
    line-height: 1.5;
    margin: 0;
    max-width: 720px;
  }
</style>
</head>
<body>
  <div class="overlay">
    <h1>Your Headline,<br>Right Here.</h1>
    <p>Concise marketing copy describing the offering. Two to three lines
    works well for social card layouts. Replace with your own.</p>
  </div>
</body>
</html>
```

Standard CSS rules apply. Use `:before/:after` for graphic accents, gradients for overlay shading, `aspect-ratio` for responsive composition.

---

## Step 3: Render to PNG with headless Chromium

Use Puppeteer (Node.js) or Playwright (Node.js or Python). Both work. Pick whichever your environment has.

### Puppeteer

```javascript
import puppeteer from 'puppeteer';

async function compositeToPNG({ htmlPath, outputPath, width, height }) {
  const browser = await puppeteer.launch({ args: ['--no-sandbox'] });
  const page = await browser.newPage();
  await page.setViewport({
    width,
    height,
    deviceScaleFactor: 2,    // 2x for retina output
  });
  await page.goto(`file://${htmlPath}`, { waitUntil: 'networkidle0' });
  await page.screenshot({
    path: outputPath,
    type: 'png',
    clip: { x: 0, y: 0, width, height },
  });
  await browser.close();
}

await compositeToPNG({
  htmlPath: '/ABS/PATH/TO/card.html',
  outputPath: '/ABS/PATH/TO/card.png',
  width: 1200,
  height: 630,
});
```

### Playwright (Python)

```python
from playwright.sync_api import sync_playwright

def composite_to_png(html_path, output_path, width, height):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=2,
        )
        page = ctx.new_page()
        page.goto(f"file://{html_path}", wait_until="networkidle")
        page.screenshot(path=output_path, type="png", full_page=False)
        browser.close()

composite_to_png(
    "/ABS/PATH/TO/card.html",
    "/ABS/PATH/TO/card.png",
    1200, 630,
)
```

---

## When to use this pattern

- Social cards, thumbnails, ad creative with headline + body copy
- Newsletter top images with multiple labeled regions
- Infographics with labels, annotations, data callouts
- Posters or flyers with body text
- Legal disclaimer cards (where typography matters as much as content)
- Templated outputs where text changes often but background stays
- Multi-language outputs from one background

## When NOT to use it

- Short text baked into a visual scene (chalkboards, neon signs, painted murals) — keep it in the prompt; Grok handles this well
- Text that is stylistically part of the art (hand-lettered, embossed, painted, engraved) — keep it in the prompt
- Text that must interact with scene elements (speech bubbles, arrows pointing at objects, labels on a 3D-rendered diagram) — keep it in the prompt OR use a 3D/illustration tool
- Single-line announcements where typography control isn't needed

---

## Templating for series production

For a newsletter, weekly card, or any output where the structure repeats but content changes:

1. Build one background image (or a small library of seasonal backgrounds)
2. Author HTML as a template with variables (Mustache, Jinja, or just JS template strings)
3. Run a render script that fills the template, exports PNG, names the output

The skill ships `examples/06-graphic-fallback-card.md` showing this end-to-end for a social card.

---

## Live local rendering vs server rendering

Most Linux environments with Node.js can run Puppeteer or Playwright headlessly. For high-volume production, consider an HTML-to-PDF service. For ad-hoc work, run Puppeteer locally.

The skill's `examples/06-graphic-fallback-card.md` runs locally on a server with snap-installed ffmpeg.
