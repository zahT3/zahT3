"""Insight relay: a riddle chain played through issues on this profile repository.

Whoever solves the current layer writes the next one; the repository owner approves it before it goes live.
Answers are stored only as salted PBKDF2 hashes, computed in the setter's browser (docs/index.html).

    python3 game/game.py play     # handle the triggering issue/comment event; writes files + an outbox
    python3 game/game.py notify   # after the workflow has pushed, post the outbox comments
    python3 game/game.py render   # rebuild assets/relay.svg and the README section from state.json
"""

import hashlib
import json
import os
import re
import sys
import unicodedata
import urllib.request
from datetime import datetime, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "game" / "state.json"
OUTBOX = ROOT / "game" / ".outbox.json"
SVG = ROOT / "assets" / "relay.svg"
README = ROOT / "README.md"
REPO = "zahT3/zahT3"
SETTER_PAGE = "https://zahT3.github.io/zahT3/"
ITERATIONS = 200_000
MAX_QUESTION, MAX_MESSAGE, MAX_ANSWER = 280, 140, 200


# ---------- answers ----------

def normalize(answer):
    """Case, width, spaces and punctuation never decide an answer: keep letters and digits only."""
    return "".join(ch for ch in unicodedata.normalize("NFKC", answer).lower() if ch.isalnum())


def digest(answer, salt, iterations=ITERATIONS):
    return hashlib.pbkdf2_hmac("sha256", normalize(answer).encode(), bytes.fromhex(salt), iterations).hex()


def parse_form(body):
    """Issue-form bodies arrive as '### Label' headings, each followed by its value."""
    fields, label, lines = {}, None, []
    for line in (body or "").splitlines():
        m = re.match(r"^###\s+(.+?)\s*$", line)
        if m:
            if label:
                fields[label] = "\n".join(lines).strip()
            label, lines = m.group(1).lower(), []
        elif label:
            lines.append(line)
    if label:
        fields[label] = "\n".join(lines).strip()
    return {k: ("" if v == "_No response_" else v) for k, v in fields.items()}


# ---------- the game ----------

def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


class Game:
    """Pure state machine over state.json; side effects are queued, not performed."""

    def __init__(self, state, owner):
        self.s, self.owner = state, owner
        self.comments, self.commit = [], None  # [(issue, body, close, reason)], commit message

    def say(self, issue, body, close=False, reason="completed"):
        self.comments.append({"issue": issue, "body": body, "close": close, "reason": reason})

    @property
    def n(self):
        return self.s["layer"]["n"]

    # --- issues ---

    def issue_opened(self, issue, user, body):
        form = parse_form(body)
        if "answer" in form:
            self.answer(issue, user, form["answer"])
        elif {"question", "hash", "salt"} <= form.keys():
            self.propose(issue, user, form)

    def answer(self, issue, user, text):
        if self.s["solved"]:
            by = self.s["solved"]["by"]
            return self.say(issue, f"Layer {self.n} was already solved by @{by}, who is writing the next one. "
                                   "Watch this repository to hear when it goes live.", close=True, reason="not_planned")
        if not normalize(text) or len(text) > MAX_ANSWER:
            return self.say(issue, "That answer is empty or too long.", close=True, reason="not_planned")
        layer = self.s["layer"]
        if digest(text, layer["salt"], layer["iterations"]) != layer["hash"]:
            return self.say(issue, "Not it. Try again whenever you like: each attempt is a new issue.",
                            close=True, reason="not_planned")
        self.s["solved"] = {"by": user, "at": now(), "issue": issue}
        self.commit = f"Relay: @{user} solves layer {self.n}"
        self.say(issue, f"Correct, @{user}. You solved layer {self.n}.\n\n"
                        f"You now write layer {self.n + 1}: open {SETTER_PAGE}?layer={self.n + 1}, write a riddle "
                        "and its answer, and leave a message for whoever comes next. The page hashes the answer in "
                        "your browser, so it never appears in public. "
                        f"@{self.owner} reviews each layer before it goes live.", close=True)

    def propose(self, issue, user, form):
        solved = self.s["solved"]
        if user != self.owner and not (solved and solved["by"] == user):
            return self.say(issue, f"Only the person who solved layer {self.n} writes the next one.",
                            close=True, reason="not_planned")
        if self.s["pending"] and user != self.owner:
            return self.say(issue, f"Layer {self.n + 1} is already waiting for review in #{self.s['pending']['issue']}.",
                            close=True, reason="not_planned")
        problem = self.invalid(form)
        if problem:
            return self.say(issue, f"{problem} Please submit it again from {SETTER_PAGE}?layer={self.n + 1}.",
                            close=True, reason="not_planned")
        layer = {"n": self.n + 1, "question": form["question"].strip(), "message": form.get("message", "").strip(),
                 "salt": form["salt"].strip().lower(), "hash": form["hash"].strip().lower(),
                 "iterations": ITERATIONS, "author": user}
        if user == self.owner:
            return self.publish(issue, layer)
        self.s["pending"] = {"issue": issue, "layer": layer}
        self.commit = f"Relay: layer {layer['n']} by @{user} awaits review"
        self.say(issue, f"Thanks, @{user}. Layer {layer['n']} is waiting for @{self.owner} to review it; "
                        "you'll be notified here.")

    def invalid(self, form):
        if form.get("layer", "").strip() != str(self.n + 1):
            return f"This form is for layer {form.get('layer') or '?'}, but the next layer is {self.n + 1}."
        q = form["question"].strip()
        if not q or len(q) > MAX_QUESTION:
            return f"The riddle must be 1–{MAX_QUESTION} characters."
        if len(form.get("message", "").strip()) > MAX_MESSAGE:
            return f"The message must be at most {MAX_MESSAGE} characters."
        if any(unicodedata.category(c) == "Cc" and c not in "\n" for c in q + form.get("message", "")):
            return "The text contains control characters."
        if not re.fullmatch(r"[0-9a-f]{32}", form["salt"].strip().lower()) or \
                not re.fullmatch(r"[0-9a-f]{64}", form["hash"].strip().lower()):
            return "The salt or hash was edited or is missing."
        return None

    # --- owner commands ---

    def comment(self, issue, user, body):
        pending = self.s["pending"]
        if user != self.owner or not pending or pending["issue"] != issue:
            return
        cmd = body.strip().split(None, 1)
        if not cmd:
            return
        if cmd[0] == "/approve":
            self.publish(issue, pending["layer"])
        elif cmd[0] == "/reject":
            reason = cmd[1].strip() if len(cmd) > 1 else "No reason given."
            self.s["pending"] = None
            self.commit = f"Relay: layer {pending['layer']['n']} sent back"
            self.say(issue, f"@{pending['layer']['author']}, this layer was not accepted: {reason}\n\n"
                            f"You can submit a revised one from {SETTER_PAGE}?layer={self.n + 1}.",
                     close=True, reason="not_planned")

    def publish(self, issue, layer):
        old = self.s["layer"]
        solved = self.s["solved"] or {}
        self.s["history"].append({k: old[k] for k in ("n", "question", "message", "author")}
                                 | {"solved_by": solved.get("by"), "solved_at": solved.get("at")})
        self.s["layer"] = layer | {"published": now()}
        self.s["solved"] = self.s["pending"] = None
        self.commit = f"Relay: layer {layer['n']} by @{layer['author']} goes live"
        self.say(issue, f"Layer {layer['n']} is live on the profile. Thank you, @{layer['author']}.", close=True)


# ---------- rendering ----------

W, FS, LH, CW, X0 = 1656, 30, 50, 18, 60
COLS = (W - 2 * X0) // CW
FONT = 'ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace'
LIME = "#bcff2f"


def width(text):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def wrap(text, cols=COLS):
    out = []
    for para in text.splitlines() or [""]:
        line = ""
        for word in re.findall(r"\S+\s*|\s+", para) or [""]:
            if width(line + word.rstrip()) <= cols:
                line += word
                continue
            if line.strip():
                out.append(line.rstrip())
            line = ""
            while width(word.rstrip()) > cols:  # long words and CJK runs break anywhere
                cut = 0
                while width(word[:cut + 1]) <= cols:
                    cut += 1
                out.append(word[:cut])
                word = word[cut:]
            line = word
        out.append(line.rstrip())
    return out


LP, LC = 12, 10  # LED strip pitch and cell, matching the motto panel


def led_strip(split, top):
    """Owner-only layer extra: an LED strip whose text depends on the viewer's light/dark scheme."""
    sys.path.insert(0, str(ROOT / "assets"))
    from build_led import GLYPHS
    groups = []
    for mode, text in (("light", split["light"]), ("dark", split["dark"])):
        rects, x = [], X0 // LP + 1
        for ch in text.upper():
            rows = GLYPHS[ch]
            rects += [f'<rect x="{(x + i) * LP}" y="{top + (j + 1) * LP}" width="{LC}" height="{LC}"/>'
                      for j, row in enumerate(rows) for i, bit in enumerate(row) if bit == "1"]
            x += len(rows[0]) + 1
        groups.append(f'<g class="led {mode}">{"".join(rects)}</g>')
    band = (f'<rect x="{X0}" y="{top}" width="{W - 2 * X0}" height="{9 * LP}" fill="url(#ledgrid)"/>')
    return band + "".join(groups), 9 * LP


def render_svg(s):
    layer, solved = s["layer"], s["solved"]
    rows = [("p", "~ % ", f"cat layer-{layer['n']:02d}.txt")]
    rows += [("q", "", line) for line in wrap(layer["question"])]
    if layer.get("split"):
        rows.append(("split", "", ""))
    if layer.get("message"):
        rows.append(("gap", "", ""))
        rows += [("m", "", line) for line in wrap(f"@{layer['author']}: {layer['message']}")]
    rows.append(("gap", "", ""))
    done = len(s["history"])
    if solved:
        rows.append(("ok", "", f"solved by @{solved['by']} · the next layer is being written"))
    else:
        tail = f" · {done} solved so far" if done else ""
        rows.append(("p", "~ % ", f"./answer{tail}"))
    bar, top = 52, 52 + 64
    height = top + (len(rows) - 1) * LH + 44
    y, body = top, []
    for kind, prompt, text in rows:
        if kind == "split":
            strip, h = led_strip(layer["split"], (y - FS + 30) // LP * LP)  # snap to the LED grid
            body.append(strip)
            y += h + 30
            continue
        if kind != "gap":
            px = X0 + width(prompt) * CW
            if prompt:
                body.append(f'<text x="{X0}" y="{y}" class="p">{escape(prompt.rstrip())}</text>')
            body.append(f'<text x="{px}" y="{y}" class="{kind}">{escape(text)}</text>')
        y += LH if kind != "gap" else LH // 2
    height = y - LH + 44
    cursor_x = X0 + (width(rows[-1][1]) + width(rows[-1][2]) + 1) * CW
    cursor = "" if solved else f'<rect class="cur" x="{cursor_x}" y="{y - LH - FS + 5}" width="{CW}" height="{FS}"/>'
    title = f"insight relay — layer {layer['n']}"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {height}" width="{W}" height="{height}" role="img" aria-label="{escape(title)}: {escape(layer['question'])}">
<title>{escape(title)}</title>
<defs><pattern id="ledgrid" x="{X0}" width="{LP}" height="{LP}" patternUnits="userSpaceOnUse"><rect width="{LC}" height="{LC}" fill="#161616"/></pattern></defs>
<style>
text{{font:{FS}px {FONT};white-space:pre}}
.p{{fill:{LIME}}}.q{{fill:#f2f2f2}}.m{{fill:#8a8a8a}}.ok{{fill:{LIME}}}.c{{fill:#f2f2f2}}
.bar{{fill:#151515}}.dot{{fill:#2e2e2e}}.title{{font-size:22px;fill:#6b6b6b}}
.led{{fill:{LIME}}}.dark{{display:none}}
@media (prefers-color-scheme:dark){{.dark{{display:inline}}.light{{display:none}}}}
.cur{{fill:{LIME};animation:blink 1.1s steps(1) infinite}}
@keyframes blink{{50%{{opacity:0}}}}
@media (prefers-reduced-motion:reduce){{.cur{{animation:none}}}}
</style>
<rect x="1" y="1" width="{W - 2}" height="{height - 2}" rx="18" fill="#000" stroke="#262626" stroke-width="2"/>
<path class="bar" d="M2 {bar}V19a17 17 0 0 1 17 -17H{W - 19}a17 17 0 0 1 17 17V{bar}Z"/>
<path d="M2 {bar}H{W - 2}" stroke="#262626" stroke-width="2"/>
{"".join(f'<circle class="dot" cx="{36 + i * 28}" cy="{bar / 2}" r="8"/>' for i in range(3))}
<text class="title" x="{W / 2}" y="{bar / 2 + 8}" text-anchor="middle">{escape(title)}</text>
{"".join(body)}
{cursor}
</svg>
"""


def render_readme(s):
    layer, solved = s["layer"], s["solved"]
    lines = [f'<img src="assets/relay.svg" alt="Insight relay, layer {layer["n"]}: {escape(layer["question"])}" width="100%">', ""]
    if solved:
        lines.append(f"Layer {layer['n']} was solved by [@{solved['by']}](https://github.com/{solved['by']}); "
                     "the next layer is on its way.")
    else:
        lines.append(f"**[Answer layer {layer['n']} →](https://github.com/{REPO}/issues/new?template=answer.yml)**"
                     " · [How the relay works](game/RULES.md)")
    solvers = [h["solved_by"] for h in s["history"] if h.get("solved_by")][-5:][::-1]
    if solvers:
        lines += ["", "Recent solvers: " + " · ".join(f"[@{u}](https://github.com/{u})" for u in solvers)]
    section = "\n".join(lines)
    text = README.read_text()
    start, end = "<!-- relay:start -->", "<!-- relay:end -->"
    if start not in text:
        return text
    head, rest = text.split(start, 1)
    return f"{head}{start}\n{section}\n{end}{rest.split(end, 1)[1]}"


def render(state):
    SVG.write_text(render_svg(state))
    README.write_text(render_readme(state))


# ---------- GitHub plumbing ----------

def api(method, path, payload):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}{path}", method=method,
                                 data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                                          "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status


def play(event_name, event):
    if event.get("issue", {}).get("pull_request"):
        return
    state = json.loads(STATE.read_text())
    game = Game(state, event["repository"]["owner"]["login"])
    issue, user = event["issue"]["number"], event["sender"]["login"]
    if event_name == "issues" and event.get("action") == "opened":
        game.issue_opened(issue, user, event["issue"].get("body"))
    elif event_name == "issue_comment" and event.get("action") == "created":
        game.comment(issue, user, event["comment"].get("body") or "")
    if game.commit:
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        render(state)
        with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as out:
            out.write(f"message={game.commit}\n")
    OUTBOX.write_text(json.dumps(game.comments))


def notify():
    for c in json.loads(OUTBOX.read_text()) if OUTBOX.exists() else []:
        api("POST", f"/issues/{c['issue']}/comments", {"body": c["body"]})
        if c["close"]:
            api("PATCH", f"/issues/{c['issue']}", {"state": "closed", "state_reason": c["reason"]})


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "play":
        play(os.environ["GITHUB_EVENT_NAME"], json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text()))
    elif mode == "notify":
        notify()
    elif mode == "render":
        render(json.loads(STATE.read_text()))
    else:
        sys.exit(__doc__)
