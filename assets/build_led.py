"""Render the profile motto as an LED panel SVG: python3 assets/build_led.py"""

from pathlib import Path

LINES = ("INTELLIGENCE IS RENTED.", "INSIGHT IS NOT.")

GLYPHS = {
    "I": ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01111"],
    "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "D": ["11100", "10010", "10001", "10001", "10001", "10010", "11100"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    ".": ["00", "00", "00", "00", "00", "11", "11"],
    " ": ["000"] * 7,
}

PITCH, CELL = 12, 10
PAD_X, PAD_Y, LINE_GAP = 4, 3, 4


def text_cells(text):
    cells, x = [], 0
    for ch in text:
        rows = GLYPHS[ch]
        for y, row in enumerate(rows):
            cells += [(x + i, y) for i, bit in enumerate(row) if bit == "1"]
        x += len(rows[0]) + 1
    return cells, x - 1


def main():
    rendered = [text_cells(t) for t in LINES]
    cols = max(w for _, w in rendered) + 2 * PAD_X
    rows = 2 * PAD_Y + 7 * len(LINES) + LINE_GAP * (len(LINES) - 1)
    width, height = cols * PITCH, rows * PITCH
    cx = cols / 2

    groups = []
    for n, (cells, w) in enumerate(rendered):
        x0 = (cols - w) // 2
        y0 = PAD_Y + n * (7 + LINE_GAP)
        start = 0.2 if n == 0 else 1.5
        rects = []
        for x, y in cells:
            gx, gy = x0 + x, y0 + y
            # Light from the centre outward, like the W3W logo boot-up.
            delay = start + abs(gx + 0.5 - cx) * 0.008
            rects.append(
                f'<rect x="{gx * PITCH}" y="{gy * PITCH}" width="{CELL}" height="{CELL}" '
                f'style="animation-delay:{delay:.3f}s"/>'
            )
        groups.append(f'<g class="l{n}">{"".join(rects)}</g>')

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="{' '.join(LINES)}">
<title>{' '.join(LINES).title()}</title>
<defs>
<pattern id="grid" width="{PITCH}" height="{PITCH}" patternUnits="userSpaceOnUse"><rect width="{CELL}" height="{CELL}" fill="#1a1a1a"/></pattern>
<filter id="glow" x="-5%" y="-30%" width="110%" height="160%"><feGaussianBlur stdDeviation="5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
</defs>
<style>
.l0 rect{{fill:#fff;animation:on .25s ease-out both}}
.l1 rect{{fill:#bcff2f;animation:on .25s ease-out both}}
.l0{{opacity:.3;animation:lease 1.4s 2.6s linear both}}
.l1{{filter:url(#glow)}}
@keyframes on{{from{{fill-opacity:0}}}}
/* The rented line flickers and fades; the insight line stays lit. */
@keyframes lease{{0%{{opacity:1}}12%{{opacity:.2}}18%{{opacity:1}}30%{{opacity:.15}}36%{{opacity:.9}}100%{{opacity:.3}}}}
@media (prefers-reduced-motion:reduce){{rect,g{{animation:none!important}}}}
</style>
<rect width="{width}" height="{height}" rx="24" fill="#000"/>
<rect x="{PITCH}" y="{PITCH}" width="{width - 2 * PITCH}" height="{height - 2 * PITCH}" fill="url(#grid)"/>
{''.join(groups)}
</svg>
"""
    out = Path(__file__).with_name("motto.svg")
    out.write_text(svg)
    print(f"{out.name}: {cols}x{rows} cells, {width}x{height}px, {len(svg)} bytes")


if __name__ == "__main__":
    main()
