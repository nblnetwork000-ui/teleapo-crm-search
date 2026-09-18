import copy
import html
import http.cookiejar
import json
import re
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

import app


class FakeSheets:
    def __init__(self):
        self.sheets = {}

    def get_spreadsheet(self, _spreadsheet_id):
        return {
            "sheets": [
                {"properties": {"title": title, "sheetId": index + 1}}
                for index, title in enumerate(self.sheets)
            ]
        }

    def batch_update(self, _spreadsheet_id, requests):
        for request in requests:
            title = request.get("addSheet", {}).get("properties", {}).get("title")
            if title:
                self.sheets.setdefault(title, [])
        return {}

    def get_values(self, _spreadsheet_id, range_name):
        title, start_row, end_row = self._parse_range(range_name)
        rows = self.sheets.get(title, [])
        return {"values": copy.deepcopy(rows[start_row - 1 : end_row])}

    def update_values(self, _spreadsheet_id, range_name, values):
        title, start_row, _end_row = self._parse_range(range_name)
        rows = self.sheets.setdefault(title, [])
        while len(rows) < start_row - 1 + len(values):
            rows.append([])
        for offset, row in enumerate(values):
            rows[start_row - 1 + offset] = copy.deepcopy(row)
        return {"updatedRange": range_name}

    def append_values(self, _spreadsheet_id, range_name, values):
        title, _start_row, _end_row = self._parse_range(range_name)
        rows = self.sheets.setdefault(title, [])
        start = len(rows) + 1
        rows.extend(copy.deepcopy(values))
        end = len(rows)
        return {"updates": {"updatedRange": f"'{title}'!A{start}:I{end}"}}

    @staticmethod
    def _parse_range(range_name):
        whole_columns = re.match(r"'((?:[^']|'')+)'!A:I$", range_name)
        if whole_columns:
            return whole_columns.group(1).replace("''", "'"), 1, 10000
        match = re.match(r"'((?:[^']|'')+)'!A(\d+)(?::I?(\d+)?)?", range_name)
        if not match:
            raise AssertionError(f"Unsupported range: {range_name}")
        title = match.group(1).replace("''", "'")
        start_row = int(match.group(2))
        end_row = int(match.group(3) or 10000)
        return title, start_row, end_row


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.password = "very-secure-password"
        self.admin_hash = app.hash_password(self.password)
        self.config = {
            "GOOGLE_SHEET_ID": "sheet-id",
            "ACCESS_USERS": {"admin@example.com": self.admin_hash},
            "ADMIN_EMAILS": {"admin@example.com"},
        }
        self.sheets = FakeSheets()
        self.store = app.UserStore(self.sheets, self.config)

    def test_bootstraps_existing_admin(self):
        admin = self.store.authenticate("admin@example.com", self.password)
        self.assertIsNotNone(admin)
        self.assertEqual(admin["role"], "admin")
        self.assertEqual(admin["status"], "active")

    def test_invite_accept_is_single_use(self):
        self.store.ensure_initialized()
        invite_url = self.store.invite("member@example.com", "https://signal.example")
        token = invite_url.split("token=", 1)[1]
        member = self.store.accept_invite(token, "another-secure-password")
        self.assertEqual(member["status"], "active")
        self.assertIsNotNone(self.store.authenticate("member@example.com", "another-secure-password"))
        with self.assertRaises(app.InputError):
            self.store.accept_invite(token, "another-secure-password")

    def test_disabled_user_cannot_authenticate(self):
        self.store.ensure_initialized()
        self.store.set_status("admin@example.com", "disabled", "different-admin@example.com")
        self.assertIsNone(self.store.authenticate("admin@example.com", self.password))

    def test_admin_cannot_disable_self(self):
        self.store.ensure_initialized()
        with self.assertRaises(app.InputError):
            self.store.set_status("admin@example.com", "disabled", "admin@example.com")

    def test_password_requires_twelve_characters(self):
        with self.assertRaises(app.InputError):
            app.hash_password("too-short")


class HttpAuthFlowTests(unittest.TestCase):
    def setUp(self):
        self.admin_password = "very-secure-password"
        self.config = {
            "ALLOW_REMOTE_ACCESS": True,
            "ACCESS_PASSWORD": "",
            "ACCESS_MEMBER_ID": "",
            "ACCESS_USERS": {"admin@example.com": app.hash_password(self.admin_password)},
            "ADMIN_EMAILS": {"admin@example.com"},
            "SESSION_SECRET": "test-session-secret",
            "APP_MODE": "events",
            "MAX_RESULTS_PER_RUN": 100,
            "SKIP_DUPLICATES": True,
            "GOOGLE_SHEET_ID": "sheet-id",
            "GOOGLE_SHEET_NAME": "イベントリスト",
            "BRAVE_SEARCH_API_KEY": "",
            "APP_BASE_URL": "",
            "RESEND_API_KEY": "",
            "INVITE_FROM_EMAIL": "SIGNAL <onboarding@example.com>",
            "REQUESTS_PER_15_MIN": 1000,
        }
        self.sheets = FakeSheets()
        handler = app.make_handler(self.config, self.sheets, "test-csrf-token")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.admin = self._opener()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    @staticmethod
    def _opener():
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def _post(self, opener, path, values):
        body = urllib.parse.urlencode(values).encode("utf-8")
        return opener.open(
            urllib.request.Request(
                self.base_url + path,
                data=body,
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ),
            timeout=5,
        )

    def test_full_invite_login_and_disable_flow(self):
        login = self._post(
            self.admin,
            "/login",
            {"email": "admin@example.com", "password": self.admin_password},
        )
        self.assertTrue(login.geturl().endswith("/events.html"))

        config = json.loads(self.admin.open(self.base_url + "/api/config", timeout=5).read())
        self.assertTrue(config["isAdmin"])

        invite_response = self._post(
            self.admin,
            "/admin/invite",
            {"csrf_token": "test-csrf-token", "email": "member@example.com"},
        ).read().decode("utf-8")
        match = re.search(r'<input value="([^"]+/invite\?token=[^"]+)" readonly', invite_response)
        self.assertIsNotNone(match)
        invite_url = html.unescape(match.group(1))
        token = urllib.parse.parse_qs(urllib.parse.urlparse(invite_url).query)["token"][0]

        member = self._opener()
        accepted = self._post(
            member,
            "/invite/accept",
            {
                "token": token,
                "password": "member-secure-password",
                "password_confirm": "member-secure-password",
            },
        )
        self.assertTrue(accepted.geturl().endswith("/events.html"))
        member_config = json.loads(member.open(self.base_url + "/api/config", timeout=5).read())
        self.assertFalse(member_config["isAdmin"])

        self._post(
            self.admin,
            "/admin/users/status",
            {"csrf_token": "test-csrf-token", "email": "member@example.com", "status": "disabled"},
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            member.open(self.base_url + "/api/config", timeout=5)
        self.assertEqual(caught.exception.code, 401)


if __name__ == "__main__":
    unittest.main()
