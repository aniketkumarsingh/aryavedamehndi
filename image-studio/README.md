# Image Studio

Makes a set of photos look like one shoot. It scores each photo, finds the
subject, frames it the same way every time, matches colour and exposure to a
reference look, and puts the subject on one shared backdrop. You can use it as
a Python library, a CLI, an HTTP API, or a drop-in web component on any
website.

```
load ─▶ subject mask (AI) ─▶ analyse ─▶ frame ─▶ colour & exposure ─▶ local contrast
     ─▶ denoise ─▶ sharpen ─▶ background (keep / soften / replace) ─▶ watermark ─▶ report
```

## What it does, and what it won't do

| Problem | What Image Studio does |
|---|---|
| Different backgrounds | `replace`: subject on one backdrop with a soft contact shadow. `soften`: keep the real background but blur, desaturate and tint it. |
| Different framing and aspect ratios | Crops around the subject to one aspect ratio. Where a hand or foot runs off the photo, that side stays on the edge so it doesn't float. |
| Colour casts, dark or bright photos | Matches the subject's colour and brightness to reference photos (`calibrate`), or auto white balance without a reference. |
| Flat detail, noise | Local contrast (CLAHE), adaptive denoise, luminance-only sharpening. |
| Large files, EXIF/GPS data | sRGB output with metadata stripped. Optional extra sizes in WebP. |

Some problems need a reshoot. **Blur and low resolution** get sharpened as well
as possible, but the report keeps flagging them, so a "100" score never hides
them. The blur check looks only at the design's edges and is tuned to catch
clear blur without false alarms on minimal designs. It can miss mild softness,
so have a person look at anything that matters. The tool never repaints parts of the subject (for example, wet henna paste
stays as it is). Colour correction is global, so the photo stays truthful.

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[ai,server]"      # drop [ai] to use the built-in heuristic masks only
```

The AI mask model downloads on first use: `birefnet-general`, about 900 MB,
cached in `~/.rembg`.

| `mask.model` | Speed (CPU, per photo) | Quality |
|---|---|---|
| `birefnet-general` (default) | ~15 s | Best: keeps whole forearms and feet, drops props and fabric |
| `isnet-general-use` | ~1.5 s | Often loses forearms and feet, and leaves props in |

## CLI

```bash
image-studio presets
image-studio analyze photos/                         # score + issues for each photo, plus how uniform the set is
image-studio process photos/ -o out/ --preset studio-warm --sheet
image-studio process a.jpg -o out/ --preset product-white --set background.color=#F7F7F7 --set output.format=webp
image-studio calibrate best1.jpg best2.jpg --preset studio-warm -o my-look.json   # "make everything look like these"
image-studio serve --port 8100
```

`process` writes the images, any extra sizes, `report.json` (per-photo report
plus set uniformity before and after) and, with `--sheet`, `before-after.jpg`.

## Presets

Presets are JSON files. Each one extends another preset or the defaults, so it
only needs to list what differs. Unknown keys are rejected, so typos fail
loudly. Keys that start with `_` are comments. Put your own presets in a folder
and point `IMAGE_STUDIO_PRESETS_DIR` at it.

```json
{
  "name": "my-shop",
  "description": "Products on brand cream, square 1600px",
  "extends": "studio-warm",
  "output": { "width": 1600, "height": 1600, "format": "jpeg", "quality": 88,
              "renditions": [{ "suffix": "-800", "width": 800, "format": "webp" }] },
  "framing": { "mode": "subject", "margin": 0.06 },
  "background": { "mode": "replace", "color": "#FBF6EC", "color2": "#F3EAD9", "shadow": 0.1 },
  "color": { "reference": { "L": 74.6, "L_median": 65, "L_std": 14.7, "a": 12.3, "b": 11.6, "chroma": 18.4 } }
}
```

Built-in presets: `default` (colour fixes only), `product-white`,
`studio-warm`, `natural-soft` and `social-portrait`. Every setting and its
default is listed in [`image_studio/config.py`](image_studio/config.py).

## HTTP API

| Endpoint | |
|---|---|
| `GET /health` | status, and whether AI masks are available |
| `GET /v1/presets` | preset names and summaries |
| `POST /v1/analyze` | form: `file`, `preset` → JSON report |
| `POST /v1/process` | form: `file`, `preset`, `options` (JSON overrides); query: `format`, `width`, `height`, `response=image\|json` |

With `response=image` (the default) you get the image bytes plus
`X-Image-Studio-Score`, `-Issues` and `-Fixed` headers. With `response=json`
you get `{ image: dataURL, width, height, report }`.

```bash
curl -F file=@hand.jpg -F preset=studio-warm "http://localhost:8100/v1/process?format=webp" -o hand.webp
```

| Environment variable | |
|---|---|
| `IMAGE_STUDIO_API_KEYS` | comma-separated keys. When set, every `/v1` call needs `X-API-Key`. |
| `IMAGE_STUDIO_CORS_ORIGINS` | sites allowed to call the API from the browser. Default: none. |
| `IMAGE_STUDIO_MAX_MB` | upload limit (default 25) |
| `IMAGE_STUDIO_CONCURRENCY` | photos processed at once (default 2; each one uses several CPU cores) |
| `IMAGE_STUDIO_PRESETS_DIR` | extra preset folder(s) |

### Docker

```bash
docker build -t image-studio .                       # bakes the AI model into the image
docker run -p 8100:8100 -v $PWD/presets:/presets -e IMAGE_STUDIO_PRESETS_DIR=/presets \
  -e IMAGE_STUDIO_CORS_ORIGINS=https://www.example.com image-studio
```

## Add it to any website

```html
<script type="module" src="https://studio.example.com/widget/image-studio.js"></script>

<image-studio endpoint="https://studio.example.com" preset="studio-warm" target="#photo"></image-studio>
<input type="file" id="photo" name="photo" hidden>  <!-- your existing upload form field -->
```

Users drop a photo, press **Enhance**, compare before and after (a slider when
the framing is unchanged, side by side when it changed), see the quality score
and what was fixed, then **Download** or **Use this photo**. Use this photo
puts the enhanced file into your form's file input and fires `change`, so an
existing upload form works unchanged.

| | |
|---|---|
| Attributes | `endpoint`, `preset` (omit to show a picker), `presets` (limit the picker), `target`, `format`, `api-key` |
| Events | `image-studio:result`, `image-studio:use`, `image-studio:error` |
| Theming | `--is-accent`, `--is-accent-text`, `--is-surface`, `--is-text`, `--is-muted`, `--is-border`, `--is-radius`, `--is-font` |

Without the UI:

```js
import { ImageStudioClient } from "https://studio.example.com/widget/image-studio.js";
const { file, report } = await new ImageStudioClient({ endpoint: "https://studio.example.com" })
  .process(input.files[0], { preset: "product-white", format: "webp" });
```

**Keys in the browser are public.** For a public site, leave
`IMAGE_STUDIO_API_KEYS` unset, restrict `IMAGE_STUDIO_CORS_ORIGINS` to your
domain, and rate-limit at your proxy. Alternatively, call the API from your own
backend with a secret key.

## Python

```python
from image_studio import process, analyze, load_preset

result = process("hand.jpg", "studio-warm", {"output": {"format": "webp"}})
result.image.save("out.webp")            # PIL image
result.report["remaining"]               # e.g. ["blurry"]
for r in result.renditions(): ...        # extra sizes
```

## Tests

```bash
.venv/bin/pip install -e ".[dev]" && .venv/bin/pytest
```

The tests use synthetic photos and the heuristic mask, so they run in about 20
seconds without downloading the AI model.
