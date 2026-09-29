"""The invariants: merging, ordering, the three checks, and the legacy projection."""

import unittest

from uadata import pipeline
from uadata.manifest import Manifest
from uadata.model import Record, SourceError, SourceResult, merge_records
from uadata.sources import require_records

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
            record(CHROME_155, count=10, sources=("a",)),
            record(CHROME_155, count=5, sources=("b",)),
        )
        self.assertEqual(merged.count, 10)

    def test_refuses_to_merge_different_strings(self):
        with self.assertRaises(ValueError):
            merge_records(record(CHROME_155), record(CHROME_134))

    def test_union_across_sources(self):
        merged = pipeline.merge_sources(
            [
                SourceResult(name="a", records={"desktop": [record(CHROME_155, count=1, sources=("a",))]}),
                SourceResult(name="b", records={"desktop": [record(FIREFOX_156, count=2, sources=("b",))]}),
            ]
        )
        self.assertEqual(len(merged["desktop"]), 2)

    def test_empty_categories_are_dropped(self):
        merged = pipeline.merge_sources([SourceResult(name="a", records={})])
        self.assertEqual(merged, {})


class OrderingTests(unittest.TestCase):
    def test_measured_first_by_count_then_unmeasured_newest_first(self):
        ordered = pipeline.order_records(
            [
                record(FIREFOX_156, sources=("a",)),
                record(CHROME_134, count=5, sources=("a",)),
                record(CHROME_155, count=9, sources=("a",)),
            ]
        )
        self.assertEqual(
            ordered,
            [
                record(CHROME_155, count=9, sources=("a",)),
                record(CHROME_134, count=5, sources=("a",)),
                record(FIREFOX_156, sources=("a",)),
            ],
        )


class FreshnessTests(unittest.TestCase):
    def setUp(self):
        self.current = Manifest(versions={"windows": 155, "firefox": 156})

    def test_current_data_passes(self):
        checks = pipeline.check_freshness(
            {"desktop": [record(CHROME_155), record(FIREFOX_156)]}, self.current
        )
        self.assertTrue(all(c.ok for c in checks), checks)

    def test_one_major_behind_passes(self):
        checks = pipeline.check_freshness(
            {"desktop": [record(CHROME_134.replace("134", "154"))]}, self.current
        )
        chrome = next(c for c in checks if c.name == "freshness/chrome")
        self.assertTrue(chrome.ok, chrome.detail)

    def test_the_thirteen_month_freeze_fails(self):
        # Exactly the old repo: pipeline healthy, source serving 134, world at 155.
        checks = pipeline.check_freshness({"desktop": [record(CHROME_134)]}, self.current)
        chrome = next(c for c in checks if c.name == "freshness/chrome")
        self.assertFalse(chrome.ok)
        self.assertIn("134", chrome.detail)

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
    def measured(n, start=1):
        return [record(f"Chrome/{100 + i}.0", count=start + i, sources=("s",)) for i in range(n)]

    @staticmethod
    def unmeasured(n):
        return [record(f"Firefox/{200 + i}.0", sources=("s",)) for i in range(n)]

    def test_current_versions_survive_a_flood_of_measured_traffic(self):
        # The whole point of the reservation. Measured frequency is dominated by
        # old strings, so a plain tail cut would evict every current browser.
        ordered = pipeline.order_records(self.measured(400) + self.unmeasured(30))
        capped, discarded = pipeline.apply_caps({"desktop": ordered})
        kept_unmeasured = [r for r in capped["desktop"] if r.count is None]
        self.assertEqual(len(kept_unmeasured), pipeline.RESERVED_UNMEASURED)
        self.assertGreater(discarded, 0)

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
        self.assertTrue(all(r.count is not None for r in capped["bot"]))

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
    def test_only_measured_records_appear(self):
        # A "most common" list must not contain strings we cannot say are common.
        payload = pipeline.build_legacy(
            "desktop",
            [record(CHROME_155, count=9, sources=("a",)), record(FIREFOX_156, sources=("a",))],
            [SourceResult(name="a")],
            "2026-09-29T00:00:00+00:00",
        )
        self.assertEqual(payload["user_agents"], [CHROME_155])
        self.assertEqual(payload["type"], "most_common_desktop")


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
