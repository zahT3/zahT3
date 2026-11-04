# Agent instructions

This public repository exists to render the `zahT3` GitHub Profile README.

- Keep `README.md` concise, accurate, and understandable without private context.
- Do not add credentials, private contact details, local machine paths, chat transcripts, private project names, or unpublished research claims.
- Do not add decorative badges, automated activity widgets, or generated metrics unless they add durable information.
- The insight relay (`game/`, `.github/`, `docs/`, and the `relay:start`/`relay:end` block in `README.md`) is the one automated part. Visitor-written riddles reach the profile only after the owner comments `/approve`. Never hand-edit the relay block or `assets/relay.svg`; change `game/state.json` and run `python3 game/game.py render`. Run `python3 -m unittest discover game` after changing `game/`.
- Verify every repository link and public claim before proposing a commit.
- Run a secret and privacy scan and inspect `git diff` before any push.
- Do not commit or push without explicit approval.
