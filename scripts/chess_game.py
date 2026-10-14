"""Community chess on the profile: anyone plays the next move by opening an issue.

The README lists every legal move as a link that opens an issue titled
"chess|move|e2e4". The chess workflow runs this script on that issue:

    python scripts/chess_game.py from-issue   # reads ISSUE_TITLE, ISSUE_USER
    python scripts/chess_game.py render       # redraw board and README block only

Issue titles are untrusted input. They arrive through environment variables,
never through workflow expressions, and only titles matching TITLE_RE are
acted on.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import urllib.parse

import chess
import chess.svg

import readme
from svgkit import ROOT, write

OWNER = "tanmay-starslab"
REPO = f"{OWNER}/{OWNER}"
STATE = ROOT / "chess" / "state.json"
TITLE_RE = re.compile(r"^chess\|(?:move\|(?P<uci>[a-h][1-8][a-h][1-8][qrbn]?)|(?P<new>new))$")
LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
PIECES = ["King", "Queen", "Rook", "Bishop", "Knight", "Pawn"]
PIECE_TYPES = {
    "King": chess.KING, "Queen": chess.QUEEN, "Rook": chess.ROOK,
    "Bishop": chess.BISHOP, "Knight": chess.KNIGHT, "Pawn": chess.PAWN,
}

BOARD_COLORS = {
    "dark": {
        "square light": "#C3C9E6", "square dark": "#6F79AE",
        "square light lastmove": "#E8CB8F", "square dark lastmove": "#BC8E42",
        "margin": "#0F1736", "coord": "#9AA2C6",
        "inner border": "#0F1736", "outer border": "#0F1736",
    },
    "light": {
        "square light": "#EEF0F8", "square dark": "#A9B0D3",
        "square light lastmove": "#F1D49C", "square dark lastmove": "#D0A65A",
        "margin": "#F6F8FC", "coord": "#565E80",
        "inner border": "#F6F8FC", "outer border": "#F6F8FC",
    },
}


def today() -> str:
    return dt.date.today().isoformat()


def new_state(game: int = 1) -> dict:
    return {"game": game, "started": today(), "moves": [], "players": {}, "result": None}


def load() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return new_state()


def save(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def replay(state: dict) -> chess.Board:
    board = chess.Board()
    for m in state["moves"]:
        board.push_uci(m["uci"])
    return board


def issue_link(title: str, body: str) -> str:
    return f"https://github.com/{REPO}/issues/new?" + urllib.parse.urlencode({"title": title, "body": body})


def move_link(board: chess.Board, move: chess.Move) -> str:
    san = board.san(move)
    url = issue_link(
        f"chess|move|{move.uci()}",
        f"I'm playing {san}. Press **Create** and the bot will make the move for you within a minute or two.",
    )
    return f"[{san}]({url})"


def outcome_text(board: chess.Board) -> str | None:
    outcome = board.outcome(claim_draw=True)
    if outcome is None:
        return None
    if outcome.winner is None:
        reason = outcome.termination.name.replace("_", " ").lower()
        return f"Draw by {reason}."
    side = "White" if outcome.winner else "Black"
    return f"Checkmate. {side} wins."


def render(state: dict) -> None:
    board = replay(state)
    last = board.peek() if board.move_stack else None
    check = board.king(board.turn) if board.is_check() else None
    for theme, colors in BOARD_COLORS.items():
        svg = chess.svg.board(board, size=440, lastmove=last, check=check, coordinates=True, colors=colors)
        write(ROOT / "chess" / f"board-{theme}.svg", svg + "\n")

    side = "White" if board.turn else "Black"
    move_no = board.fullmove_number
    lines = [
        "<table><tr><td width=\"48%\" valign=\"top\">",
        "",
        "<picture>",
        '  <source media="(prefers-color-scheme: dark)" srcset="chess/board-dark.svg">',
        f'  <img src="chess/board-light.svg" width="100%" alt="Community chess board, game {state["game"]}">',
        "</picture>",
        "",
        "</td><td valign=\"top\">",
        "",
    ]
    result = outcome_text(board)
    if result:
        lines += [
            f"**Game {state['game']} is over. {result}**",
            "",
            f"[Start game {state['game'] + 1}]({issue_link('chess|new', 'Press **Create** to set up a fresh board.')})",
        ]
    else:
        lines += [
            f"**Game {state['game']}, move {move_no}. {side} to play.**",
            "",
            "Click a move, then press **Create** on the issue page that opens. "
            "A bot checks the move, plays it and redraws this board within a minute or two.",
            "",
        ]
        by_piece: dict[str, list[str]] = {}
        for move in sorted(board.legal_moves, key=lambda m: board.san(m)):
            piece = board.piece_at(move.from_square)
            name = next(n for n, t in PIECE_TYPES.items() if t == piece.piece_type)
            by_piece.setdefault(name, []).append(move_link(board, move))
        lines += ["| Piece | Moves |", "| :-- | :-- |"]
        for name in PIECES:
            if name in by_piece:
                lines.append(f"| {name} | {' '.join(by_piece[name])} |")

    if state["moves"]:
        recent = state["moves"][-6:]
        start_ply = len(state["moves"]) - len(recent)
        played = []
        for i, m in enumerate(recent):
            ply = start_ply + i
            prefix = f"{ply // 2 + 1}." if ply % 2 == 0 else f"{ply // 2 + 1}…"
            played.append(f"{prefix} {m['san']} by @{m['user']}")
        lines += ["", "**Last moves:** " + ", ".join(played) + "."]
    if state["players"]:
        top = sorted(state["players"].items(), key=lambda kv: (-kv[1], kv[0].lower()))[:5]
        lines += ["", "**Most moves this game:** " + ", ".join(f"@{u} ({n})" for u, n in top) + "."]
    lines += ["", "</td></tr></table>"]
    readme.update({"CHESS": "\n".join(lines)})


def play_from_issue() -> str:
    title = os.environ.get("ISSUE_TITLE", "").strip()
    user = os.environ.get("ISSUE_USER", "").strip()
    if not LOGIN_RE.match(user):
        return "This move could not be attributed to a GitHub user, so it was not played."
    match = TITLE_RE.match(title)
    if not match:
        return (
            "This issue title isn't a move the bot understands. Use the move links in the "
            f"[profile README](https://github.com/{OWNER}) to play."
        )

    state = load()
    board = replay(state)

    if match.group("new"):
        if outcome_text(board) is None and user != OWNER:
            return "The current game is still going, so a new one can't be started yet. Play a move instead!"
        state = new_state(state["game"] + 1)
        save(state)
        render(state)
        return f"Game {state['game']} is set up. White to play: pick the first move on the [profile](https://github.com/{OWNER})."

    if outcome_text(board):
        return f"Game {state['game']} has finished. Start a new one from the [profile](https://github.com/{OWNER})."

    if state["moves"] and state["moves"][-1]["user"] == user and user != OWNER:
        return "You played the last move, so let someone else answer it. Share the board with a friend!"

    move = chess.Move.from_uci(match.group("uci"))
    if move not in board.legal_moves:
        # A pawn reaching the last rank without a piece letter: default to a queen.
        queen = chess.Move.from_uci(match.group("uci") + "q")
        if queen in board.legal_moves:
            move = queen
        else:
            return (
                f"`{match.group('uci')}` isn't legal in the current position "
                f"(someone may have moved first). Pick a move from the [profile](https://github.com/{OWNER})."
            )

    san = board.san(move)
    board.push(move)
    state["moves"].append({"uci": move.uci(), "san": san, "user": user, "date": today()})
    state["players"][user] = state["players"].get(user, 0) + 1
    result = outcome_text(board)
    state["result"] = result
    save(state)
    render(state)

    reply = f"Thanks @{user}, you played **{san}**."
    if result:
        reply += f" {result} Start the next game from the [profile](https://github.com/{OWNER})."
    else:
        side = "White" if board.turn else "Black"
        reply += f" {side} is to play next on the [profile](https://github.com/{OWNER})."
    return reply


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "render"
    if command == "render":
        state = load()
        if not STATE.exists():
            save(state)
        render(state)
        return 0
    if command == "from-issue":
        reply = play_from_issue()
        print(reply)
        reply_file = os.environ.get("REPLY_FILE")
        if reply_file:
            with open(reply_file, "w", encoding="utf-8") as fh:
                fh.write(reply + "\n")
        return 0
    print(f"unknown command {command!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
