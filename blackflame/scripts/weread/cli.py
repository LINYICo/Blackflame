"""JSON command line for the Blackflame skill."""

import argparse
import getpass
import json
import os
import sys
import warnings

from . import auth
from .client import WeReadClient


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, '{"error":"Invalid arguments. Use --help for usage."}\n')


def main(argv=None):
    parser = Parser(prog="weread")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("auth").add_argument("action", choices=["set", "verify", "clear"])
    for name in ("book", "chapters", "progress", "highlights", "thoughts", "notebooks", "search", "shelf"):
        cmd = commands.add_parser(name)
        if name in ("book", "chapters", "progress", "highlights", "thoughts"):
            cmd.add_argument("book_id")
        if name == "search":
            cmd.add_argument("keyword")
            cmd.add_argument("--context", required=True)
            cmd.add_argument("--scope", type=int, choices=(0, 6, 10, 14, 16), default=10)
        if name in ("search", "thoughts", "notebooks"):
            cmd.add_argument("--count", type=int)
            cmd.add_argument("--cursor", type=int)
    params = vars(parser.parse_args(argv))
    command = params.pop("command")
    try:
        if command == "auth":
            action = params["action"]
            if action == "set":
                value = os.environ.get("WEREAD_API_KEY")
                if value is None:
                    with warnings.catch_warnings():
                        warnings.simplefilter("error", getpass.GetPassWarning)
                        value = getpass.getpass("WeRead API key: ")
                auth.save_key(value)
                result = {"stored": "macOS Keychain"}
            elif action == "clear":
                auth.clear_key()
                result = {"cleared": "macOS Keychain", "environment_present": "WEREAD_API_KEY" in os.environ}
            else:
                WeReadClient(auth.read_key()).notebooks(count=1)
                result = {"verified": True}
        else:
            result = getattr(WeReadClient(auth.read_key()), command)(**params)
    except (getpass.GetPassWarning, EOFError, KeyboardInterrupt):
        print('{"error":"Secure input unavailable or interrupted."}', file=sys.stderr)
        return 1
    except auth.WeReadError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
