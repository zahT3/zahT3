"""Render the line-art shelf SVG: python3 assets/build_shelf.py"""

from pathlib import Path

W, H = 1656, 640
VP = (828, 300)  # vanishing point of the one-point perspective
DEPTH = 0.13  # how far back walls and box sides recede toward VP
SLOT, RISE, HOLD = 3.0, 0.45, 1.7  # seconds per box: rise, hold, sink, rest

# (repo, card note, icon, x, y_base, width, height); y_base is the shelf the box stands on.
# Notes paraphrase each repository's own GitHub description.
BOXES = [
    ("falling-stars", "31,956 meteorites", "globe", 110, 318, 340, 112),
    ("hotseat", "account switcher", "swap", 900, 318, 320, 104),
    ("fire-calc", "4 questions, 1 number", "flame", 660, 598, 330, 116),
    ("auto-hunt-job", "local-first job search", "lens", 150, 598, 300, 96),
    ("all-email-in-chat", "email via MCP", "mail", 1210, 598, 350, 124),
]

# 36x36 line icons, drawn from the card's icon origin.
ICONS = {
    "globe": '<circle cx="18" cy="20" r="14"/><ellipse cx="18" cy="20" rx="6" ry="14"/><path d="M4 20h28M30 2l-9 9"/>',
    "swap": '<path d="M2 10h30l-7-7m7 7-7 7M34 28H4l7-7m-7 7 7 7"/>',
    "flame": '<path d="M18 2c12 12 12 24 0 32C6 26 8 18 14 12c0 8 6 8 4-10z"/>',
    "lens": '<circle cx="14" cy="14" r="11"/><path d="M22 22l12 12"/>',
    "mail": '<rect x="1" y="6" width="34" height="24"/><path d="M1 6l17 14 17-14"/>',
}
# Plain blocks that fill the shelves; they never move.
BLOCKS = [(560, 318, 100, 232), (1430, 318, 96, 176), (70, 598, 64, 176), (1060, 598, 70, 206)]

LINE = "#e8e8e8"
FACE = "#121212"
LIME = "#bcff2f"


def toward_vp(x, y, k=DEPTH):
    return x + (VP[0] - x) * k, y + (VP[1] - y) * k


def pts(*ps):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in ps)


def room():
    x0, y0, x1, y1 = 24, 24, W - 24, H - 24
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    back = [toward_vp(*c, 0.16) for c in corners]
    out = [f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" class="ln" fill="none"/>']
    out.append(f'<polygon points="{pts(*back)}" class="ln" fill="#0a0a0a"/>')
    out += [f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" class="ln"/>' for a, b in zip(corners, back)]
    for sy in (318, 330):
        bl, br = toward_vp(x0, sy, 0.16), toward_vp(x1, sy, 0.16)
        out.append(f'<polyline points="{pts((x0, sy), bl, br, (x1, sy))}" class="ln" fill="none"/>')
    return "\n".join(out)


def side_face(x, y, w, h, dashed=True):
    """Visible side of a box: the side facing the vanishing point."""
    ex = x + w if x + w / 2 < VP[0] else x
    a, b = (ex, y), (ex, y + h)
    cls = "ln dash" if dashed else "ln"
    return f'<polygon points="{pts(a, toward_vp(*a), toward_vp(*b), b)}" class="{cls}" fill="#0c0c0c"/>'


def block(x, base, w, h):
    y = base - h
    return side_face(x, y, w, h) + f'<rect x="{x}" y="{y}" width="{w}" height="{h}" class="ln" fill="#050505"/>'


def card(i, note, icon, x, y, w):
    # Only the top ~70px clears the box when lifted, so content stays in that band.
    cw, ch = w * 0.84, 92
    cx = x + (w - cw) / 2
    return (
        f'<g class="card c{i}"><rect x="{cx:.1f}" y="{y}" width="{cw:.1f}" height="{ch}" class="ln" fill="#161616"/>'
        f'<g class="mk" transform="translate({cx + 16:.1f} {y + 14})">{ICONS[icon]}</g>'
        f'<text class="note" x="{cx + 66:.1f}" y="{y + 39}">{note}</text></g>'
    )


def box(i, label, note, icon, x, base, w, h):
    y = base - h
    tab = f'<polyline points="{pts((x + w * 0.2, y), (x + w * 0.2, y - 10), (x + w * 0.8, y - 10), (x + w * 0.8, y))}" class="ln" fill="none"/>'
    return (
        f'<g class="box b{i}">{side_face(x, y, w, h)}{tab}{card(i, note, icon, x, y, w)}'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" class="ln" fill="{FACE}"/>'
        f'<text x="{x + w / 2}" y="{y + h / 2 + 9}" text-anchor="middle">{label}</text></g>'
    )


def keyframes(i, n):
    total = SLOT * n
    pct = lambda t: f"{(i * SLOT + t) / total * 100:.2f}%"
    start, up, down, end = pct(0), pct(RISE), pct(RISE + HOLD), pct(RISE + HOLD + RISE)
    pop = (
        f"@keyframes p{i}{{0%,{start},{end},100%{{transform:none}}"
        f"{up},{down}{{transform:translateY(10px) scale(1.09)}}}}"
    )
    lift = f"@keyframes l{i}{{0%,{start},{end},100%{{transform:none}}{up},{down}{{transform:translateY(-70px)}}}}"
    # Every other box dims while this one is out.
    dim_on = [f"{(j * SLOT + RISE * 0.5) / total * 100:.2f}%,{(j * SLOT + RISE + HOLD) / total * 100:.2f}%" for j in range(n) if j != i]
    dim_off = [f"{(j * SLOT) / total * 100:.2f}%,{(j * SLOT + RISE * 2 + HOLD) / total * 100:.2f}%" for j in range(n) if j != i]
    dim = f"@keyframes d{i}{{0%,100%,{','.join(dim_off)}{{opacity:1}}{','.join(dim_on)}{{opacity:.32}}}}"
    rules = (
        f".b{i}{{animation:p{i} {total}s cubic-bezier(.2,.8,.2,1) infinite,d{i} {total}s ease infinite}}"
        f".c{i}{{animation:l{i} {total}s cubic-bezier(.2,.8,.2,1) infinite}}"
    )
    return pop + lift + dim + rules


def main():
    n = len(BOXES)
    style = (
        f".ln{{stroke:{LINE};stroke-width:2;stroke-linejoin:round}}"
        ".dash{stroke-dasharray:7 6}"
        f".mk{{fill:none;stroke:{LIME};stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round}}"
        f"text{{font:500 26px ui-sans-serif,-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;fill:{LINE}}}"
        ".note{font-size:19px;fill:#b8b8b8}"
        ".box,.card{transform-box:fill-box;transform-origin:50% 100%}"
        + "".join(keyframes(i, n) for i in range(n))
        + "@media (prefers-reduced-motion:reduce){.box,.card{animation:none!important}}"
    )
    labels = ", ".join(b[0] for b in BOXES)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="A shelf of public repositories: {labels}">',
        "<title>Public repositories</title>",
        f"<style>{style}</style>",
        f'<rect width="{W}" height="{H}" rx="24" fill="#000"/>',
        room(),
        *(block(*b) for b in BLOCKS),
        *(box(i, *b) for i, b in enumerate(BOXES)),
        "</svg>",
    ]
    out = Path(__file__).with_name("shelf.svg")
    out.write_text("\n".join(parts) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
