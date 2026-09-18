"""Fetch the self-hosted Prompt font files (Thai + Latin subsets) from Google
Fonts and the SIL Open Font License text, and save them under
frontend/public/fonts/prompt/ so the app can self-host them — no Google
Fonts <link>/CDN at runtime, per the app's "zero external requests" rule
(frontend/src/app/layout.tsx, frontend/src/styles/tokens.css).

Prompt (Cadson Demak, OFL) is jakkaritw's free stand-in for the licensed CI
font FC Minimal (2026-09-18) — see .claude/plan.md for the decision.

Uses only the Python standard library (urllib) — no installs, per this
machine's no-admin-rights constraint (CLAUDE.md "No-install machine").

Idempotent: re-running always re-downloads and overwrites the same target
files, so the output is identical run to run.

Run from repo root:
    python setup/fetch_prompt_font.py
"""

import re
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Weights actually used by the app's CSS (tokens.css --fw-* roles + raw
# numeric weights in global.css): 100 (.page-title em / .glassy em),
# 400, 500, 600, 700, 800.
WEIGHTS = [100, 400, 500, 600, 700, 800]

# The app is Thai + English only — latin-ext / vietnamese subsets are not needed.
SUBSETS = ("thai", "latin")

GOOGLE_CSS_URL = (
    "https://fonts.googleapis.com/css2?family=Prompt:wght@"
    + ";".join(str(w) for w in WEIGHTS)
    + "&display=swap"
)
OFL_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/prompt/OFL.txt"

# A modern desktop Chrome UA is required so Google's CSS2 endpoint returns
# woff2 sources (older/unset UAs get eot/ttf instead).
CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

OUT_DIR = Path(__file__).resolve().parent.parent / "frontend" / "public" / "fonts" / "prompt"

FONT_FACE_RE = re.compile(
    r"/\*\s*(?P<subset>[\w-]+)\s*\*/\s*"
    r"@font-face\s*\{"
    r"(?P<body>[^}]+)"
    r"\}",
    re.MULTILINE,
)
WEIGHT_RE = re.compile(r"font-weight:\s*(\d+)")
URL_RE = re.compile(r"url\((https://fonts\.gstatic\.com/[^)]+\.woff2)\)")


def fetch_text(url: str) -> str:
    """Fetch a URL as UTF-8 text with a Chrome User-Agent."""
    request = urllib.request.Request(url, headers={"User-Agent": CHROME_UA})
    with urllib.request.urlopen(request) as response:
        return response.read().decode("utf-8")


def fetch_bytes(url: str) -> bytes:
    """Fetch a URL as raw bytes."""
    request = urllib.request.Request(url, headers={"User-Agent": CHROME_UA})
    with urllib.request.urlopen(request) as response:
        return response.read()


def parse_font_faces(css_text: str) -> list[dict]:
    """Parse Google's css2 response into (subset, weight, url) entries."""
    entries = []
    for match in FONT_FACE_RE.finditer(css_text):
        subset = match.group("subset")
        body = match.group("body")
        weight_match = WEIGHT_RE.search(body)
        url_match = URL_RE.search(body)
        if weight_match and url_match:
            entries.append(
                {
                    "subset": subset,
                    "weight": int(weight_match.group(1)),
                    "url": url_match.group(1),
                }
            )
    return entries


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Fetching Google Fonts CSS: {GOOGLE_CSS_URL}")
    css_text = fetch_text(GOOGLE_CSS_URL)
    entries = [e for e in parse_font_faces(css_text) if e["subset"] in SUBSETS]

    wanted = {(w, s) for w in WEIGHTS for s in SUBSETS}
    found = {(e["weight"], e["subset"]) for e in entries}
    missing = wanted - found
    if missing:
        raise RuntimeError(f"Google Fonts response is missing entries: {sorted(missing)}")

    total_bytes = 0
    for entry in entries:
        filename = f"prompt-{entry['weight']}-{entry['subset']}.woff2"
        dest = OUT_DIR / filename
        data = fetch_bytes(entry["url"])
        dest.write_bytes(data)
        total_bytes += len(data)
        print(f"  {filename}  {len(data)} bytes")

    print(f"Fetching licence: {OFL_URL}")
    licence_text = fetch_text(OFL_URL)
    licence_path = OUT_DIR / "OFL.txt"
    with open(licence_path, "w", encoding="utf-8") as f:
        f.write(licence_text)
    total_bytes += len(licence_text.encode("utf-8"))
    print(f"  OFL.txt  {len(licence_text.encode('utf-8'))} bytes")

    print(f"Total: {len(entries)} font files + licence, {total_bytes} bytes")


if __name__ == "__main__":
    main()
