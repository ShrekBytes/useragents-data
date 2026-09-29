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
from uadata.manifest import Manifest
from uadata.model import Record, SourceError, SourceResult

CURRENT = Manifest(versions={"windows": 155, "mac": 155, "android": 155, "firefox": 156})


def ua(major):
    return (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
    )


EDGETAG = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36 Edg/154.0.4258.37"
)


class FakeSource:
    def __init__(self, name, records=None, error=None):
        self.name = name
        self.records = records or {}
        self.error = error

    def fetch(self, session):
        if self.error:
            raise SourceError(self.error)
        return SourceResult(name=self.name, records=self.records)


def desktop(*majors, counts=False):
    return [
        Record(user_agent=ua(m), count=i + 1 if counts else None, sources=("s",))
        for i, m in enumerate(majors)
    ]


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.cwd = os.getcwd()
        os.chdir(self.dir)
        self.addCleanup(os.chdir, self.cwd)

    def build(self, sources, manifest=CURRENT, argv=None):
        # The scraper narrates to stdout; keep it out of the test report.
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
        code = self.build([FakeSource("s", {"desktop": []})])
        self.assertEqual(code, 1)

    def test_every_source_down_publishes_nothing(self):
        code = self.build([FakeSource("a", error="timeout"), FakeSource("b", error="404")])
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists("data"))

    # --- resilience, not perfection ---------------------------------------

    def test_one_source_down_does_not_block_the_other(self):
        code = self.build(
            [FakeSource("s", {"desktop": desktop(155, counts=True)}), FakeSource("dead", error="504")]
        )
        self.assertEqual(code, 0)
        statuses = {s["name"]: s["status"] for s in self.published()["sources"]}
        self.assertEqual(statuses, {"s": "ok", "dead": "failed"})

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
        self.assertEqual(self.build([FakeSource("s", {"desktop": desktop(155, counts=True)})]), 0)
        payload = self.published()
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["sources"][0]["name"], "s")
        self.assertEqual(payload["user_agents"][0]["sources"], ["s"])

    def test_legacy_projection_keeps_the_v1_shape(self):
        self.build([FakeSource("s", {"desktop": desktop(155, counts=True)})])
        with open("common/desktop.json", encoding="utf-8") as handle:
            legacy = json.load(handle)
        self.assertEqual(legacy["type"], "most_common_desktop")
        self.assertEqual(legacy["user_agents"], [ua(155)])
        self.assertEqual(legacy["scraped_from"], ["s"])

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
        self.assertEqual(runs[0]["sources"]["s"], 3)


if __name__ == "__main__":
    unittest.main()
