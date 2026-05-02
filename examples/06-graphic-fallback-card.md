# Example 06: Graphic fall-back — text-heavy social card

> **Path note:** in shell commands `~/foo` works because the shell expands `~`. In CSS `url()`, JS string literals, and `file://` URLs the tilde does NOT expand — substitute the absolute path of your working directory wherever you see `/ABS/PATH/TO/`.


For images that need real typography (body text, multiple labeled regions, dense layouts), don't fight the model. Generate the background only, composite text in HTML+CSS, render with headless Chromium.

This is the same pattern as `openai-image`'s text-heavy composites. It works because Imagine renders short text well but degrades on body copy; HTML+CSS gives pixel-perfect typography for everything.

## Use case

A 1200×630 social card for a marketing event:
- Background: a stylized estate planning illustration (vague, atmospheric)
- Foreground text: headline ("Free Estate Planning Webinar"), subhead with date/time, footer with the registration URL

Asking Imagine to render all that text gets you wrapping artifacts and unreadable kerning. HTML gets you typeset perfection.

## Step 1: Generate the background

```bash
python3 scripts/generate_image.py \
  "A modern law office at golden hour, warm interior lighting, tall windows overlooking a city skyline, an empty leather chair in the foreground, books on shelves in the background, professional and inviting tone, photorealistic, shallow depth of field. Empty negative space in the upper-left third of the frame for text overlay, plain darker wall, no decorative elements in that region." \
  --model grok-imagine-image-pro \
  --resolution 2k \
  --aspect-ratio 16:9 \
  --label event-card-bg
```

`$0.070` for the pro model at 2k. Worth it; this image is the foundation of a marketing piece.

The "empty negative space ... no decorative elements in that region" language is what tells the model to leave room for the overlay. Without it the model fills the frame.

## Step 2: HTML composite

Save as `~/work/event-card.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Webinar Card</title>
<style>
  body {
    margin: 0;
    padding: 0;
    width: 1200px;
    height: 630px;
    position: relative;
    background-image: url('/ABS/PATH/TO/grok-imagine-output/{TIMESTAMP}-t2i-event-card-bg/image.jpg');
    background-size: cover;
    background-position: center;
    font-family: Georgia, "Times New Roman", serif;
    color: #fff;
  }
  .overlay {
    position: absolute;
    top: 60px;
    left: 80px;
    max-width: 580px;
    text-shadow: 0 2px 12px rgba(0, 0, 0, 0.85);
  }
  .eyebrow {
    text-transform: uppercase;
    letter-spacing: 0.15em;
    font-size: 14px;
    color: #f4d4a3;
    margin: 0 0 18px;
    font-weight: 600;
  }
  h1 {
    font-size: 56px;
    line-height: 1.05;
    margin: 0 0 28px;
    font-weight: 700;
    letter-spacing: -0.01em;
  }
  .meta {
    font-size: 22px;
    line-height: 1.45;
    margin: 0 0 36px;
    font-weight: 400;
  }
  .footer {
    position: absolute;
    bottom: 50px;
    left: 80px;
    right: 80px;
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    font-size: 18px;
    color: rgba(255, 255, 255, 0.85);
  }
  .url { font-weight: 600; color: #f4d4a3; }
</style>
</head>
<body>
  <div class="overlay">
    <p class="eyebrow">Free Public Webinar</p>
    <h1>Your Headline,<br>Right Here.</h1>
    <p class="meta">Thursday, June 12 at 7:00 PM Central<br>Online, free, 45 minutes plus Q&amp;A</p>
  </div>
  <div class="footer">
    <span>Your Company &middot; Your City, ST</span>
    <span class="url">register at example.com/event</span>
  </div>
</body>
</html>
```

Replace `{TIMESTAMP}` with the actual output folder name.

## Step 3: Render with headless Chromium

Most Linux servers have Node and can run Puppeteer. Save as `~/work/render-card.js`:

```javascript
import puppeteer from 'puppeteer';

const browser = await puppeteer.launch({ args: ['--no-sandbox'] });
const page = await browser.newPage();
await page.setViewport({ width: 1200, height: 630, deviceScaleFactor: 2 });
await page.goto('file:///ABS/PATH/TO/event-card.html', { waitUntil: 'networkidle0' });
await page.screenshot({
  path: '/ABS/PATH/TO/event-card.png',
  type: 'png',
  clip: { x: 0, y: 0, width: 1200, height: 630 },
});
await browser.close();
console.log('Rendered to /ABS/PATH/TO/event-card.png');
```

Run:

```bash
node --input-type=module ~/work/render-card.js
```

Output: `event-card.png` at 2400×1260 (retina). The text is real typography; the background is the Imagine output. Edit the text in the HTML and re-render — no need to regenerate the image.

## Templating for series

Once you've built one card, the next ten are nearly free. Parameterize the HTML:

```javascript
async function renderCard({ eyebrow, headline, meta, footerLeft, footerUrl, output }) {
  const html = template
    .replace('{{EYEBROW}}', eyebrow)
    .replace('{{HEADLINE}}', headline)
    .replace('{{META}}', meta)
    .replace('{{FOOTER_LEFT}}', footerLeft)
    .replace('{{FOOTER_URL}}', footerUrl);
  // ... render
}

await renderCard({
  eyebrow: 'Free Public Webinar',
  headline: 'Estate Planning,<br>Done Right.',
  meta: 'Thursday, June 12 at 7:00 PM Central<br>Online, free',
  footerLeft: 'Your Company',
  footerUrl: 'register at example.com/event',
  output: 'webinar-jun-12.png',
});
```

Templating math: a year of weekly social cards from one background = `$0.07 + 52 × ~free` instead of 52 image generations at `$0.07` each.

## When NOT to use this pattern

- Short text baked into the scene (chalkboards, neon signs, hand-painted murals) — keep it in the prompt; Imagine renders these well
- Text that interacts with scene elements (speech bubbles, arrows, pointers) — keep in the prompt or move to a 3D / illustration tool
- One-off announcements where typography control isn't the priority — direct generation is faster

## Common pitfalls

- **Forgetting to leave space in the background.** If you don't tell the model "empty negative space in upper-left third," it fills the frame and your text overlaps faces or important detail
- **Background image path in HTML uses a relative path that breaks.** Use absolute paths (`file:///` URLs in `goto`, absolute paths in `background-image`) when running headless
- **Forgetting `deviceScaleFactor: 2`** for retina output. Renders look soft on modern displays without it
- **Using web fonts loaded over the network without `waitUntil: 'networkidle0'`** — the screenshot fires before fonts load, falling back to system fonts
