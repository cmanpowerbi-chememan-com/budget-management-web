"""Crop the real web-result screenshots the AI captured during the UAT run, one per case,
named by Test Case ID, into requirement_spec/5_uat/expected_result_image/.

The 54-case workbook is text-heavy; a picture of what the screen actually showed makes each
case easy to follow. Source = the primary evidence screenshot listed in each case's `evidence`
field (.scratch/uat-prep/runner/shots/*.png). Each image is auto-cropped to its content (the
outer uniform margin is trimmed) so the app view fills the frame.

    python -X utf8 requirement_spec/5_uat/_build/crop_web_result_images.py            # all cases
    python -X utf8 requirement_spec/5_uat/_build/crop_web_result_images.py UAT-01     # one (preview)

Never Read the PNGs — the user reviews them.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / ".scratch/uat-prep/runner/results.json"
SHOTS = ROOT / ".scratch/uat-prep/runner/shots"
OUT_DIR = ROOT / "requirement_spec/5_uat/expected_result_image"
OUT_DIR.mkdir(parents=True, exist_ok=True)
PAD = 10        # px of margin kept around the cropped content


def primary_shot(evidence: str) -> Path | None:
    """First shots/ file named in the comma-separated evidence string."""
    for part in (evidence or "").split(","):
        part = part.strip()
        if part.startswith("shots/"):
            p = SHOTS / Path(part).name
            if p.exists():
                return p
    return None


def autocrop(im: Image.Image) -> Image.Image:
    """Trim the uniform outer border (the app background), keep a small pad."""
    rgb = im.convert("RGB")
    # background colour sampled from the top-left corner
    bg = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
    diff = ImageChops.difference(rgb, bg)
    bbox = diff.getbbox()
    if not bbox:
        return im
    left, top, right, bottom = bbox
    left = max(0, left - PAD)
    top = max(0, top - PAD)
    right = min(rgb.width, right + PAD)
    bottom = min(rgb.height, bottom + PAD)
    return im.crop((left, top, right, bottom))


def main() -> int:
    d = json.load(RESULTS.open(encoding="utf-8"))
    by_id = {c["id"]: c for c in d["cases"]}
    ids = [a.upper() for a in sys.argv[1:] if a.upper().startswith("UAT-")]
    targets = ids or sorted(by_id, key=lambda x: int(x.split("-")[1]))
    done, missing = 0, []
    for cid in targets:
        c = by_id.get(cid)
        shot = primary_shot(c.get("evidence", "")) if c else None
        if not shot:
            missing.append(cid)
            continue
        out = OUT_DIR / f"{cid}.png"
        autocrop(Image.open(shot)).save(out)
        print(f"{cid:8s} <- {shot.name:44s} -> {out.name}")
        done += 1
    print(f"\ncropped {done} case(s); no screenshot for: {missing or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
