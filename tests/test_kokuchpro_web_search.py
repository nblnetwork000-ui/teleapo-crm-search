import unittest
from unittest.mock import patch

import app


class KokuchproWebSearchTests(unittest.TestCase):
    def search(self, **overrides):
        payload = {"keyword": "交流会", "area": "東京都", "source": "kokuchpro", "results": 20, "futureOnly": True}
        payload.update(overrides)
        return app.parse_event_search_input(payload, 100)

    def test_maps_kokuchpro_search_result(self):
        result = {
            "title": "異業種交流会 2026年10月15日 19:00〜21:00 - こくちーずプロ",
            "description": "東京都で開催される交流会です（東京都） 参加費: 3,000円",
            "url": "https://www.kokuchpro.com/event/abc123/",
        }
        item = app.kokuchpro_event_from_web_result(result)
        self.assertEqual(item["title"], "異業種交流会 2026年10月15日 19:00〜21:00")
        self.assertEqual(item["startedAt"], "2026-10-15T19:00:00+09:00")
        self.assertEqual(item["endedAt"], "2026-10-15T21:00:00+09:00")
        self.assertEqual(item["place"], "東京都")
        self.assertEqual(item["fee"], "3,000円")
        self.assertEqual(item["source"], "こくちーずプロ")

    def test_rejects_non_event_and_non_kokuchpro_results(self):
        self.assertIsNone(app.kokuchpro_event_from_web_result({"url": "https://example.com/event/abc/"}))
        self.assertIsNone(app.kokuchpro_event_from_web_result({"url": "https://www.kokuchpro.com/group/abc/"}))

    @patch.object(app, "request_json")
    def test_search_uses_brave_site_query(self, request_json):
        request_json.return_value = {"web": {"results": [
            {"title": "無料交流会 2026年10月20日 10:00 - こくちーずプロ", "description": "開催場所（東京都） 無料イベント", "url": "https://www.kokuchpro.com/event/free-event/"},
            {"title": "別サイト", "url": "https://example.com/event/other/"},
        ]}}
        items = app.search_kokuchpro_events("brave-key", self.search())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["fee"], "無料")
        self.assertIn("site%3Akokuchpro.com%2Fevent%2F", request_json.call_args.args[0])

    def test_requires_web_search_key(self):
        with self.assertRaises(app.InputError):
            app.search_kokuchpro_events("", self.search())


if __name__ == "__main__":
    unittest.main()
