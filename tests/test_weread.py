import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from blackflame.scripts.weread import auth, cli, client

KEY = "wrk-" + "fixture"


class CredentialTests(unittest.TestCase):
    def test_keychain_lifecycle_and_environment_precedence(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(auth.sys, "platform", "darwin"),
            patch.object(auth, "_keychain") as factory,
        ):
            store = factory.return_value
            auth.save_key(KEY)
            store.set_password.assert_called_once_with(auth.SERVICE, auth.ACCOUNT, KEY)
            store.get_password.return_value = KEY
            self.assertEqual(auth.read_key(), KEY)
            auth.clear_key()
            store.delete_password.assert_called_once_with(auth.SERVICE, auth.ACCOUNT)
            os.environ["WEREAD_API_KEY"] = KEY + "2"
            factory.reset_mock()
            self.assertEqual(auth.read_key(), KEY + "2")
            factory.assert_not_called()

    def test_invalid_key_and_keychain_failure_are_safe(self):
        with (
            patch.object(auth.sys, "platform", "darwin"),
            patch.object(auth, "_keychain", side_effect=RuntimeError(KEY)),
        ):
            for value in (KEY + "\n", KEY):
                with self.assertRaises(auth.WeReadError) as caught:
                    auth.save_key(value)
                self.assertNotIn(KEY, str(caught.exception))
                self.assertIsNone(caught.exception.__context__)


class GatewayTests(unittest.TestCase):
    def setUp(self):
        factory = self.enterContext(patch.object(client.http.client, "HTTPSConnection"))
        self.connection = factory.return_value
        self.response = self.connection.getresponse.return_value
        self.response.status = 200
        self.api = client.WeReadClient(KEY)
        self.factory = factory

    def reply(self, value):
        self.response.read.return_value = json.dumps(value).encode()

    def check_request(self, name, **params):
        self.factory.assert_called_with("i.weread.qq.com", timeout=15)
        method, path, body, headers = self.connection.request.call_args.args
        self.assertEqual((method, path), ("POST", "/api/agent/gateway"))
        self.assertEqual(json.loads(body), {"api_name": name, "skill_version": "1.0.6", **params})
        self.assertEqual(headers, {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
        self.connection.set_debuglevel.assert_called_with(0)
        self.connection.close.assert_called()

    def test_book_and_shelf_calls_preserve_fields(self):
        for method, path, params, data in [
            ("book", "/book/info", {"bookId": "123"}, {"title": "三体"}),
            ("chapters", "/book/chapterinfo", {"bookId": "123"}, {"chapters": []}),
            ("shelf", "/shelf/sync", {}, {"albums": [], "books": [], "mp": {}}),
            ("progress", "/book/getprogress", {"bookId": "123"}, {"book": {"progress": 1}}),
            ("highlights", "/book/bookmarklist", {"bookId": "123"}, {"updated": []}),
        ]:
            with self.subTest(method):
                self.reply(data)
                self.assertEqual(getattr(self.api, method)(*params.values()), data)
                self.check_request(path, **params)

    def test_paginated_endpoints(self):
        for method, args, path, cursor_name, items, params in [
            (
                "search",
                ["三体", "找三体"],
                "/store/search",
                "maxIdx",
                {"results": [{"scope": 17, "books": [{"searchIdx": 8}]}, {"books": []}]},
                {"keyword": "三体", "context": "找三体", "scope": 10},
            ),
            ("notebooks", [], "/user/notebooks", "lastSort", {"books": [{"sort": 8}]}, {}),
            ("thoughts", ["123"], "/review/list/mine", "synckey", {"reviews": [], "synckey": 8}, {"bookid": "123"}),
        ]:
            with self.subTest(method):
                first = {"hasMore": 1, "upgrade_info": {}, **items}
                self.reply(first)
                fetch = getattr(self.api, method)
                page = fetch(*args)
                self.check_request(path, **params)
                self.assertEqual(page, {"data": first, "next_cursor": 8})
                self.reply({"hasMore": 0, **items})
                self.assertIsNone(fetch(*args, cursor=page["next_cursor"], count=2)["next_cursor"])
                self.check_request(path, **params, **{cursor_name: 8}, count=2)

    def test_http_and_transport_errors(self):
        self.response.read.return_value = b"unavailable"
        for status, message in [(403, "denied"), (401, "denied"), (429, "Rate limited"), (302, "302"), (503, "503")]:
            self.response.status = status
            with self.assertRaisesRegex(auth.WeReadError, message):
                self.api.shelf()
        self.response.status = 499
        self.reply({"errcode": -2003, "errlog": KEY})
        with self.assertRaisesRegex(auth.WeReadError, "-2003（HTTP 499）"):
            self.api.book("missing")
        self.connection.getresponse.side_effect = TimeoutError(KEY)
        with self.assertRaisesRegex(auth.WeReadError, "timed out"):
            self.api.shelf()
        self.connection.getresponse.side_effect = OSError(KEY)
        with self.assertRaisesRegex(auth.WeReadError, "connection failed"):
            self.api.shelf()
        self.assertEqual(self.connection.request.call_count, 8)

    def test_malformed_business_and_credential_echo_responses(self):
        for raw in [
            b"broken",
            b"[]",
            b'{"progress":NaN}',
            b'{"errcode":-17}',
            json.dumps({"books": [{"title": KEY}]}).encode(),
        ]:
            self.response.read.return_value = raw
            with self.assertRaises(auth.WeReadError) as caught:
                self.api.shelf()
            self.assertNotIn(KEY, str(caught.exception))
        for data in [{"hasMore": 1, "books": []}, {"hasMore": 1, "books": [{"sort": 9}]}, {}]:
            self.reply(data)
            with self.assertRaises(auth.WeReadError):
                self.api.notebooks(cursor=9)

    def test_cli_json_and_exit_status(self):
        self.enterContext(patch.dict(os.environ, {"WEREAD_API_KEY": KEY}))
        for args, response, expected, status in [
            (["auth", "verify"], {"hasMore": 0, "books": []}, {"verified": True}, 0),
            (["book", "123"], {"title": "三体"}, {"title": "三体"}, 0),
            (["book", "123"], {"errcode": -1, "errmsg": KEY}, {"error": "微信读书业务错误 -1（HTTP 200）。"}, 1),
        ]:
            self.reply(response)
            with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
                self.assertEqual(cli.main(args), status)
            self.assertEqual(json.loads((err if status else out).getvalue()), expected)
            if args[0] == "auth":
                self.check_request("/user/notebooks", count=1)
        with redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as caught:
            cli.main(["auth", "set", KEY])
        self.assertEqual(caught.exception.code, 2)
        self.assertNotIn(KEY, json.loads(err.getvalue())["error"])

    def test_cli_hidden_input_unavailable(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(auth.getpass, "getpass", side_effect=auth.getpass.GetPassWarning),
            patch.object(auth, "save_key") as save,
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(cli.main(["auth", "set"]), 1)
            save.assert_not_called()
