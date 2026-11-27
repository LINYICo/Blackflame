"""JSON command line for the Blackflame skill."""

import argparse
import json
import os
import sys

from . import auth
from .client import SEARCH_SCOPES, WeReadClient


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, '{"error":"Invalid arguments. Use --help for usage."}\n')


def main(argv=None):
    parser = Parser(prog="weread")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("auth").add_argument("action", choices=["set", "verify", "clear"])
    commands.add_parser("shelf")
    for name in ("book", "chapters", "progress", "highlights"):
        commands.add_parser(name).add_argument("book_id")
    thoughts = commands.add_parser("thoughts")
    thoughts.add_argument("book_id")
    search = commands.add_parser("search")
    search.add_argument("keyword")
    search.add_argument("--context", required=True)
    search.add_argument("--scope", type=int, choices=SEARCH_SCOPES, default=10)
    for cmd in (search, thoughts, commands.add_parser("notebooks")):
        cmd.add_argument("--count", type=int)
        cmd.add_argument("--cursor", type=int)
    params = vars(parser.parse_args(argv))
    command = params.pop("command")
    try:
        if command == "auth":
            action = params["action"]
            if action == "set":
                auth.configure_key()
                result = {"stored": "macOS Keychain"}
            elif action == "clear":
                auth.clear_key()
                result = {"cleared": "macOS Keychain", "environment_present": "WEREAD_API_KEY" in os.environ}
            else:
                data = WeReadClient(auth.read_key()).notebooks(count=1)["data"]
                if not all(type(data.get(k)) is int and data[k] >= 0 for k in ("totalBookCount", "totalNoteCount")):
                    raise auth.WeReadError("Invalid notebook verification response.")
                result = {"verified": True}
        else:
            result = getattr(WeReadClient(auth.read_key()), command)(**params)
    except auth.WeReadError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
