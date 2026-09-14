"""Shared helper to finish a UAT expected-result image: crop the region, draw markers
(only for saved-screenshot mode — live markers are baked in the DOM), and append the
numbered legend. Numbers in the legend match the gold circles on the image.

build(src, out, crop, legend, saved_marks=None)
  src         path to the screenshot (live-marked, or a raw saved shot)
  out         output PNG path
  crop        (l, t, r, b) crop box in the SOURCE image, or None to keep full
  legend      list of Thai strings; item i gets circle number i
  saved_marks list of {n, box:(l,t,r,b), badge:'above'|'below'} in SOURCE coords —
              PIL draws these rings+badges (use only when markers are NOT already
              baked into the image); omit for live-marked shots.
"""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

F = r"C:\Windows\Fonts\tahoma.ttf"
FB = r"C:\Windows\Fonts\tahomabd.ttf"
GOLD = (253, 203, 53)
GOLD_DK = (120, 79, 33)
GREEN_DK = (9, 83, 45)
INK = (28, 28, 28)


def fnt(sz, bold=False):
    return ImageFont.truetype(FB if bold else F, sz)


def badge(d, x, y, n, r=14):
    d.ellipse((x - r, y - r, x + r, y + r), fill=GOLD, outline=(255, 255, 255), width=3)
    d.ellipse((x - r, y - r, x + r, y + r), outline=GOLD_DK, width=2)
    f = fnt(16, True)
    t = str(n)
    tb = d.textbbox((0, 0), t, font=f)
    d.text((x - (tb[2] - tb[0]) / 2, y - (tb[3] - tb[1]) / 2 - tb[1]), t, font=f, fill=GOLD_DK)


MIN_W = 980          # canvas never narrower than this, so the legend text always fits
LEG_X = 70           # legend text left edge (after the number badge)
LINE_H = 30          # height of one wrapped legend line


def _wrap(d, text, font, max_w):
    """Wrap Thai/mixed text to max_w px. Break on spaces; hard-break a too-long token."""
    lines, cur = [], ""
    for tok in text.split(" "):
        trial = tok if not cur else cur + " " + tok
        if d.textlength(trial, font=font) <= max_w:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        # token itself too long -> char-break
        if d.textlength(tok, font=font) <= max_w:
            cur = tok
        else:
            piece = ""
            for ch in tok:
                if d.textlength(piece + ch, font=font) <= max_w:
                    piece += ch
                else:
                    lines.append(piece)
                    piece = ch
            cur = piece
    if cur:
        lines.append(cur)
    return lines or [""]


def build(src, out, crop, legend, saved_marks=None):
    im = Image.open(src).convert("RGB")
    d0 = ImageDraw.Draw(im)
    for m in saved_marks or []:
        l, t, r, b = m["box"]
        d0.rounded_rectangle((l - 4, t - 4, r + 4, b + 4), radius=10, outline=GOLD, width=3)
        cx = (l + r) / 2
        by = (b + 22) if m.get("badge") == "below" else (t - 22)
        badge(d0, cx, by, m["n"])
    base = im.crop(crop) if crop else im
    W = max(base.width, MIN_W)
    sh = base.height
    lf = fnt(20)
    d_m = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    max_txt = W - LEG_X - 26
    wrapped = [_wrap(d_m, tx, lf, max_txt) for tx in legend]
    legh = 14 + 40 + sum(len(w) * LINE_H + 8 for w in wrapped) + 14
    cv = Image.new("RGB", (W, sh + legh), (255, 255, 255))
    cv.paste(base, ((W - base.width) // 2, 0))
    d = ImageDraw.Draw(cv)
    d.line((0, sh, W, sh), fill=(227, 231, 236), width=2)
    y = sh + 12
    d.text((26, y), "สิ่งที่ต้องเห็น (Expected Result) — เลขตรงกับวงกลมบนภาพ", font=fnt(22, True), fill=GREEN_DK)
    y += 42
    for i, wlines in enumerate(wrapped, 1):
        badge(d, 42, y + 10, i, r=13)
        for j, ln in enumerate(wlines):
            d.text((LEG_X, y + j * LINE_H), ln, font=lf, fill=INK)
        y += len(wlines) * LINE_H + 8
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    cv.save(out)
    return cv.size
