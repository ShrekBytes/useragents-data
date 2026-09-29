"""The invariants: merging, ordering, the checks, and the legacy projection."""

import unittest

from uadata import pipeline
from uadata.manifest import Manifest
from uadata.model import CATEGORIES, Record, SourceError, SourceResult, merge_records
from uadata.sources import require_records

PRIMARY = pipeline.ORDERING_SOURCE

CHROME_155 = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
CHROME_134 = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
FIREFOX_156 = "Mozilla/5.0 (X11; Linux x86_64; rv:156.0) Gecko/20100101 Firefox/156.0"
EDGE_154 = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36 Edg/154.0.4258.37"
EDGE_100 = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36 Edg/100.0.0.0"
SAFARI_27 = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/27.0 Safari/605.1.15"
SAFARI_20 = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/20.0 Safari/605.1.15"
OPERA_136 = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 OPR/136.0.6008.52"
OPERA_100 = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36 OPR/100.0.0.0"
SAMSUNG_30 = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/30.0 Chrome/143.0.0.0 Mobile Safari/537.36"
SAMSUNG_20 = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/20.0 Chrome/100.0.0.0 Mobile Safari/537.36"
FXIOS_157 = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) FxiOS/157.0 Mobile/15E148 Safari/605.1.15"
FXIOS_150 = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) FxiOS/150.0 Mobile/15E148 Safari/605.1.15"


def record(ua, **kwargs):
    return Record(user_agent=ua, **kwargs)


class MergeTests(unittest.TestCase):
    def test_provenance_unions(self):
        merged = merge_records(
            record(CHROME_155, sources=("useragents.me",)),
            record(CHROME_155, browser="Chrome 155", sources=("winfuture23",)),
        )
        self.assertEqual(merged.sources, ("useragents.me", "winfuture23"))
        self.assertEqual(merged.browser, "Chrome 155")

    def test_counts_are_never_summed_across_sources(self):
        # 10 from one source and 5 from another does not mean 15. Counts are only
        # comparable within the source that measured them.
        merged = merge_records(
            record(CHROME_155, count=10, count_source="a"),
            record(CHROME_155, count=5, count_source="b"),
        )
        self.assertEqual(merged.count, 10)
        self.assertEqual(merged.count_source, "a")

    def test_the_attribution_travels_with_the_count(self):
        # A number published without saying who measured it is a number no consumer
        # can compare against anything.
        merged = merge_records(
            record(CHROME_155, sources=("a",)), record(CHROME_155, count=5, count_source="b")
        )
        self.assertEqual((merged.count, merged.count_source), (5, "b"))
        self.assertTrue(merged.measured_by("b"))
        self.assertFalse(merged.measured_by("a"))

    def test_the_ordering_sources_measurement_wins_whatever_the_ingestion_order(self):
        # SOURCES is a list, so "first one wins" would silently drop the designated
        # ordering source's number whenever a second counting source is listed first.
        merged = merge_records(
            record(CHROME_155, count=5, count_source="b"),
            record(CHROME_155, count=10, count_source=PRIMARY),
            prefer=PRIMARY,
        )
        self.assertEqual((merged.count, merged.count_source), (10, PRIMARY))

    def test_refuses_to_merge_different_strings(self):
        with self.assertRaises(ValueError):
            merge_records(record(CHROME_155), record(CHROME_134))

    def test_union_across_sources(self):
        merged = pipeline.merge_sources(
            [
                SourceResult(name="a", records={"desktop": [record(CHROME_155, count=1, count_source="a")]}),
                SourceResult(name="b", records={"desktop": [record(FIREFOX_156, count=2, count_source="b")]}),
            ]
        )
        self.assertEqual(len(merged["desktop"]), 2)

    def test_empty_categories_are_dropped(self):
        merged = pipeline.merge_sources([SourceResult(name="a", records={})])
        self.assertEqual(merged, {})


class AttributionTests(unittest.TestCase):
    def test_a_count_with_no_source_is_refused(self):
        # Not at publication time: by then the record is already sitting in the
        # unranked block, where nobody would notice it should have been ranked.
        with self.assertRaises(ValueError):
            record(CHROME_155, count=10)

    def test_a_source_with_no_count_is_refused(self):
        # The other direction is worse: it claims a measurement nobody made, and
        # `measured_by` would sort it into the ranked block as a measured zero,
        # ahead of every real measurement.
        with self.assertRaises(ValueError):
            record(CHROME_155, count_source="a")

    def test_a_percentage_on_its_own_is_refused(self):
        # A share of a sample that was never stated, attributed to nobody. It
        # would otherwise ride through the merge untouched and publish.
        with self.assertRaises(ValueError):
            record(CHROME_155, percentage=2.5)

    def test_a_count_with_a_percentage_keeps_them_together(self):
        both = record(CHROME_155, count=10, percentage=2.5, count_source="a")
        self.assertEqual((both.count, both.percentage, both.count_source), (10, 2.5, "a"))

    def test_a_source_measuring_nothing_publishes_no_numbers_at_all(self):
        plain = record(CHROME_155, sources=("crawler-user-agents",))
        self.assertEqual(
            plain.to_json(),
            {
                "user_agent": CHROME_155,
                "os": None,
                "browser": None,
                "device": None,
                "count": None,
                "percentage": None,
                "count_source": None,
                "sources": ["crawler-user-agents"],
            },
        )


class OrderingTests(unittest.TestCase):
    def test_ranked_first_by_the_ordering_sources_count_then_the_rest_newest_first(self):
        ordered = pipeline.order_records(
            [
                record(FIREFOX_156, sources=(PRIMARY,)),
                record(CHROME_134, count=5, count_source=PRIMARY, sources=(PRIMARY,)),
                record(CHROME_155, count=9, count_source=PRIMARY, sources=(PRIMARY,)),
            ]
        )
        self.assertEqual(
            ordered,
            [
                record(CHROME_155, count=9, count_source=PRIMARY, sources=(PRIMARY,)),
                record(CHROME_134, count=5, count_source=PRIMARY, sources=(PRIMARY,)),
                record(FIREFOX_156, sources=(PRIMARY,)),
            ],
        )

    def test_two_measured_sources_do_not_interleave_into_one_ranking(self):
        # 10,000 hits in one site's sample and 5 in another's says nothing about
        # which is more common. The second source's string is not "less common", it
        # is a different measurement, so it must not sit between two of ours.
        ordered = pipeline.order_records(
            [
                record(SAFARI_27, count=5, count_source="other", sources=("other",)),
                record(CHROME_155, count=1, count_source=PRIMARY, sources=(PRIMARY,)),
                record(CHROME_134, count=10_000, count_source=PRIMARY, sources=(PRIMARY,)),
            ]
        )
        self.assertEqual(
            [r.user_agent for r in ordered],
            [CHROME_134, CHROME_155, SAFARI_27],
        )

    def test_another_sources_measurement_never_enters_the_ranking(self):
        # The shared predicate `order_records` and `apply_caps` both split on. If it
        # ever went back to "count is not None", a second counting source would
        # start buying positions in a ranking it has no standing in.
        other = record(SAFARI_27, count=10**6, count_source="other", sources=("other",))
        ranked, unranked = pipeline.split_ranked([other])
        self.assertEqual((ranked, unranked), ([], [other]))

    def test_the_ranked_block_is_never_broken_by_an_unranked_record(self):
        ranked = [
            record(f"Chrome/{150 + i}.0", count=i + 1, count_source=PRIMARY, sources=(PRIMARY,))
            for i in range(5)
        ]
        unranked = [
            record(f"Chrome/{100 + i}.0", count=10**9, count_source="other", sources=("other",))
            for i in range(3)
        ]
        ordered = pipeline.order_records(ranked + unranked)
        self.assertEqual([r.count for r in ordered[:5]], [5, 4, 3, 2, 1])


class CoverageTests(unittest.TestCase):
    @staticmethod
    def dataset():
        return {
            category: [record(f"{category}-agent", sources=("a", "b"))]
            for category in CATEGORIES
        }

    def test_every_device_category_is_published(self):
        checks = pipeline.check_coverage(self.dataset())
        self.assertTrue(all(c.ok for c in checks), [c.detail for c in checks])
        self.assertEqual(
            [c.name for c in checks], [f"coverage/{c}" for c in CATEGORIES]
        )

    def test_a_missing_category_fails(self):
        # check_regression cannot catch this one: bot strings carry no browser
        # family, so a whole category of crawlers could vanish and publish cleanly.
        merged = self.dataset()
        del merged["bot"]
        bot = next(c for c in pipeline.check_coverage(merged) if c.name == "coverage/bot")
        self.assertFalse(bot.ok)
        self.assertEqual(bot.level, "error")

    def test_the_report_says_how_many_sources_confirmed_each_category(self):
        merged = self.dataset()
        merged["bot"] = [record("Googlebot/2.1", sources=("a",))]
        merged["bot"].append(record("AhrefsBot/7.0", sources=("b",)))
        bot = next(c for c in pipeline.check_coverage(merged) if c.name == "coverage/bot")
        self.assertIn("2 source(s): a, b", bot.detail)
        self.assertEqual(bot.level, "warning")

    def test_a_single_surviving_source_does_not_block_publication(self):
        # ADR-0003: one source down is a degraded build, not a failed one. The
        # category is still published, so the coverage check must not demand a
        # second confirmer.
        merged = {c: [record(f"{c}-agent", sources=("a",))] for c in CATEGORIES}
        self.assertTrue(all(c.ok for c in pipeline.check_coverage(merged)))


class FreshnessTests(unittest.TestCase):
    def setUp(self):
        self.current = Manifest(
            versions={"windows": 155, "firefox": 156, "edge_windows": 154, "safari": 27}
        )

    def test_current_data_passes(self):
        checks = pipeline.check_freshness(
            {
                "desktop": [
                    record(CHROME_155),
                    record(FIREFOX_156),
                    record(EDGE_154),
                    record(SAFARI_27),
                ]
            },
            self.current,
        )
        self.assertTrue(all(c.ok for c in checks), checks)

    def test_one_major_behind_passes(self):
        # ADR-0010: the run is weekly and the source data is at most a week old,
        # so one major behind is the newest thing there was, not a freeze.
        checks = pipeline.check_freshness(
            {"desktop": [record(CHROME_155.replace("155", "154"))]}, self.current
        )
        chrome = next(c for c in checks if c.name == "freshness/chrome")
        self.assertTrue(chrome.ok, chrome.detail)

    def test_two_majors_behind_fails(self):
        # The other side of that boundary, and the shortest freeze the oracle can
        # see. Asserting it in both directions is what makes the tolerance a
        # decision rather than a number that happens to be there.
        checks = pipeline.check_freshness(
            {"desktop": [record(CHROME_155.replace("155", "153"))]}, self.current
        )
        chrome = next(c for c in checks if c.name == "freshness/chrome")
        self.assertFalse(chrome.ok)
        self.assertEqual(chrome.level, "error")
        self.assertIn("153", chrome.detail)

    def test_the_thirteen_month_freeze_fails(self):
        # Exactly the old repo: pipeline healthy, source serving 134, world at 155.
        checks = pipeline.check_freshness({"desktop": [record(CHROME_134)]}, self.current)
        chrome = next(c for c in checks if c.name == "freshness/chrome")
        self.assertFalse(chrome.ok)
        self.assertIn("134", chrome.detail)

    def test_edge_and_safari_are_asserted_against_their_vendors(self):
        # Every family with a vendor feed is checked, not the two that were
        # convenient when this was first written. An unasserted family is a family
        # whose staleness nothing can see.
        checks = pipeline.check_freshness(
            {"desktop": [record(EDGE_154), record(SAFARI_27)]}, self.current
        )
        self.assertTrue(all(c.ok for c in checks), [c.detail for c in checks])
        self.assertEqual(
            sorted(c.name for c in checks),
            ["freshness/chrome", "freshness/edge", "freshness/firefox", "freshness/safari"],
        )

    def test_a_stale_edge_fails(self):
        # Edge carries its own major in `Edg/`, so a dataset that stopped
        # refreshing its Edge strings can look current on the Chrome assertion.
        checks = pipeline.check_freshness(
            {"desktop": [record(CHROME_155), record(EDGE_100)]}, self.current
        )
        edge = next(c for c in checks if c.name == "freshness/edge")
        self.assertFalse(edge.ok)
        self.assertEqual(edge.level, "error")
        self.assertIn("100", edge.detail)

    def test_a_stale_safari_fails(self):
        # Safari is the family most easily asserted for in name only: it rides the
        # operating system release, so a dataset can carry Version/20 for a year
        # with every other family current and nothing else complaining.
        checks = pipeline.check_freshness({"desktop": [record(SAFARI_20)]}, self.current)
        safari = next(c for c in checks if c.name == "freshness/safari")
        self.assertFalse(safari.ok)
        self.assertEqual(safari.level, "error")
        self.assertIn("20", safari.detail)

    def test_missing_manifest_skips_rather_than_passing_silently(self):
        checks = pipeline.check_freshness(
            {"desktop": [record(CHROME_134)]}, Manifest(errors=["vendor down"])
        )
        chrome = next(c for c in checks if c.name == "freshness/chrome")
        self.assertTrue(chrome.ok)
        self.assertEqual(chrome.level, "warning")
        self.assertIn("skipped", chrome.detail)

    def test_no_chrome_at_all_warns_rather_than_failing(self):
        # Absence is a coverage gap. Failing here would let a surviving source that
        # lacks one browser block publication, contradicting ADR-0003. Losing a
        # family we used to have is the regression check's job.
        checks = pipeline.check_freshness({"desktop": [record(FIREFOX_156)]}, self.current)
        chrome = next(c for c in checks if c.name == "freshness/chrome")
        self.assertTrue(chrome.ok)
        self.assertEqual(chrome.level, "warning")
        self.assertIn("no chrome", chrome.detail)


class RegressionTests(unittest.TestCase):
    def test_version_going_backwards_fails(self):
        previous = {"desktop": [{"user_agent": CHROME_155}]}
        checks = pipeline.check_regression({"desktop": [record(CHROME_134)]}, previous)
        self.assertTrue(checks)
        self.assertFalse(any(c.ok for c in checks))

    def test_same_or_newer_passes(self):
        previous = {"desktop": [{"user_agent": CHROME_155}]}
        self.assertEqual(pipeline.check_regression({"desktop": [record(CHROME_155)]}, previous), [])

    def test_a_family_vanishing_is_a_regression(self):
        # The hole found in review: check_freshness only warns when a family is
        # absent, on the grounds that the regression check catches it. It did not,
        # because a family dropping to nothing read as "nothing to compare".
        previous = {"desktop": [{"user_agent": EDGE_154}]}
        checks = pipeline.check_regression({"desktop": [record(CHROME_155)]}, previous)
        self.assertEqual([c.name for c in checks], ["regression/desktop/edge"])
        self.assertFalse(checks[0].ok)

    def test_regression_covers_every_family_not_just_chrome_and_firefox(self):
        cases = [
            ("edge", EDGE_154, EDGE_100),
            ("safari", SAFARI_27, SAFARI_20),
            ("opera", OPERA_136, OPERA_100),
            ("samsung", SAMSUNG_30, SAMSUNG_20),
            ("firefox_ios", FXIOS_157, FXIOS_150),
        ]
        for family, was_ua, now_ua in cases:
            with self.subTest(family=family):
                previous = {"desktop": [{"user_agent": was_ua}]}
                checks = pipeline.check_regression({"desktop": [record(now_ua)]}, previous)
                self.assertTrue(checks, f"{family} regression went unnoticed")
                self.assertEqual(checks[0].name, f"regression/desktop/{family}")
                self.assertFalse(checks[0].ok)

    def test_a_family_we_never_published_is_not_a_regression(self):
        previous = {"desktop": [{"user_agent": CHROME_155}]}
        added = pipeline.check_regression(
            {"desktop": [record(CHROME_155), record(SAFARI_27)]}, previous
        )
        self.assertEqual(added, [])

    def test_a_family_only_a_down_source_held_is_a_degradation_not_a_regression(self):
        # The outage this dataset was built to survive. useragents.me is the only
        # source that confirmed Safari, so when it goes down Safari goes with it —
        # and the build still has to publish what the other two found.
        previous = {"desktop": [{"user_agent": SAFARI_27, "sources": [PRIMARY]}]}
        checks = pipeline.check_regression(
            {"desktop": [record(CHROME_155, sources=("winfuture23",))]},
            previous,
            down={PRIMARY, "crawler-user-agents"},
        )
        self.assertEqual([c.name for c in checks], ["regression/desktop/safari"])
        self.assertTrue(checks[0].ok)
        self.assertEqual(checks[0].level, "warning")
        # The message names who actually held the family, not everyone who is down:
        # a build summary that blames a source for something it never saw is a lie
        # that costs somebody an afternoon.
        self.assertIn(f"confirmed only by {PRIMARY}", checks[0].detail)
        self.assertNotIn("crawler-user-agents", checks[0].detail)

    def test_a_family_a_source_still_up_confirmed_still_fails(self):
        # Attribution is not an excuse. The moment any source that confirmed the
        # family is still answering, losing it is unexplained and a hard failure.
        previous = {
            "desktop": [
                {"user_agent": SAFARI_27, "sources": [PRIMARY]},
                {"user_agent": SAFARI_20, "sources": ["winfuture23"]},
            ]
        }
        checks = pipeline.check_regression({"desktop": []}, previous, down={PRIMARY})
        self.assertFalse(checks[0].ok)
        self.assertEqual(checks[0].level, "error")

    def test_a_version_going_backwards_for_a_down_source_only_warns(self):
        previous = {"desktop": [{"user_agent": CHROME_155, "sources": [PRIMARY]}]}
        checks = pipeline.check_regression(
            {"desktop": [record(CHROME_134, sources=("winfuture23",))]},
            previous,
            down={PRIMARY},
        )
        self.assertTrue(checks[0].ok)
        self.assertIn("155", checks[0].detail)

    def test_older_strings_from_a_source_still_up_do_not_veto_the_explanation(self):
        # Only the records above what we still hold were lost. A category keeps
        # plenty of old strings from a source that is answering, and none of them
        # is the reason the newest version vanished — counting them blocked every
        # run on which a second source was down, which is the outage the second
        # source exists to survive.
        previous = {
            "bot": [
                {"user_agent": CHROME_155.replace("155", "146"), "sources": ["crawler-user-agents"]},
                {"user_agent": CHROME_155.replace("155", "131"), "sources": [PRIMARY]},
                {"user_agent": CHROME_155.replace("155", "126"), "sources": ["crawler-user-agents"]},
            ]
        }
        checks = pipeline.check_regression(
            {"bot": [record(CHROME_155.replace("155", "131"), sources=(PRIMARY,))]},
            previous,
            down={"crawler-user-agents"},
        )
        chrome = next(c for c in checks if c.name == "regression/bot/chrome")
        self.assertTrue(chrome.ok, chrome.detail)
        self.assertIn("146 to 131", chrome.detail)

    def test_an_up_source_that_drops_the_newest_version_still_fails(self):
        # The mirror of the above, and the reason the rule is not a loophole: the
        # lost version has to belong to the down source alone.
        previous = {
            "bot": [
                {"user_agent": CHROME_155.replace("155", "146"), "sources": [PRIMARY, "winfuture23"]},
                {"user_agent": CHROME_155.replace("155", "131"), "sources": [PRIMARY]},
            ]
        }
        checks = pipeline.check_regression(
            {"bot": [record(CHROME_155.replace("155", "131"), sources=(PRIMARY,))]},
            previous,
            down={PRIMARY},
        )
        chrome = next(c for c in checks if c.name == "regression/bot/chrome")
        self.assertFalse(chrome.ok)
        self.assertEqual(chrome.level, "error")

    def test_no_down_sources_means_no_attribution_is_available(self):
        previous = {"desktop": [{"user_agent": SAFARI_27, "sources": [PRIMARY]}]}
        checks = pipeline.check_regression({"desktop": []}, previous)
        self.assertFalse(checks[0].ok)

    def test_a_published_record_with_no_provenance_is_never_excused(self):
        # Provenance we cannot read cannot exonerate anyone. A file published before
        # `sources` existed is not evidence that the source still up never confirmed
        # the version — so the loss stays a failure even when another record in the
        # same category is attributable.
        previous = {
            "desktop": [
                {"user_agent": SAFARI_27, "sources": [PRIMARY]},
                {"user_agent": SAFARI_20},
            ]
        }
        checks = pipeline.check_regression({"desktop": []}, previous, down={PRIMARY})
        self.assertFalse(checks[0].ok)

    def test_provenance_that_is_not_a_list_is_not_provenance(self):
        previous = {"desktop": [{"user_agent": SAFARI_27, "sources": "useragents.me"}]}
        checks = pipeline.check_regression({"desktop": []}, previous, down={PRIMARY})
        self.assertFalse(checks[0].ok)


class ShrinkageTests(unittest.TestCase):
    @staticmethod
    def history(counts):
        return [{"sources": {"s": c}} for c in counts]

    def test_grace_period_for_a_new_source(self):
        checks = pipeline.check_shrinkage(
            [SourceResult(name="s", records={"desktop": [record(CHROME_155)]})], self.history([10, 10])
        )
        self.assertTrue(checks[0].ok)
        self.assertEqual(checks[0].level, "warning")
        self.assertIn("no baseline", checks[0].detail)

    def test_small_drop_warns(self):
        checks = pipeline.check_shrinkage(
            [SourceResult(name="s", records={"desktop": [record(CHROME_155)] * 80})],
            self.history([100] * 6),
        )
        self.assertTrue(checks[0].ok)
        self.assertEqual(checks[0].level, "warning")

    def test_collapse_fails(self):
        # The old scraper's behaviour: source up, valid JSON, a fifth of the rows.
        checks = pipeline.check_shrinkage(
            [SourceResult(name="s", records={"desktop": [record(CHROME_155)] * 10})],
            self.history([100] * 6),
        )
        self.assertFalse(checks[0].ok)
        self.assertEqual(checks[0].level, "error")

    def test_a_down_source_is_reported_not_counted_as_shrinkage(self):
        checks = pipeline.check_shrinkage(
            [SourceResult(name="s", error="timeout")], self.history([100] * 6)
        )
        self.assertTrue(checks[0].ok)
        self.assertIn("source down", checks[0].detail)

    def test_growth_does_not_warn(self):
        checks = pipeline.check_shrinkage(
            [SourceResult(name="s", records={"desktop": [record(CHROME_155)] * 500})],
            self.history([100] * 6),
        )
        self.assertTrue(checks[0].ok)
        self.assertEqual(checks[0].level, "warning")


class CapTests(unittest.TestCase):
    @staticmethod
    def measured(n, start=1, source=PRIMARY):
        return [
            record(f"Chrome/{100 + i}.0", count=start + i, count_source=source, sources=(source,))
            for i in range(n)
        ]

    @staticmethod
    def unmeasured(n):
        return [record(f"Firefox/{200 + i}.0", sources=("s",)) for i in range(n)]

    def test_current_versions_survive_a_flood_of_measured_traffic(self):
        # The whole point of the reservation. Measured frequency is dominated by
        # old strings, so a plain tail cut would evict every current browser.
        ordered = pipeline.order_records(self.measured(400) + self.unmeasured(30))
        capped, discarded = pipeline.apply_caps({"desktop": ordered})
        kept_unmeasured = [r for r in capped["desktop"] if not r.measured_by(PRIMARY)]
        self.assertEqual(len(kept_unmeasured), pipeline.RESERVED_UNRANKED)
        self.assertGreater(discarded, 0)

    def test_another_sources_traffic_cannot_evict_the_current_strings(self):
        # A second counting source does not get to spend the budget on a ranking we
        # never made: its records are ordered and capped as unranked, so a flood of
        # old strings it measured cannot push the current ones out of the file.
        # Under the old "count is not None" split these filled the measured block
        # and cost the newest strings nine of their twenty reserved slots.
        old = [
            record(f"Chrome/{1 + i // 4}.0", count=i + 1, count_source="other", sources=("other",))
            for i in range(300)
        ]
        ordered = pipeline.order_records(old + self.unmeasured(30))
        capped, _ = pipeline.apply_caps({"desktop": ordered})
        kept = {r.user_agent for r in capped["desktop"]}
        self.assertTrue(
            {f"Firefox/{200 + i}.0" for i in range(30)} <= kept,
            "another source's traffic evicted the current strings",
        )

    def test_unmeasured_are_the_newest_ones_kept(self):
        ordered = pipeline.order_records(self.measured(400) + self.unmeasured(50))
        capped, _ = pipeline.apply_caps({"desktop": ordered})
        kept = [r.user_agent for r in capped["desktop"] if r.count is None]
        # Newest first, so the reserved slots go to the most current strings.
        self.assertEqual(kept[:2], ["Firefox/249.0", "Firefox/248.0"])

    def test_category_respects_its_sub_cap(self):
        ordered = pipeline.order_records(self.measured(500) + self.unmeasured(10))
        capped, _ = pipeline.apply_caps({"bot": ordered})
        self.assertEqual(len(capped["bot"]), pipeline.CATEGORY_CAPS["bot"])

    def test_total_never_exceeds_the_budget(self):
        merged = {
            category: pipeline.order_records(self.measured(400) + self.unmeasured(30))
            for category in pipeline.CATEGORY_CAPS
        }
        capped, _ = pipeline.apply_caps(merged)
        self.assertLessEqual(
            sum(len(v) for v in capped.values()), pipeline.TOTAL_CAP
        )

    def test_measured_may_still_fill_the_cap_when_there_is_no_reserve_to_protect(self):
        capped, _ = pipeline.apply_caps({"bot": self.measured(300)})
        self.assertEqual(len(capped["bot"]), pipeline.CATEGORY_CAPS["bot"])
        self.assertTrue(all(r.measured_by(PRIMARY) for r in capped["bot"]))

    def test_an_uncapped_category_is_an_error_not_a_silent_pass(self):
        capped, _ = pipeline.apply_caps({"smart-tv": self.measured(900)})
        check = next(c for c in pipeline.check_caps(capped) if c.name == "cap/categories")
        self.assertFalse(check.ok)
        self.assertIn("smart-tv", check.detail)

    def test_check_caps_passes_on_a_realistic_dataset(self):
        merged = {
            category: pipeline.order_records(self.measured(40) + self.unmeasured(25))
            for category in pipeline.CATEGORY_CAPS
        }
        checks = pipeline.check_caps(merged)
        self.assertTrue(all(c.ok for c in checks), [c.detail for c in checks])


class LegacyProjectionTests(unittest.TestCase):
    def test_only_the_ordering_sources_ranking_appears(self):
        # A "most common" list must not contain strings we cannot say are common.
        payload = pipeline.build_legacy(
            "desktop",
            [
                record(CHROME_155, count=9, count_source=PRIMARY, sources=(PRIMARY,)),
                record(FIREFOX_156, sources=(PRIMARY,)),
            ],
            "2026-09-29T00:00:00+00:00",
        )
        self.assertEqual(payload["user_agents"], [CHROME_155])
        self.assertEqual(payload["type"], "most_common_desktop")
        self.assertEqual(payload["scraped_from"], [PRIMARY])

    def test_another_sources_measurements_are_not_mixed_into_the_ranking(self):
        # Two samples compared is not a ranking. The ordering already keeps them
        # apart; this file is the place a consumer reads as a popularity list.
        payload = pipeline.build_legacy(
            "desktop",
            [
                record(CHROME_155, count=9, count_source=PRIMARY, sources=(PRIMARY,)),
                record(FIREFOX_156, count=9999, count_source="other", sources=("other",)),
            ],
            "2026-09-29T00:00:00+00:00",
        )
        self.assertEqual(payload["user_agents"], [CHROME_155])

    def test_it_is_empty_and_claims_nothing_when_no_source_measured_anything(self):
        # The honest result on a run where the ordering source is down: there is no
        # "most common" to publish, and `scraped_from` must not name a source whose
        # strings are not in the file. data/ still carries the current strings.
        payload = pipeline.build_legacy(
            "desktop",
            [record(CHROME_155, sources=("winfuture23",))],
            "2026-09-29T00:00:00+00:00",
        )
        self.assertEqual(payload["user_agents"], [])
        self.assertEqual(payload["scraped_from"], [])


class ValidationTests(unittest.TestCase):
    def test_rejects_empty_list(self):
        with self.assertRaises(SourceError):
            require_records([], "week-desktop")

    def test_rejects_wrong_type(self):
        with self.assertRaises(SourceError):
            require_records({"rows": []}, "week-desktop")

    def test_rejects_row_without_user_agent(self):
        with self.assertRaises(SourceError):
            require_records([{"count": 1}], "week-desktop")

    def test_rejects_blank_user_agent(self):
        with self.assertRaises(SourceError):
            require_records([{"user_agent": "   "}], "week-desktop")

    def test_accepts_good_payload(self):
        self.assertEqual(require_records([{"user_agent": CHROME_155}], "x"), [{"user_agent": CHROME_155}])


if __name__ == "__main__":
    unittest.main()
