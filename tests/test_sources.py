"""The source adapters, driven by canned payloads rather than the network.

Every source here is a remote service that can change its shape without telling us.
These are the tests that turn "the site is different today" into a failure with a
name on it, rather than a quietly smaller dataset.
"""

import unittest

from tests import FakeSession, Response
from uadata.model import CATEGORIES, SourceError
from uadata.sources import CrawlerUserAgents, UserAgentsMe, WinFuture23

CHROME_155 = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
)
CHROME_154 = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
)
IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/27.0 Mobile/15E148 Safari/604.1"
)
IPAD = (
    "Mozilla/5.0 (iPad; CPU OS 18_7 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/27.0 Mobile/15E148 Safari/604.1"
)
GOOGLEBOT = "Googlebot/2.1 (+http://www.google.com/bot.html)"
BOT_IN_A_BROWSER_COSTUME = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 6_0 like Mac OS X) AppleWebKit/536.26 "
    "(KHTML, like Gecko) Version/6.0 Mobile/10A5376e Safari/8536.25 "
    "(compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)

WINDOW = "2026-09-20-to-2026-09-27"


def winfuture(device_type="computer", ua=CHROME_154, **extra):
    return {
        "schema_version": 1,
        "generated_at": "2026-09-28T21:51:13.703Z",
        "window": "48h",
        "user_agents": [
            {
                "ua": ua,
                "browser": {"name": "Chrome", "version": "154.0.0"},
                "os": {"name": "Windows", "version": "NT 10.0"},
                "device_type": device_type,
                "first_seen": "2026-09-10",
                "last_seen": "2026-09-28",
                **extra,
            }
        ],
    }


def useragents_me():
    return [
        {
            "user_agent": CHROME_155,
            "os": "Windows 10",
            "browser": "Chrome 155.0.0.0",
            "device": None,
            "count": 10116,
            "percentage": 25.48,
        }
    ]


class WinFuture23Tests(unittest.TestCase):
    def fetch(self, payload, url=WinFuture23.url):
        return WinFuture23().fetch(FakeSession({url: Response(payload)}))

    def test_it_files_its_own_vocabulary_into_our_device_categories(self):
        result = self.fetch(
            {
                "generated_at": "2026-09-28T21:51:13.703Z",
                "user_agents": [
                    {"ua": CHROME_154, "device_type": "computer"},
                    {"ua": IPHONE, "device_type": "mobile"},
                    {"ua": IPAD, "device_type": "tablet"},
                ],
            }
        )
        self.assertEqual(
            {c: [r.user_agent for r in v] for c, v in result.records.items()},
            {"desktop": [CHROME_154], "mobile": [IPHONE], "tablet": [IPAD]},
        )

    def test_an_unrecognised_device_type_fails_rather_than_being_guessed(self):
        # Filing a wearable or a TV string under desktop is a wrong record, and
        # dropping it silently is the 13-month bug all over again.
        with self.assertRaises(SourceError) as caught:
            self.fetch(winfuture(device_type="smart-tv"))
        self.assertIn("smart-tv", str(caught.exception))

    def test_it_publishes_no_count_so_nothing_it_says_is_presented_as_measured(self):
        record = self.fetch(winfuture()).records["desktop"][0]
        self.assertIsNone(record.count)
        self.assertIsNone(record.percentage)
        self.assertIsNone(record.count_source)

    def test_it_names_its_own_browser_and_os_in_the_shape_we_publish(self):
        record = self.fetch(winfuture()).records["desktop"][0]
        self.assertEqual(record.browser, "Chrome 154.0.0")
        self.assertEqual(record.os, "Windows NT 10.0")

    def test_a_missing_version_does_not_render_as_the_word_none(self):
        payload = winfuture(browser=None)
        self.assertIsNone(self.fetch(payload).records["desktop"][0].browser)

    def test_provenance_is_the_sources_own_collection_time_not_ours(self):
        # The source knows when it looked better than we do.
        self.assertEqual(
            self.fetch(winfuture()).collected_at, "2026-09-28T21:51:13.703Z"
        )

    def test_every_record_names_the_source_that_supplied_it(self):
        record = self.fetch(winfuture()).records["desktop"][0]
        self.assertEqual(record.sources, (WinFuture23.name,))

    def test_a_row_without_a_user_agent_fails_the_fetch(self):
        payload = winfuture(ua=None)
        with self.assertRaises(SourceError):
            self.fetch(payload)

    def test_a_payload_that_is_not_an_object_fails_the_fetch(self):
        for payload in ([], {"count": 12}, {"user_agents": {}}):
            with self.subTest(payload=payload):
                with self.assertRaises(SourceError):
                    self.fetch(payload)


class CrawlerUserAgentsTests(unittest.TestCase):
    def fetch(self, payload, url=CrawlerUserAgents.url):
        return CrawlerUserAgents().fetch(FakeSession({url: Response(payload)}))

    @staticmethod
    def payload(*instances):
        return [{"pattern": "Googlebot\\/", "instances": list(instances)}]

    def test_every_observed_string_becomes_a_bot(self):
        result = self.fetch(self.payload(GOOGLEBOT, BOT_IN_A_BROWSER_COSTUME))
        self.assertEqual(
            [r.user_agent for r in result.records["bot"]],
            [GOOGLEBOT, BOT_IN_A_BROWSER_COSTUME],
        )
        self.assertEqual(list(result.records), ["bot"])

    def test_a_crawler_in_a_browser_costume_is_still_a_crawler(self):
        # Filing it under mobile because the string mentions Safari would be the
        # most popular kind of wrong available to this repo.
        result = self.fetch(self.payload(BOT_IN_A_BROWSER_COSTUME))
        self.assertNotIn("mobile", result.records)

    def test_it_publishes_no_count(self):
        record = self.fetch(self.payload(GOOGLEBOT)).records["bot"][0]
        self.assertIsNone(record.count)
        self.assertIsNone(record.count_source)

    def test_every_record_names_the_source_that_supplied_it(self):
        record = self.fetch(self.payload(GOOGLEBOT)).records["bot"][0]
        self.assertEqual(record.sources, (CrawlerUserAgents.name,))

    def test_patterns_are_not_data(self):
        # A regex matches infinitely many strings, none of which anybody sent. A
        # pattern-only file is a broken source, not a source with nothing to say.
        with self.assertRaises(SourceError) as caught:
            self.fetch([{"pattern": "Googlebot\\/"}, {"pattern": "bingbot"}])
        self.assertIn("zero rows", str(caught.exception))

    def test_a_blank_observed_string_fails_the_fetch(self):
        with self.assertRaises(SourceError):
            self.fetch(self.payload("   "))

    def test_a_payload_that_is_not_a_list_fails_the_fetch(self):
        for payload in ({}, [], None):
            with self.subTest(payload=payload):
                with self.assertRaises(SourceError):
                    self.fetch(payload)


class SourceCoverageTests(unittest.TestCase):
    """The dataset's independence, asserted on the real adapters.

    Every Device Category has to be reachable without any one source, which is the
    property the whole build is arranged around: one source going away must not
    take the data with it.
    """

    def routes(self):
        base = "https://useragents.me"
        routes = {
            base: Response(None, text=f'<a href="{base}/data/{WINDOW}-desktop.json">x</a>'),
            CrawlerUserAgents.url: Response(
                [{"pattern": "Googlebot\\/", "instances": [GOOGLEBOT]}]
            ),
            WinFuture23.url: Response(
                {
                    "generated_at": "2026-09-28T21:51:13.703Z",
                    "user_agents": [
                        {"ua": CHROME_154, "device_type": "computer"},
                        {"ua": IPHONE, "device_type": "mobile"},
                        {"ua": IPAD, "device_type": "tablet"},
                    ],
                }
            ),
        }
        for category in ("desktop", "mobile", "tablet", "bot"):
            routes[f"{base}/data/{WINDOW}-{category}.json"] = Response(useragents_me())
            routes[f"{base}/data/{WINDOW}-latest-{category}.json"] = Response(
                useragents_me()
            )
        return routes

    def fetch_all(self, sources):
        return [source.fetch(FakeSession(self.routes())) for source in sources]

    def test_every_device_category_is_covered_by_more_than_one_source(self):
        results = self.fetch_all([UserAgentsMe(), WinFuture23(), CrawlerUserAgents()])
        covered = {
            category: {
                source
                for result in results
                for record in result.records.get(category, [])
                for source in record.sources
            }
            for category in CATEGORIES
        }
        for category, sources in covered.items():
            with self.subTest(category=category):
                self.assertGreaterEqual(
                    len(sources), 2, f"{category} rests on {sorted(sources)}"
                )

    def test_browsers_do_not_depend_on_the_unlicensed_source(self):
        # This is the property that makes ADR-0006 survivable: the current-version
        # desktop, mobile and tablet strings are CC0, not borrowed.
        results = self.fetch_all([WinFuture23(), CrawlerUserAgents()])
        covered = {c for result in results for c in result.records}
        self.assertEqual(covered, {"desktop", "mobile", "tablet", "bot"})

    def test_the_measured_source_is_the_one_the_ranking_uses(self):
        # Not a formatting detail: this name is what decides which counts may order
        # the published file, so a source that does not appear here is not a ranking.
        result = UserAgentsMe().fetch(FakeSession(self.routes()))
        self.assertEqual(
            {r.count_source for records in result.records.values() for r in records},
            {"useragents.me"},
        )


if __name__ == "__main__":
    unittest.main()
