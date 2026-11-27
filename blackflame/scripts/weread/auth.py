"""Resolve WeRead credentials without file or command-line storage."""

import getpass
import os
import sys
import warnings

SERVICE = "Blackflame.WeRead"
ACCOUNT = "api-key"


class WeReadError(Exception):
    """A diagnostic safe to display to the caller."""


def checked_key(value: str) -> str:
    if not (value.startswith("wrk-") and len(value) > 4 and all("!" <= c <= "~" for c in value)):
        raise WeReadError("Invalid API key format.")
    return value


def _keychain():
    from keyring.backends.macOS import Keyring

    return Keyring()


def _credential(action, *args):
    if sys.platform != "darwin":
        raise WeReadError("Keychain requires macOS. Supply WEREAD_API_KEY through the environment.")
    try:
        backend = _keychain()
        if action == "delete_password" and backend.get_password(SERVICE, ACCOUNT) is None:
            return
        return getattr(backend, action)(SERVICE, ACCOUNT, *args)
    except Exception:
        pass
    raise WeReadError("Keychain access failed. Check the project dependencies and Keychain permissions.")


def read_key() -> str:
    value = os.environ.get("WEREAD_API_KEY")
    if value is None:
        value = _credential("get_password")
    if value is None:
        raise WeReadError("Configure a WeRead API key first.")
    return checked_key(value)


def save_key(value: str):
    _credential("set_password", checked_key(value))


def configure_key():
    value = os.environ.get("WEREAD_API_KEY")
    if value is None:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                value = getpass.getpass("WeRead API key: ")
        except (getpass.GetPassWarning, EOFError, KeyboardInterrupt):
            raise WeReadError("Secure input unavailable or interrupted.") from None
    save_key(value)


def clear_key():
    _credential("delete_password")
