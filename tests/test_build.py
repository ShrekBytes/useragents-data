"""End-to-end behaviour of the build, against fakes rather than the network.

The regression these protect is the one that cost this repo 13 months of stale
data: the pipeline ran green every day against a source serving browser 134 while
the world moved to 155, and nothing compared the output against anything.
"""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import scraper
from uadata import pipeline
from uadata.manifest import Manifest
from uadata.model import CATEGORIES, Record, SourceError, SourceResult

CURRENT = Manifest(versions={"windows": 155, "mac": 155, "android": 155, "firefox": 156})

# The source whose measured frequency defines the published order. The fakes below
# stand in for it whenever a test needs a count to mean anything.
PRIMARY = pipeline.ORDERING_SOURCE

# A string no parser recognises, so it carries no browser family and therefore
# cannot make a stale dataset look fresh or a current one look stale.
NEUTRAL = "a-string-no-parser-recognises"


def fill_categories(records):
    """Fill the Device Categories the test did not supply.

    Every build publishes all four, and an empty one fails the coverage check, so a
    test that only exercises desktop still has to say what the rest hold.
    """
    filler = Record(NEUTRAL, sources=("s",))
    return {category: records.get(category, [filler]) for category in CATEGORIES}


def ua(major):
    return (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
    )


EDGETAG = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36 Edg/154.0.4258.37"
)

SAFARITAG = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/27.0 Safari/605.1.15"
)

GOOGLEBOT = "Googlebot/2.1 (+http://www.google.com/bot.html)"


class FakeSource:
    def __init__(self, name, records=None, error=None):
        self.name = name
        self.records = records or {}
        self.error = error

    def fetch(self, session):
        if self.error:
            raise SourceError(self.error)
        return SourceResult(name=self.name, records=self.records)


def desktop(*majors, counts=False, source=PRIMARY):
    return [
        Record(
            user_agent=ua(m),
            count=i + 1 if counts else None,
            count_source=source if counts else None,
            sources=(source,),
        )
        for i, m in enumerate(majors)
    ]


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.cwd = os.getcwd()
        os.chdir(self.dir)
        self.addCleanup(os.chdir, self.cwd)

    def build(self, sources, manifest=CURRENT, argv=None, fill=True):
        # The scraper narrates to stdout; keep it out of the test report.
        if fill:
            sources = [
                FakeSource(s.name, fill_categories(s.records), s.error) for s in sources
            ]
        with contextlib.redirect_stdout(io.StringIO()), mock.patch.object(
            scraper, "SOURCES", sources
        ), mock.patch.object(scraper, "fetch_manifest", return_value=manifest):
            return scraper.main(argv or [])

    def seed_history(self, name, counts, runs=6):
        os.makedirs("state", exist_ok=True)
        with open("state/history.json", "w", encoding="utf-8") as handle:
            json.dump({"runs": [{"sources": {name: c}} for c in counts[:runs]]}, handle)

    def published(self, category="desktop"):
        with open(f"data/{category}.json", encoding="utf-8") as handle:
            return json.load(handle)

    # --- the failure that actually happened ---------------------------------

    def test_stale_source_does_not_publish(self):
        code = self.build([FakeSource("s", {"desktop": desktop(134)})])
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists("data/desktop.json"))

    def test_a_source_serving_an_empty_list_is_a_failure_not_a_result(self):
        # require_records rejects this before it can become a quietly smaller file.
        # No filler: the point is that an empty category is not quietly repopulated.
        code = self.build([FakeSource("s", {"desktop": []})], fill=False)
        self.assertEqual(code, 1)

    def test_every_source_down_publishes_nothing(self):
        code = self.build([FakeSource("a", error="timeout"), FakeSource("b", error="404")])
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists("data"))

    def test_a_device_category_that_empties_out_blocks_publication(self):
        # check_regression cannot see this one: bot strings carry no browser family,
        # so the whole category could vanish and the file would simply stop existing.
        code = self.build([FakeSource("s", {"desktop": desktop(155)})], fill=False)
        self.assertEqual(code, 1)

    # --- resilience, not perfection ---------------------------------------

    def test_one_source_down_does_not_block_the_other(self):
        code = self.build(
            [FakeSource(PRIMARY, {"desktop": desktop(155, counts=True)}), FakeSource("dead", error="504")]
        )
        self.assertEqual(code, 0)
        statuses = {s["name"]: s["status"] for s in self.published()["sources"]}
        self.assertEqual(statuses, {PRIMARY: "ok", "dead": "failed"})

    def test_the_primary_source_being_down_still_publishes_current_data(self):
        # The whole point of adding a second source: useragents.me going away costs
        # the frequency counts, not the dataset.
        self.assertEqual(
            self.build([FakeSource(PRIMARY, {"desktop": desktop(155, counts=True)})]), 0
        )
        self.assertEqual(
            self.build(
                [
                    FakeSource(PRIMARY, error="503"),
                    FakeSource("winfuture23", {"desktop": desktop(155, source="winfuture23")}),
                ]
            ),
            0,
        )
        payload = self.published("desktop")
        self.assertIn(ua(155), [r["user_agent"] for r in payload["user_agents"]])
        self.assertEqual(
            {r["count"] for r in payload["user_agents"]}, {None}, "no source measured this"
        )
        with open("common/desktop.json", encoding="utf-8") as handle:
            legacy = json.load(handle)
        # The legacy file is the ordering source's ranking, and there is none.
        self.assertEqual(legacy["user_agents"], [])

    def test_the_ordering_source_going_away_does_not_block_publication(self):
        # The outage this dataset was built to survive, end to end. The source that
        # measured everything is also the only one that confirmed Safari and Edge,
        # so its records leave with it — and the regression check has to trace each
        # lost family back to a source that is actually down rather than blocking
        # every future run. Without that, the second source is decorative.
        def sources(measured):
            return [
                FakeSource(
                    PRIMARY,
                    records={"desktop": desktop(155, counts=True) + [
                        Record(SAFARITAG, sources=(PRIMARY,)),
                        Record(EDGETAG, sources=(PRIMARY,)),
                    ]},
                    error=None if measured else "503",
                ),
                FakeSource("winfuture23", {"desktop": desktop(155, source="winfuture23")}),
                FakeSource("crawler-user-agents", {"bot": [Record(GOOGLEBOT, sources=("crawler-user-agents",))]}),
            ]

        self.assertEqual(self.build(sources(measured=True)), 0)
        self.assertEqual(self.build(sources(measured=False)), 0)

        published = self.published("desktop")
        self.assertIn(ua(155), [r["user_agent"] for r in published["user_agents"]])
        self.assertNotIn(SAFARITAG, [r["user_agent"] for r in published["user_agents"]])
        # Bot coverage is untouched: it never depended on the source that went away.
        self.assertIn(GOOGLEBOT, [r["user_agent"] for r in self.published("bot")["user_agents"]])

    def test_a_family_an_up_source_confirmed_still_blocks_publication(self):
        # Attribution is not a loophole. A source that is still answering and drops
        # a family it confirmed last run has lost it for no stated reason, and the
        # outage of a different source does not cover for it.
        safari = Record(SAFARITAG, sources=(PRIMARY, "winfuture23"))
        self.assertEqual(
            self.build(
                [
                    FakeSource(PRIMARY, {"desktop": desktop(155, counts=True) + [safari]}),
                    FakeSource("winfuture23", {"desktop": desktop(155, source="winfuture23") + [safari]}),
                ]
            ),
            0,
        )
        code = self.build(
            [
                FakeSource(PRIMARY, error="503"),
                FakeSource("winfuture23", {"desktop": desktop(155, source="winfuture23")}),
            ]
        )
        self.assertEqual(code, 1)

    def test_a_second_counting_source_cannot_displace_the_ordering_sources_number(self):
        # `SOURCES` is a list, and a second counting source added to it could easily
        # be listed first. First-one-wins would then publish the other sample's
        # number and drop ours, and the record would fall out of the ranking
        # entirely — the exact failure the ordering rule exists to prevent.
        mine = Record(ua(155), count=100, count_source=PRIMARY, sources=(PRIMARY,))
        theirs = Record(ua(155), count=7, count_source="other", sources=("other",))
        code = self.build(
            [
                FakeSource("other", {"desktop": [theirs]}),
                FakeSource(PRIMARY, {"desktop": [mine]}),
            ]
        )
        self.assertEqual(code, 0)
        published = self.published()["user_agents"][0]
        self.assertEqual((published["count"], published["count_source"]), (100, PRIMARY))
        with open("common/desktop.json", encoding="utf-8") as handle:
            self.assertEqual(json.load(handle)["user_agents"], [ua(155)])

    def test_shrinkage_is_not_blamed_on_a_source_that_is_down(self):
        # Attributable means attributable: another source being unreachable explains
        # its own absence, not a collapse in a source that is up and answering.
        self.seed_history("s", [100] * 6)
        code = self.build(
            [FakeSource("s", {"desktop": desktop(155) * 5}), FakeSource("dead", error="timeout")]
        )
        self.assertEqual(code, 1)

    def test_a_source_that_shrinks_while_still_up_fails_the_run(self):
        self.seed_history("s", [100] * 6)
        code = self.build([FakeSource("s", {"desktop": desktop(155) * 10})])
        self.assertEqual(code, 1)

    def test_a_source_at_a_normal_size_passes_its_baseline(self):
        self.seed_history("s", [100] * 6)
        code = self.build([FakeSource("s", {"desktop": desktop(155) * 100})])
        self.assertEqual(code, 0)

    def test_published_data_may_not_go_backwards(self):
        self.assertEqual(self.build([FakeSource("s", {"desktop": desktop(155)})]), 0)
        self.assertEqual(self.build([FakeSource("s", {"desktop": desktop(140)})]), 1)

    # --- the happy path, and what it promises ------------------------------

    def test_fresh_data_is_published_with_provenance(self):
        self.assertEqual(self.build([FakeSource(PRIMARY, {"desktop": desktop(155, counts=True)})]), 0)
        payload = self.published()
        self.assertEqual(payload["schema_version"], 3)
        self.assertEqual(payload["sources"][0]["name"], PRIMARY)
        self.assertEqual(payload["user_agents"][0]["sources"], [PRIMARY])
        self.assertEqual(payload["user_agents"][0]["count_source"], PRIMARY)

    def test_two_sources_confirming_one_string_name_both(self):
        # Provenance is the record of who saw it, and no source is more real than
        # the other. A record both saw must be able to say so, and the measurement
        # must still be attributed to the one that made it.
        both = {PRIMARY: {"desktop": desktop(155, counts=True)}}
        other = {
            "winfuture23": {
                "desktop": [Record(ua(155), browser="Chrome 155.0.0", sources=("winfuture23",))]
            }
        }
        self.assertEqual(self.build([FakeSource(PRIMARY, both[PRIMARY]), FakeSource("winfuture23", other["winfuture23"])]), 0)
        record = self.published()["user_agents"][0]
        self.assertEqual(record["sources"], sorted([PRIMARY, "winfuture23"]))
        self.assertEqual(record["browser"], "Chrome 155.0.0")
        self.assertEqual(record["count_source"], PRIMARY)

    def test_legacy_projection_keeps_the_v1_shape(self):
        self.build([FakeSource(PRIMARY, {"desktop": desktop(155, counts=True)})])
        with open("common/desktop.json", encoding="utf-8") as handle:
            legacy = json.load(handle)
        self.assertEqual(legacy["type"], "most_common_desktop")
        self.assertEqual(legacy["user_agents"], [ua(155)])
        self.assertEqual(legacy["scraped_from"], [PRIMARY])

    def test_a_family_that_vanishes_blocks_publication(self):
        # End to end: the review hole. Freshness only warns on an absent family, so
        # without the regression check a browser could quietly drop out of a file
        # that used to contain it and still publish.
        self.assertEqual(
            self.build([FakeSource("s", {"desktop": [Record(ua(155), sources=("s",)), Record(EDGETAG, sources=("s",))]})]),
            0,
        )
        self.assertEqual(self.build([FakeSource("s", {"desktop": [Record(ua(155), sources=("s",))]})]), 1)

    def test_check_mode_writes_nothing(self):
        code = self.build([FakeSource("s", {"desktop": desktop(155)})], argv=["--check"])
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists("data"))
        self.assertFalse(os.path.exists("common"))

    def test_freshness_reports_both_scopes(self):
        # bot.json holds Chrome 131 while the collection holds 154. Publishing only
        # the per-file number would read as a stale dataset.
        self.build(
            [
                FakeSource(
                    "s",
                    {
                        "bot": [Record(ua(131), sources=("s",))],
                        "desktop": [Record(ua(155), sources=("s",))],
                    },
                )
            ]
        )
        freshness = self.published("bot")["freshness"]
        self.assertEqual(freshness["in_this_file_max_majors"]["chrome"], 131)
        self.assertEqual(freshness["collection_max_majors"]["chrome"], 155)
        self.assertEqual(freshness["manifest"]["versions"]["windows"], 155)

    def test_history_accumulates_for_the_baseline(self):
        self.build([FakeSource("s", {"desktop": desktop(155) * 3})])
        with open("state/history.json", encoding="utf-8") as handle:
            runs = json.load(handle)["runs"]
        self.assertEqual(len(runs), 1)
        # Three supplied, plus one filler in each of the other three categories.
        self.assertEqual(runs[0]["sources"]["s"], 6)


if __name__ == "__main__":
    unittest.main()
