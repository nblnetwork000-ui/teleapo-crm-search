import unittest
from unittest.mock import patch

import app


class EventFeeTests(unittest.TestCase):
    def test_amount_recognizes_free_ranges_and_multiple_prices(self):
        self.assertEqual(app.event_fee_amount("無料"), 0)
        self.assertEqual(app.event_fee_amount("参加費 3,000〜5,000円"), 3000)
        self.assertEqual(app.event_fee_amount("男性 5,000円 / 女性 3,000円"), 3000)
        self.assertEqual(app.event_fee_amount("¥12,000"), 12000)
        self.assertEqual(app.event_fee_amount("3千円"), 3000)
        self.assertIsNone(app.event_fee_amount("要確認"))

    def test_price_band_boundaries_and_unknown(self):
        events = [{"fee": fee} for fee in ("無料", "3,000円", "3,001円", "5,000円", "5,001円", "10,000円", "10,001円", "")]
        expected = {"free": [0], "under3000": [1], "under5000": [2, 3], "under10000": [4, 5], "over10000": [6], "unknown": [7]}
        for band, indexes in expected.items():
            with self.subTest(band=band):
                self.assertEqual(app.filter_and_sort_events_by_fee(events, band), [events[index] for index in indexes])

    def test_sort_keeps_unknown_last_in_both_directions(self):
        events = [{"fee": fee} for fee in ("要確認", "5,000円", "無料", "3,000円")]
        self.assertEqual([item["fee"] for item in app.filter_and_sort_events_by_fee(events, "all", "low")], ["無料", "3,000円", "5,000円", "要確認"])
        self.assertEqual([item["fee"] for item in app.filter_and_sort_events_by_fee(events, "all", "high")], ["5,000円", "3,000円", "無料", "要確認"])

    def test_jsonld_offer_price(self):
        self.assertEqual(app.fee_from_jsonld_offers([{"price": "5000", "priceCurrency": "JPY"}, {"price": 3000}]), "3,000円")
        self.assertEqual(app.fee_from_jsonld_offers({"price": 0}), "無料")
        self.assertEqual(app.fee_from_jsonld_offers({"price": 20, "priceCurrency": "USD"}), "")

    def test_search_input_rejects_invalid_fee_options(self):
        payload = {"keyword": "交流会", "source": "all", "results": 20}
        self.assertEqual(app.parse_event_search_input(payload, 100)["feeBand"], "all")
        self.assertFalse(app.parse_event_search_input(payload, 100)["append"])
        with self.assertRaises(app.InputError):
            app.parse_event_search_input({**payload, "feeBand": "negative"}, 100)
        with self.assertRaises(app.InputError):
            app.parse_event_search_input({**payload, "feeSort": "random"}, 100)

    def test_search_filters_and_sorts_before_limiting_results(self):
        search = app.parse_event_search_input({"keyword": "交流会", "source": "connpass", "results": 2, "feeBand": "under5000", "feeSort": "high"}, 100)
        events = [{"title": title, "fee": fee} for title, fee in (("不明", ""), ("安い", "3,001円"), ("高い", "5,000円"), ("対象外", "10,000円"))]
        with patch.object(app, "scrape_connpass_search", return_value=events):
            result = app.search_connpass_events(search)
        self.assertEqual([item["title"] for item in result["items"]], ["高い", "安い"])


if __name__ == "__main__":
    unittest.main()
