"""python3 -m unittest discover game"""

import json
import os
import secrets
import tempfile
import unittest
from pathlib import Path

import game

OWNER = "zahT3"


def state(answer="lantern"):
    salt = secrets.token_hex(16)
    return {"layer": {"n": 1, "question": "q1", "message": "", "salt": salt, "hash": game.digest(answer, salt),
                      "iterations": game.ITERATIONS, "author": OWNER, "published": None},
            "solved": None, "pending": None, "history": []}


def form(**fields):
    return "\n\n".join(f"### {k.title()}\n\n{v}" for k, v in fields.items())


def layer_form(n=2, question="q2", answer="moon", message="hi"):
    salt = secrets.token_hex(16)
    return form(layer=n, question=question, message=message, salt=salt, hash=game.digest(answer, salt))


class Answers(unittest.TestCase):
    def test_normalize_ignores_case_space_punctuation_width(self):
        self.assertEqual(game.normalize(" The  Moon! "), "themoon")
        self.assertEqual(game.normalize("１２３"), "123")
        self.assertEqual(game.normalize("月亮，。"), "月亮")

    def test_parse_form(self):
        body = "### Answer\n\n  lantern \n\n### Message\n\n_No response_"
        self.assertEqual(game.parse_form(body), {"answer": "lantern", "message": ""})


class Flow(unittest.TestCase):
    def setUp(self):
        self.s = state()
        self.g = game.Game(self.s, OWNER)

    def test_wrong_answer_is_closed_without_state_change(self):
        self.g.issue_opened(5, "eve", form(answer="lamp"))
        self.assertIsNone(self.s["solved"])
        self.assertIsNone(self.g.commit)
        self.assertTrue(self.g.comments[0]["close"])

    def test_right_answer_marks_solver_and_blocks_others(self):
        self.g.issue_opened(5, "alice", form(answer=" Lantern. "))
        self.assertEqual(self.s["solved"]["by"], "alice")
        self.assertIn("?layer=2", self.g.comments[0]["body"])
        self.g.issue_opened(6, "bob", form(answer="lantern"))
        self.assertEqual(self.s["solved"]["by"], "alice")
        self.assertIn("already solved", self.g.comments[-1]["body"])

    def test_only_the_solver_may_propose(self):
        self.g.issue_opened(5, "alice", form(answer="lantern"))
        self.g.issue_opened(7, "mallory", layer_form())
        self.assertIsNone(self.s["pending"])
        self.assertIn("Only the person", self.g.comments[-1]["body"])

    def test_solver_proposal_waits_for_owner_approval(self):
        self.g.issue_opened(5, "alice", form(answer="lantern"))
        self.g.issue_opened(7, "alice", layer_form())
        self.assertEqual(self.s["pending"]["issue"], 7)
        self.assertEqual(self.s["layer"]["n"], 1)
        self.g.comment(7, "alice", "/approve")      # solver cannot approve their own layer
        self.g.comment(7, "mallory", "/approve")
        self.assertEqual(self.s["layer"]["n"], 1)
        self.g.comment(7, OWNER, "/approve")
        self.assertEqual(self.s["layer"]["n"], 2)
        self.assertEqual(self.s["layer"]["author"], "alice")
        self.assertIsNone(self.s["solved"])
        self.assertIsNone(self.s["pending"])
        self.assertEqual(self.s["history"][0]["solved_by"], "alice")
        # the new layer accepts its own answer
        self.g.issue_opened(9, "bob", form(answer="MOON"))
        self.assertEqual(self.s["solved"]["by"], "bob")

    def test_reject_lets_solver_resubmit(self):
        self.g.issue_opened(5, "alice", form(answer="lantern"))
        self.g.issue_opened(7, "alice", layer_form())
        self.g.comment(7, OWNER, "/reject too easy to search")
        self.assertIsNone(self.s["pending"])
        self.assertIn("too easy to search", self.g.comments[-1]["body"])
        self.g.issue_opened(8, "alice", layer_form(question="better"))
        self.assertEqual(self.s["pending"]["layer"]["question"], "better")

    def test_owner_layer_goes_live_without_review(self):
        self.g.issue_opened(7, OWNER, layer_form())
        self.assertEqual(self.s["layer"]["n"], 2)

    def test_invalid_proposals(self):
        self.g.issue_opened(5, "alice", form(answer="lantern"))
        for body, why in [(layer_form(n=5), "next layer is 2"),
                          (layer_form(question="x" * 281), "1–280"),
                          (layer_form(message="m" * 141), "at most 140"),
                          (form(layer=2, question="q", message="", salt="zz", hash="00"), "salt or hash")]:
            self.g.issue_opened(7, "alice", body)
            self.assertIsNone(self.s["pending"])
            self.assertIn(why, self.g.comments[-1]["body"])


class Rendering(unittest.TestCase):
    def test_wrap_respects_cjk_width(self):
        lines = game.wrap("月" * 100, cols=20)
        self.assertTrue(all(game.width(l) <= 20 for l in lines))
        self.assertEqual("".join(lines), "月" * 100)

    def test_svg_escapes_user_text(self):
        s = state()
        s["layer"]["question"] = '<script>alert("x")</script> & friends'
        svg = game.render_svg(s)
        self.assertNotIn("<script>", svg)
        self.assertIn("&lt;script&gt;", svg)

    def test_split_strip_shows_one_text_per_scheme(self):
        s = state()
        s["layer"]["split"] = {"light": "NOT", "dark": "RENT"}
        svg = game.render_svg(s)
        self.assertIn('class="led light"', svg)
        self.assertIn('class="led dark"', svg)
        self.assertIn("@media (prefers-color-scheme:dark){.dark{display:inline}.light{display:none}}", svg)


class Motto(unittest.TestCase):
    """Layer 1 depends on the rented motto line blinking a readable Morse message."""

    def test_morse_decodes_back_to_the_message(self):
        import re
        import sys
        sys.path.insert(0, str(game.ROOT / "assets"))
        import build_led
        frames, dur = build_led.morse_keyframes(build_led.MORSE_TEXT)
        stops = [(float(p), float(v)) for p, v in re.findall(r"([\d.]+)%\{opacity:([\d.]+)\}", frames)]
        unit = 100 * build_led.MORSE_UNIT / dur
        runs = [(v == 1, round((b - a) / unit)) for (a, v), (b, _) in zip(stops, stops[1:] + [(100, 0)])]
        code = {v: k for k, v in build_led.MORSE.items()}
        text, letter = "", ""
        for lit, units in runs:
            if lit:
                letter += "." if units == 1 else "-"
            elif units >= 3:
                text += code[letter] + (" " if units == 7 else "")
                letter = ""
        self.assertEqual(text, build_led.MORSE_TEXT)
        self.assertIn(frames, (game.ROOT / "assets" / "motto.svg").read_text())  # the committed SVG is current


class Play(unittest.TestCase):
    """End to end through play(): event file in, state/README/SVG/outbox out."""

    def test_correct_answer_event(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            saved = game.STATE, game.README, game.SVG, game.OUTBOX
            game.STATE, game.README, game.SVG, game.OUTBOX = d / "s.json", d / "R.md", d / "r.svg", d / "o.json"
            try:
                game.STATE.write_text(json.dumps(state()))
                game.README.write_text("top\n<!-- relay:start -->\nold\n<!-- relay:end -->\nbottom\n")
                out = d / "out"
                os.environ["GITHUB_OUTPUT"] = str(out)
                event = {"action": "opened", "repository": {"owner": {"login": OWNER}}, "sender": {"login": "alice"},
                         "issue": {"number": 3, "body": form(answer="lantern")}}
                game.play("issues", event)
                self.assertEqual(json.loads(game.STATE.read_text())["solved"]["by"], "alice")
                self.assertIn("solved by @alice", game.SVG.read_text())
                readme = game.README.read_text()
                self.assertTrue(readme.startswith("top\n") and readme.endswith("bottom\n"))
                self.assertNotIn("old", readme)
                self.assertIn("message=Relay: @alice solves layer 1", out.read_text())
                self.assertEqual(json.loads(game.OUTBOX.read_text())[0]["issue"], 3)
            finally:
                game.STATE, game.README, game.SVG, game.OUTBOX = saved
                os.environ.pop("GITHUB_OUTPUT", None)


if __name__ == "__main__":
    unittest.main()
