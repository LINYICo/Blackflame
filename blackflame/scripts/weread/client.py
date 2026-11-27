"""Small synchronous client for the documented read-only gateway operations."""

import http.client
import json
from contextlib import closing

from .auth import WeReadError, checked_key

HOST = "i.weread.qq.com"
PATH = "/api/agent/gateway"
SKILL_VERSION = "1.0.6"
SEARCH_SCOPES = (0, 6, 10, 14, 16)


class WeReadClient:
    def __init__(self, api_key: str):
        self._key = checked_key(api_key)

    def _request(self, api_name, **params):
        for field in ("bookId", "bookid"):
            if field in params and not (isinstance(params[field], str) and params[field].strip()):
                raise WeReadError("A book ID is required.")
        payload = {k: v for k, v in params.items() if v is not None}
        payload.update(api_name=api_name, skill_version=SKILL_VERSION)
        try:
            body = json.dumps(payload)
        except ValueError:
            raise WeReadError("Invalid gateway parameters.") from None
        escaped_key = json.dumps(self._key)[1:-1]
        if escaped_key in body:
            raise WeReadError("Request parameters contain a credential.")
        status = None
        try:
            with closing(http.client.HTTPSConnection(HOST, timeout=15)) as connection:
                connection.set_debuglevel(0)  # Never trace authorization headers.
                connection.request(
                    "POST", PATH, body, {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}
                )
                response = connection.getresponse()
                if response.status in (401, 403):
                    raise WeReadError("Authentication or access denied.")
                if response.status == 429:
                    raise WeReadError("Rate limited. Try again later.")
                if 300 <= response.status < 400:
                    raise WeReadError(f"Gateway HTTP error {response.status}.")
                status = response.status
                raw = response.read()
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise WeReadError("Invalid gateway response.")
            code = data.get("errcode", 0)
            if type(code) is not int:
                raise WeReadError("Invalid gateway error code.")
            if code:
                raise WeReadError(f"微信读书业务错误 {code}（HTTP {status}）。")
            if status != 200:
                raise WeReadError(f"Gateway HTTP error {status}.")
            if escaped_key in json.dumps(data, allow_nan=False):
                raise WeReadError("Invalid gateway response.")
            return data
        except TimeoutError:
            error = "Gateway request timed out."
        except (OSError, http.client.HTTPException):
            error = "Gateway connection failed."
        except (ValueError, RecursionError):
            if status is None:
                error = "Invalid gateway request or response."
            else:
                error = "Invalid gateway JSON." if status == 200 else f"Gateway HTTP error {status}."
        raise WeReadError(error)

    def book(self, book_id):
        return self._request("/book/info", bookId=book_id)

    def chapters(self, book_id):
        return self._request("/book/chapterinfo", bookId=book_id)

    def shelf(self):
        return self._request("/shelf/sync")

    def progress(self, book_id):
        return self._request("/book/getprogress", bookId=book_id)

    def highlights(self, book_id):
        return self._request("/book/bookmarklist", bookId=book_id)

    def search(self, keyword, context, scope=10, count=None, cursor=None):
        if (
            not all(isinstance(v, str) and v.strip() for v in (keyword, context))
            or type(scope) is not int
            or scope not in SEARCH_SCOPES
        ):
            raise WeReadError("Supply a search term, context and supported book search scope.")
        return self._page("/store/search", "maxIdx", cursor, count, keyword=keyword, context=context, scope=scope)

    def notebooks(self, count=None, cursor=None):
        return self._page("/user/notebooks", "lastSort", cursor, count)

    def thoughts(self, book_id, count=None, cursor=None):
        return self._page("/review/list/mine", "synckey", cursor, count, bookid=book_id)

    def _page(self, api_name, cursor_field, cursor, count, **params):
        if (count is not None and (type(count) is not int or count < 1)) or (
            cursor is not None and (type(cursor) is not int or cursor < 0)
        ):
            raise WeReadError("Count must be positive and cursor nonnegative.")
        data = self._request(api_name, count=count, **params, **{cursor_field: cursor})
        next_cursor = None
        # The aggregate search overview can omit the flag and provides no continuation.
        overview = params.get("scope") == 0 and not cursor and isinstance(data.get("sid"), str) and data["sid"]
        flag = data.get("hasMore", 0 if overview else None)
        if type(flag) is not int or flag not in (0, 1):
            raise WeReadError("Invalid gateway pagination flag.")
        items_field = {"maxIdx": "results", "lastSort": "books", "synckey": "reviews"}[cursor_field]
        if not isinstance(data.get(items_field), list):
            raise WeReadError("Invalid gateway page contents.")
        if flag:
            try:
                if cursor_field == "maxIdx":
                    books = next(group["books"] for group in reversed(data["results"]) if group.get("books"))
                    next_cursor = books[-1]["searchIdx"]
                elif cursor_field == "lastSort":
                    next_cursor = data["books"][-1]["sort"]
                else:
                    next_cursor = data["synckey"]
            except (KeyError, TypeError, IndexError, AttributeError, StopIteration):
                pass
            if type(next_cursor) is not int or next_cursor <= 0 or next_cursor == cursor:
                raise WeReadError("Missing or repeated gateway pagination cursor.")
            if cursor and (
                (cursor_field == "maxIdx" and next_cursor < cursor)
                or (cursor_field == "lastSort" and next_cursor > cursor)
            ):
                raise WeReadError("Gateway pagination cursor moved backwards.")
        return {"data": data, "next_cursor": next_cursor}
