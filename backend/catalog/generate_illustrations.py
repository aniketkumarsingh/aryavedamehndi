"""Generates AI illustrations for catalog designs that have no photo yet.

Reads the prompts in illustration_prompts.json, asks Gemini for each image,
saves it as illustrations/<slug>.jpg and records it on the design in
designs.json ("illustration": {"generator", "prompt"}), then removes the
prompt. The site shows these with an "Illustration" badge and never uses
them as the reference a finished design is matched against.

Two backends:
- Gemini (default): needs GEMINI_API_KEY in backend/.env from
  aistudio.google.com, on a key with billing (the free tier has no images).
- --local: FLUX.1-schnell (Apache 2.0) on this Mac via mflux - free, no
  account. Needs an Apple Silicon Mac with 16 GB+ and mflux installed
  (pip install mflux); the first run downloads the model (~9 GB).

Always look at every new image before publishing - check the fingers or
toes, that only henna colours are used and that there is no stray text.
To redo one, delete its "illustration" entry and image, put its prompt
back in illustration_prompts.json and run this again. Then:

    cd backend
    venv/bin/python catalog/generate_illustrations.py [slug ...]
    venv/bin/python catalog/generate_illustrations.py --local --mflux /path/to/mflux-generate [slug ...]
    venv/bin/python catalog/name_images.py
    ../image-studio/.venv/bin/python catalog/build_studio.py
    venv/bin/python seed_designs.py
"""

import argparse
import base64
import io
import json
import re
import subprocess
import sys
import tempfile
import zlib
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
PROMPTS = HERE / "illustration_prompts.json"
CATALOG = HERE / "designs.json"
ILLUSTRATIONS = HERE / "illustrations"
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
LOCAL_MODEL = "dhairyashil/FLUX.1-schnell-mflux-4bit"  # Apache 2.0 FLUX.1-schnell, 4-bit for Apple Silicon


def api_key() -> str:
    env = HERE.parent / ".env"
    for line in env.read_text().splitlines() if env.exists() else []:
        m = re.match(r"\s*GEMINI_API_KEY\s*=\s*(.*)", line)
        if m:
            return m.group(1).strip().strip("'\"")
    sys.exit("GEMINI_API_KEY is missing from backend/.env")


def generate(prompt: str, model: str, key: str) -> Image.Image:
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "1:1"}},
    }
    req = urllib.request.Request(
        API.format(model=model),
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    for attempt in range(4):
        try:
            data = json.load(urllib.request.urlopen(req, timeout=180))
            break
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 503) or attempt == 3:
                raise SystemExit(f"Gemini refused the request: HTTP {e.code} {e.read().decode()[:300]}")
            time.sleep(10 * 2**attempt)
    for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
        inline = part.get("inlineData") or part.get("inline_data")
        if inline:
            return Image.open(io.BytesIO(base64.b64decode(inline["data"]))).convert("RGB")
    reason = data.get("candidates", [{}])[0].get("finishReason") or data.get("promptFeedback")
    raise RuntimeError(f"no image returned ({reason})")


def generate_local(prompt: str, mflux: str, seed: int) -> Image.Image:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.png"
        cmd = [mflux, "--model", LOCAL_MODEL, "--base-model", "schnell", "--steps", "4", "--seed", str(seed),
               "--width", "1024", "--height", "1024", "--prompt", prompt, "--output", str(out)]
        run = subprocess.run(cmd, capture_output=True, text=True)
        if run.returncode or not out.exists():
            raise RuntimeError(f"mflux failed: {(run.stderr or run.stdout)[-300:]}")
        return Image.open(out).convert("RGB")


def main(only: set[str], local: bool, mflux: str, seed_offset: int) -> None:
    prompts_doc = json.loads(PROMPTS.read_text())
    prompts, model = prompts_doc["prompts"], prompts_doc["model"]
    data = json.loads(CATALOG.read_text())
    designs = {d["slug"]: d for d in data["designs"]}
    key = None if local else api_key()
    ILLUSTRATIONS.mkdir(exist_ok=True)
    made = 0
    for slug, prompt in list(prompts.items()):
        if only and slug not in only:
            continue
        design = designs.get(slug)
        if design is None or design.get("image") or design.get("illustration"):
            print(f"skip {slug}: not a design waiting for an image")
            continue
        # Stable seed per design, so a run can be reproduced; --seed-offset gives a fresh variant.
        seed = zlib.crc32(slug.encode()) % 100000 + seed_offset
        try:
            img = generate_local(prompt, mflux, seed) if local else generate(prompt, model, key)
        except RuntimeError as e:
            print(f"FAILED {slug}: {e}")
            continue
        img.save(ILLUSTRATIONS / f"{slug}.jpg", quality=93)
        generator = f"FLUX.1-schnell (local, seed {seed})" if local else f"Gemini ({model})"
        design["illustration"] = {"generator": generator, "prompt": prompt}
        del prompts[slug]
        made += 1
        # Save after each image so an interrupted run keeps what it made.
        CATALOG.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        PROMPTS.write_text(json.dumps(prompts_doc, indent=2, ensure_ascii=False) + "\n")
        print(f"made {slug} ({img.width}x{img.height}) -> illustrations/{slug}.jpg")
    print(f"{made} illustrations made, {len(prompts)} prompts left - check each image before publishing")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("slugs", nargs="*", help="only these designs (default: all prompts)")
    parser.add_argument("--local", action="store_true", help="generate on this Mac with FLUX.1-schnell")
    parser.add_argument("--mflux", default="mflux-generate", help="path to mflux-generate (with --local)")
    parser.add_argument("--seed-offset", type=int, default=0, help="change to get a different variant")
    args = parser.parse_args()
    main(set(args.slugs), args.local, args.mflux, args.seed_offset)
