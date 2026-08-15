"""Contrast math behind the sea-green shell decision (design/mockups/*.png).

Answers three questions with WCAG 2.x ratios:
  1. what passes on #2E8B57 as-is,
  2. how dark a sea-green shell must be for the CURRENT cream/gold text scheme
     to stay AA,
  3. which near-black on-shell ink clears AA on #2E8B57.

Run: python -X utf8 design/mockups/theme-shell-green-contrast.py
"""


def lin(c: float) -> float:
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb(hexs: str) -> tuple[int, int, int]:
    h = hexs.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def lum(hexs: str) -> float:
    r, g, b = rgb(hexs)
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def ratio(a: str, b: str) -> float:
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def mark(r: float) -> str:
    return 'AA(4.5+)' if r >= 4.5 else ('3:1 large-only' if r >= 3.0 else 'FAIL')


def scale(hexs: str, f: float) -> str:
    r, g, b = rgb(hexs)
    return '#%02x%02x%02x' % (round(r * f), round(g * f), round(b * f))


SEA = '#2E8B57'
CURRENT = '#1a472a'
FG = {
    '--ink-on-shell  cream  #f2eee5': '#f2eee5',
    '--ink-on-shell-2 muted #c6c0b2': '#c6c0b2',
    '--accent-on-shell gold #d4ac52': '#d4ac52',
    'white button label     #ffffff': '#ffffff',
    '--ink dark             #1c1a16': '#1c1a16',
    'near-black             #0a0a0a': '#0a0a0a',
}

print(f'1) on the picked shell {SEA} (vs current {CURRENT})')
for name, fg in FG.items():
    print(f'   {name:34s} sea {ratio(fg, SEA):5.2f} {mark(ratio(fg, SEA)):16s}'
          f' current {ratio(fg, CURRENT):5.2f} {mark(ratio(fg, CURRENT))}')

print(f'\n2) darkest sea-green that keeps each fg at AA 4.5 (same hue, RGB scaled)')
for name, fg in list(FG.items())[:4]:
    hit = None
    f = 1.0
    while f > 0.2:
        cand = scale(SEA, f)
        if ratio(fg, cand) >= 4.5:
            hit = cand
            break
        f -= 0.005
    print(f'   {name:34s} -> {hit or "impossible"}'
          + (f'  (ratio {ratio(fg, hit):.2f}, {round(f * 100)}% of the picked value)' if hit else ''))

print(f'\n3) light text can never reach AA on {SEA}: pure #ffffff tops out at '
      f'{ratio("#ffffff", SEA):.2f}. Only near-black clears it '
      f'(#000000 = {ratio("#000000", SEA):.2f}).')
