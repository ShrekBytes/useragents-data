"""The separation guarantee, the generator, and the fidelity bar.

Three things are asserted here that nothing else can assert:

- a Synthetic string is built from the manifest, and the tokens in it are the
  ones a real client sends
- no published file can hold both kinds, whatever is handed to the builder
- every generated string is identified correctly by two independent real parsers

The last one is the point of the whole feature. A generator that produces a
structurally wrong string — the Gecko tokens on a Chromium string, `Edg/` without
its `Chrome/`, a Chrome browser token on an iOS device — ships something no parser
can place, and the damage lands on whoever sends it.
"""

import json
import os
import unittest
from unittest import mock

from uadata import browsers, fidelity, pipeline, synthetic
from uadata.manifest import Manifest
from uadata.model import KINDS, OBSERVED, SYNTHETIC, MixedKindsError, Record

CURRENT = Manifest(
    versions={
        "windows": 155,
        "mac": 155,
        "linux": 154,
        "android": 155,
        "firefox": 156,
        "firefox_esr": 140,
        "edge_windows": 154,
        "edge_macos": 154,
        "edge_linux": 154,
    }
)

# The exact strings a current release of each product sends, at CURRENT's
# versions. Written out rather than generated, because the whole claim is that the
# generator agrees with reality: a test that built the expectation with the same
# code it is testing would agree with any bug.
EXPECTED = {
    "chrome-windows": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36",
    "chrome-mac": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36",
    "chrome-linux": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36",
    # `Android 10; K` is Chromium's frozen platform token, not a claim about the
    # device. Reduction reduced the Android version and the model to that literal
    # precisely so a current Chrome would not be sending a live Android version.
    "chrome-android": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/155.0.0.0 Mobile Safari/537.36",
    # Same string minus `Mobile`. That one token is the whole difference between
    # the phone and the tablet, and getting it wrong files a phone under tablet.
    "chrome-android-tablet": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36",
    # Chromium Edge reports the same major in both tokens, because it is the same
    # Chromium. Taking `Chrome/` from one vendor feed and `Edg/` from another
    # produces a string no Edge build has ever sent.
    "edge-windows": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36 Edg/154.0.0.0",
    "edge-mac": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36 Edg/154.0.0.0",
    "edge-linux": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36 Edg/154.0.0.0",
    # Firefox carries no AppleWebKit and no Safari token, and repeats the version
    # inside the platform comment as `rv:`. It is the shape most often rebuilt as
    # if it were a Chromium string.
    "firefox-firefox-windows": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:156.0) "
    "Gecko/20100101 Firefox/156.0",
    # `10.15` with dots, against Chromium's `10_15_7` with underscores. Both are
    # frozen; neither is the macOS version.
    "firefox-firefox-mac": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:156.0) "
    "Gecko/20100101 Firefox/156.0",
    "firefox-firefox-linux": "Mozilla/5.0 (X11; Linux x86_64; rv:156.0) "
    "Gecko/20100101 Firefox/156.0",
    "firefox-firefox_esr-windows": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) "
    "Gecko/20100101 Firefox/140.0",
    "firefox-firefox_esr-mac": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:140.0) "
    "Gecko/20100101 Firefox/140.0",
    "firefox-firefox_esr-linux": "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) "
    "Gecko/20100101 Firefox/140.0",
}


def records(manifest=CURRENT, observed=()):
    return synthetic.build(manifest, observed)


class GeneratorTests(unittest.TestCase):
    def test_every_string_is_the_one_a_current_client_sends(self):
        generated, _ = records()
        self.assertEqual({r.synthesized_from: r.user_agent for r in generated}, EXPECTED)

    def test_every_template_is_generated(self):
        # A template that stopped being generated would take a browser out of the
        # dataset without anybody deciding to. The set of names is the contract.
        generated, _ = records()
        self.assertEqual(
            sorted(r.synthesized_from for r in generated), sorted(EXPECTED)
        )
        self.assertEqual(len(synthetic.TEMPLATES), len(EXPECTED))

    def test_versions_come_from_the_manifest_and_nowhere_else(self):
        # ADR-0005: the generator and the staleness oracle read one artifact, so
        # they cannot disagree about what "current" means. Advancing the manifest
        # advances every string built from it.
        advanced = Manifest(
            versions={**CURRENT.versions, "windows": 156, "edge_windows": 155}
        )
        generated, _ = records(advanced)
        by_name = {r.synthesized_from: r.user_agent for r in generated}
        self.assertIn("Chrome/156.0.0.0", by_name["chrome-windows"])
        # Edge takes its own feed's number, and both its tokens move together.
        self.assertIn("Chrome/155.0.0.0 Safari/537.36 Edg/155.0.0.0", by_name["edge-windows"])

    def test_a_missing_manifest_entry_generates_nothing(self):
        # Not a default, and not the last value we happened to see. A version we
        # cannot read is a version we cannot vouch for, and the freshness check
        # skips for exactly the same reason.
        partial = Manifest(versions={"windows": 155})
        generated, _ = records(partial)
        self.assertEqual([r.synthesized_from for r in generated], ["chrome-windows"])

    def test_every_platform_appears_in_every_platform_table(self):
        # Four parallel dicts keyed by platform, and a key added to one of them and
        # not the others fails at the moment that platform is used, as a KeyError in
        # the middle of a build rather than as a test failure. So the keys are
        # asserted equal here.
        tables = {
            name: getattr(synthetic, name)
            for name in (
                "CHROMIUM_PLATFORMS",
                "GECKO_PLATFORMS",
                "OS_FAMILIES",
                "OS_LABELS",
            )
        }
        desktop = set(synthetic.CHROMIUM_PLATFORMS) - {"android"}
        expected_keys = {
            "CHROMIUM_PLATFORMS": set(synthetic.CHROMIUM_PLATFORMS),
            # Gecko is only ever asked for the desktop platforms, so it has no
            # Android token and must not grow one: Firefox on Android genuinely
            # reports the device's Android version, which is why it is not generated.
            "GECKO_PLATFORMS": desktop,
            "OS_FAMILIES": set(synthetic.CHROMIUM_PLATFORMS),
            "OS_LABELS": set(synthetic.CHROMIUM_PLATFORMS),
        }
        for name, keys in expected_keys.items():
            with self.subTest(table=name):
                self.assertEqual(set(tables[name]), keys)
        self.assertEqual({t.platform for t in synthetic.TEMPLATES}, set(synthetic.CHROMIUM_PLATFORMS))
        self.assertNotIn(
            "android",
            synthetic.GECKO_PLATFORMS,
            "a Gecko Android token would mean inventing the device's Android version",
        )

    def test_a_template_whose_platform_has_no_token_cannot_be_rendered(self):
        # The guard for a future platform added to TEMPLATES without a token. A
        # KeyError from the renderer would abort the run with a traceback; refusing
        # to generate says which template is at fault.
        template = synthetic.Template(
            name="chrome-plan9",
            product="windows",
            platform="plan9",
            engine="chromium",
            family="chrome",
            category="desktop",
            os="plan9",
        )
        with self.assertRaises(KeyError):
            synthetic.render(template, 155)

    def test_no_synthetic_record_may_claim_a_frequency(self):
        # Refused at construction, not at publication: by then the record is in the
        # file wearing the one label that says nobody can vouch for it.
        with self.assertRaises(ValueError):
            Record(
                user_agent=EXPECTED["chrome-windows"],
                kind=SYNTHETIC,
                count=5,
                count_source="useragents.me",
                synthesized_from="chrome-windows",
            )

    def test_a_synthetic_record_must_name_the_template_that_built_it(self):
        # Otherwise it is a string of unknown manufacture wearing the Synthetic
        # label, and there is no record anywhere of how it was made.
        with self.assertRaises(ValueError):
            Record(user_agent=EXPECTED["chrome-windows"], kind=SYNTHETIC)

    def test_an_observed_record_may_not_name_a_template(self):
        with self.assertRaises(ValueError):
            Record(user_agent=EXPECTED["chrome-windows"], synthesized_from="chrome-windows")

    def test_every_record_declares_its_kind(self):
        # The point of the field: a consumer holding one record, with no idea which
        # file it came out of, can still tell what claim to make about it.
        for kind in KINDS:
            row = Record(
                user_agent="x", kind=kind, synthesized_from="t" if kind == SYNTHETIC else None
            ).to_json()
            self.assertEqual(row["kind"], kind)

    def test_an_unknown_kind_is_refused(self):
        with self.assertRaises(ValueError):
            Record(user_agent="x", kind="observed-ish")


class SeparationTests(unittest.TestCase):
    """Observed and Synthetic never share a file (ADR-0002)."""

    observed = Record(user_agent=EXPECTED["chrome-windows"], sources=("a",))
    fabricated = Record(
        user_agent="a string nobody ever sent",
        kind=SYNTHETIC,
        synthesized_from="chrome-windows",
    )

    def test_a_mixed_set_is_refused_by_both_publishers(self):
        # Both, because both files are opened by a consumer who reads a list and
        # does not read a schema. Neither may be the only thing standing between a
        # fabricated string and somebody's User-Agent header.
        for build in (
            lambda records: pipeline.build_payload(
                "desktop", records, [], CURRENT, "now"
            ),
            lambda records: pipeline.build_legacy("desktop", records, "now"),
        ):
            with self.subTest(build=build):
                with self.assertRaises(MixedKindsError):
                    build([self.observed, self.fabricated])

    def test_the_right_records_in_the_wrong_dataset_are_refused_too(self):
        # A Synthetic record reaching the Observed dataset is as wrong as a mixed
        # file, and would not be caught by looking for a second kind.
        with self.assertRaises(MixedKindsError):
            pipeline.build_payload("desktop", [self.fabricated], [], CURRENT, "now")
        with self.assertRaises(MixedKindsError):
            pipeline.build_synthetic_payload("desktop", [self.observed], CURRENT, "now")

    def test_two_records_of_one_kind_publish(self):
        # Otherwise the guard is not a separation rule but a size limit, and a
        # future category with one kind in it would fail for no stated reason.
        self.assertEqual(
            pipeline.build_payload("desktop", [self.observed], [], CURRENT, "now")["kind"],
            OBSERVED,
        )
        self.assertEqual(
            pipeline.build_synthetic_payload(
                "desktop", [self.fabricated], CURRENT, "now"
            )["kind"],
            SYNTHETIC,
        )

    def test_the_check_names_the_category_that_is_mixed(self):
        checks = pipeline.check_separation(
            {"desktop": [self.observed, self.fabricated], "bot": [self.observed]}
        )
        by_name = {c.name: c for c in checks}
        self.assertFalse(by_name["separation/desktop"].ok)
        self.assertEqual(by_name["separation/desktop"].level, "error")
        self.assertTrue(by_name["separation/bot"].ok)

    def test_the_check_states_the_kind_of_what_was_published(self):
        checks = pipeline.check_separation({"desktop": [self.observed]})
        self.assertEqual(checks[0].level, "warning")
        self.assertIn("1 observed records", checks[0].detail)

    def test_a_synthetic_string_that_is_also_observed_is_a_failure(self):
        # A string cannot have been both witnessed and built. The generator refuses
        # to emit one; this is what proves it did.
        generated, withheld = records()
        clash = {r.user_agent for r in generated} & {self.observed.user_agent}
        self.assertNotEqual(clash, set(), "fixture no longer collides; fix the test")
        check = next(
            c for c in pipeline.check_synthetic(generated, {"desktop": [self.observed]}, withheld)
            if c.name == "synthetic/collision"
        )
        self.assertFalse(check.ok)
        self.assertEqual(check.level, "error")
        self.assertIn(self.observed.user_agent, check.detail)

    def test_the_generator_withholds_a_string_it_has_already_observed(self):
        # Rather than publishing it as a fabrication. A string we hold as real is
        # published as real, and calling it synthetic would make the dataset's one
        # promise untrue.
        generated, withheld = records(observed=[EXPECTED["chrome-windows"]])
        self.assertNotIn(EXPECTED["chrome-windows"], {r.user_agent for r in generated})
        self.assertIn(
            synthetic.Withheld("chrome-windows", "already Observed"), withheld
        )

    def test_a_withheld_template_is_named_rather_than_silently_dropped(self):
        # A template quietly vanishing is how a browser leaves the dataset without
        # anybody deciding to, and a count alone would not say which.
        generated, withheld = records(observed=[EXPECTED["chrome-windows"]])
        check = next(
            c
            for c in pipeline.check_synthetic(generated, {}, withheld)
            if c.name == "synthetic/withheld[already Observed]"
        )
        self.assertTrue(check.ok)
        self.assertEqual(check.level, "warning")
        self.assertIn("chrome-windows", check.detail)

    def test_a_template_with_no_manifest_entry_is_named_too(self):
        # The other silent reason, and the one that needs a human. A vendor outage
        # would otherwise take most of the templates out of the dataset with nothing
        # in the build summary to say so. It does not fail the build — refusing to
        # publish for a vendor being down is exactly what ADR-0003 forbids — but it
        # is an error-level annotation, so it is not a run that looks healthy.
        generated, withheld = records(manifest=Manifest(versions={"windows": 155}))
        names = {c.name: c for c in pipeline.check_synthetic(generated, {}, withheld)}
        check = next(
            c for name, c in names.items() if name.startswith("synthetic/withheld[no manifest")
        )
        self.assertTrue(check.ok)
        self.assertEqual(check.level, "error", "an unreadable vendor must be visible")
        # One check per reason, so a name is never split across two of them. Every
        # product the partial manifest is missing gets its own annotation.
        self.assertEqual(
            sorted(name for name in names if name.startswith("synthetic/withheld[")),
            [
                "synthetic/withheld[no manifest entry for android]",
                "synthetic/withheld[no manifest entry for edge_linux]",
                "synthetic/withheld[no manifest entry for edge_macos]",
                "synthetic/withheld[no manifest entry for edge_windows]",
                "synthetic/withheld[no manifest entry for firefox]",
                "synthetic/withheld[no manifest entry for firefox_esr]",
                "synthetic/withheld[no manifest entry for linux]",
                "synthetic/withheld[no manifest entry for mac]",
            ],
        )
        self.assertEqual([r.synthesized_from for r in generated], ["chrome-windows"])
        self.assertEqual(len(withheld), 13, "every template accounted for")

    def test_a_vendor_outage_withholds_templates_without_failing_the_build(self):
        # ADR-0003 applied to the generator. One vendor's feed being unreadable
        # degrades the Synthetic dataset; it does not block the Observed one, which
        # is the whole point of keeping the two concerns separable.
        generated, withheld = records(manifest=Manifest(versions={"windows": 155}))
        checks = pipeline.check_synthetic(generated, {}, withheld)
        self.assertTrue(all(c.ok for c in checks), [c.detail for c in checks])

    def test_an_empty_synthetic_dataset_is_a_failure_not_an_empty_file(self):
        # The same reason every source being down publishes nothing: a file of zero
        # records reads as "there are no Synthetic user agents", which is a claim.
        check = pipeline.check_synthetic([], {}, [])[0]
        self.assertEqual(check.name, "synthetic/present")
        self.assertFalse(check.ok)
        self.assertEqual(check.level, "error")


class FidelityTests(unittest.TestCase):
    """Two real parsers, one question (ADR-0005)."""

    def setUp(self):
        self.generated, self.withheld = records()

    def parsed(self, parser, user_agents):
        return fidelity.parse(parser, tuple(user_agents))

    def test_both_parsers_identify_every_generated_string(self):
        for parser in fidelity.PARSERS:
            with self.subTest(parser=parser):
                checks = [
                    c
                    for c in pipeline.check_fidelity(self.generated, CURRENT)
                    if c.name == f"synthetic/fidelity/{parser}"
                ]
                self.assertEqual(len(checks), 1)
                self.assertTrue(checks[0].ok, checks[0].detail)
                self.assertIn(
                    f"{len(self.generated)} user agents read as intended", checks[0].detail
                )

    def test_the_two_parsers_are_genuinely_independent(self):
        # uap-core calls macOS "Mac OS X" and ua-parser-js calls it "macOS". If
        # they ever agreed on spelling, the second parser would be adding nothing
        # and the check would be one parser wearing two names.
        strings = tuple(r.user_agent for r in self.generated)
        self.assertNotEqual(
            {p.os_family for p in self.parsed(fidelity.UAP_CORE, strings).values()},
            {p.os_family for p in self.parsed(fidelity.UA_PARSER, strings).values()},
        )

    def test_each_parser_is_asked_and_answered_about_the_same_string(self):
        strings = tuple(r.user_agent for r in self.generated)
        for parser in fidelity.PARSERS:
            with self.subTest(parser=parser):
                parsed = self.parsed(parser, strings)
                self.assertEqual(set(parsed), set(strings))
                for record in self.generated:
                    self.assertEqual(parsed[record.user_agent].browser_major,
                                     int(record.browser.rsplit(" ", 1)[1]))

    def check_for(self, records, parser, manifest=CURRENT):
        """The one Check `parser` returned, however many were asked."""
        matches = [
            c
            for c in pipeline.check_fidelity(records, manifest)
            if c.name == f"synthetic/fidelity/{parser}"
        ]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_a_short_reply_from_a_parser_is_a_parser_failure_not_a_bad_string(self):
        # Node returning fewer results than strings asked about is a broken adapter.
        # Truncating on `zip` would leave the missing strings out of the dict, and
        # the caller would raise a KeyError about a User Agent string — which reads
        # as "this string is bad" rather than "the parser did not do its job".
        strings = tuple(r.user_agent for r in self.generated[:2])
        broken = mock.Mock(return_value=mock.Mock(returncode=0, stdout="[[]]"))
        with mock.patch.object(fidelity.subprocess, "run", broken):
            with self.assertRaises(fidelity.ParserUnavailable) as caught:
                fidelity._ua_parser(strings)
        self.assertIn("1 results for 2", str(caught.exception))

    def test_the_browser_family_is_checked_and_not_just_the_version(self):
        # The family is the thing a wrong token actually corrupts. A string whose
        # `Firefox/156.0` token sits on Chromium scaffolding carries the right
        # version and the wrong browser, and a check comparing versions alone would
        # pass it — verified by deleting the family comparison, which leaves the
        # whole suite green.
        wrong_family = Record(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36 OPR/155.0.0.0"
            ),
            kind=SYNTHETIC,
            os="Windows 10",
            browser="Chrome 155",
            synthesized_from="chrome-windows",
        )
        for parser in fidelity.PARSERS:
            with self.subTest(parser=parser):
                check = self.check_for([wrong_family], parser)
                self.assertFalse(check.ok, f"{parser} passed a Chrome string as Opera")
                self.assertIn("155", check.detail)

    def test_the_os_is_checked_and_not_just_the_browser(self):
        # Same argument one field over. A string that names the right browser on the
        # wrong platform parses as a browser and nothing else, so a version-only
        # check never notices.
        wrong_os = Record(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
            ),
            kind=SYNTHETIC,
            os="Windows 10",
            browser="Chrome 155",
            synthesized_from="chrome-windows",
        )
        for parser in fidelity.PARSERS:
            with self.subTest(parser=parser):
                check = self.check_for([wrong_os], parser)
                self.assertFalse(check.ok, f"{parser} passed a Linux string as Windows")
                self.assertIn("Linux", check.detail)

    def test_the_version_is_checked_too(self):
        # The obvious one, kept explicit so the other two cannot quietly become the
        # whole check.
        stale = Record(
            user_agent=EXPECTED["chrome-windows"].replace("155", "140"),
            kind=SYNTHETIC,
            os="Windows 10",
            browser="Chrome 140",
            synthesized_from="chrome-windows",
        )
        for parser in fidelity.PARSERS:
            with self.subTest(parser=parser):
                self.assertFalse(self.check_for([stale], parser).ok)

    def test_a_mislabelled_record_fails_even_when_the_string_is_correct(self):
        # The same defect one layer down. `os` and `browser` are published fields a
        # consumer filters on, so a label that disagrees with the string it sits on
        # is a confidently wrong answer rather than an obviously broken one. Held
        # apart from the parser assertions because it holds for every parser.
        mislabelled = Record(
            user_agent=EXPECTED["chrome-windows"],
            kind=SYNTHETIC,
            os="Windows 11",  # the string says NT 10.0
            browser="Chrome 155",
            synthesized_from="chrome-windows",
        )
        for parser in fidelity.PARSERS:
            with self.subTest(parser=parser):
                check = self.check_for([mislabelled], parser)
                self.assertFalse(check.ok)
                self.assertIn("os is 'Windows 11'", check.detail)

    def test_the_expected_version_is_read_from_the_manifest_not_the_record(self):
        # A record that lies about its own `browser` label must not be checked
        # against its own lying. The manifest is what the staleness oracle reads,
        # so it is what this reads: the two checks cannot both be satisfied by
        # disagreeing about the version.
        lying = Record(
            user_agent=EXPECTED["chrome-windows"],
            kind=SYNTHETIC,
            browser="Chrome 999",
            synthesized_from="chrome-windows",
        )
        for parser in fidelity.PARSERS:
            with self.subTest(parser=parser):
                check = next(
                    c
                    for c in pipeline.check_fidelity([lying], CURRENT)
                    if c.name == f"synthetic/fidelity/{parser}"
                )
                self.assertFalse(check.ok, "a self-declared version was trusted")
                self.assertIn("Chrome 999", check.detail)

    def test_every_generated_string_is_verified_not_just_sampled(self):
        # `check_fidelity` deduplicates before parsing. Every record must still be
        # judged, or a run where the generator emitted a duplicate twice would
        # verify it once and report it twice.
        doubled = self.generated + self.generated
        for parser in fidelity.PARSERS:
            with self.subTest(parser=parser):
                check = next(
                    c
                    for c in pipeline.check_fidelity(doubled, CURRENT)
                    if c.name == f"synthetic/fidelity/{parser}"
                )
                self.assertTrue(check.ok, check.detail)
                self.assertIn(f"{len(self.generated)} user agents", check.detail)

    def test_a_parser_that_cannot_run_fails_rather_than_skipping(self):
        # The promise is that published strings were verified. A verification that
        # did not happen is not a verification that passed, and the alternative here
        # is a Synthetic dataset nobody ever checked.
        with mock.patch.object(
            fidelity, "parse", side_effect=fidelity.ParserUnavailable("node: not found")
        ):
            checks = pipeline.check_fidelity(self.generated, CURRENT)
        self.assertEqual(len(checks), len(fidelity.PARSERS))
        for check in checks:
            with self.subTest(parser=check.name):
                self.assertFalse(check.ok)
                self.assertEqual(check.level, "error")
                self.assertIn("unavailable", check.detail)

    def test_the_check_names_which_parser_objected(self):
        # One check per parser. A single merged check would leave an operator
        # guessing which regex database disagreed.
        self.assertEqual(
            sorted(c.name for c in pipeline.check_fidelity(self.generated, CURRENT)),
            ["synthetic/fidelity/ua-parser", "synthetic/fidelity/uap-core"],
        )

    def test_nothing_is_generated_that_the_repository_itself_cannot_classify(self):
        # The cheapest fidelity test there is: the same family detection the
        # staleness oracle uses. Catches a token in the wrong order before it ships.
        for record in self.generated:
            template = synthetic.TEMPLATES_BY_NAME[record.synthesized_from]
            with self.subTest(template=template.name):
                self.assertEqual(browsers.detect(record.user_agent), template.family)
                self.assertEqual(
                    browsers.major(record.user_agent, template.family),
                    int(record.browser.rsplit(" ", 1)[1]),
                )


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.generated, self.withheld = records()

    def test_synthetic_files_carry_the_manifest_they_were_built_from(self):
        # The entire provenance of a Synthetic record. There is no source to name
        # and nothing to have been collected, so the manifest is the answer to the
        # only question a reader can ask about it.
        payload = pipeline.build_synthetic_payload(
            "desktop",
            [r for r in self.generated if r.os == "Windows 10"],
            CURRENT,
            "now",
        )
        self.assertEqual(payload["kind"], SYNTHETIC)
        self.assertEqual(payload["schema_version"], pipeline.SCHEMA_VERSION)
        self.assertEqual(payload["generated_from"]["manifest"]["versions"], CURRENT.versions)
        self.assertNotIn("sources", payload)
        self.assertNotIn("freshness", payload)

    def test_every_published_record_declares_its_kind(self):
        payload = pipeline.build_synthetic_payload("desktop", self.generated, CURRENT, "now")
        for row in payload["user_agents"]:
            self.assertEqual(row["kind"], SYNTHETIC)
        for row in payload["user_agents"]:
            self.assertIsNone(row["count"])
            self.assertIsNone(row["count_source"])

    def test_an_observed_record_declares_its_kind_in_the_canonical_payload(self):
        # The other direction, and the one the migration actually breaks: a
        # consumer that switches on `kind` and finds it absent in an old file
        # should see a version it can check, not a `null` that reads as Observed.
        payload = pipeline.build_payload("desktop", [], [], CURRENT, "now")
        self.assertEqual(payload["kind"], OBSERVED)
        self.assertEqual(payload["schema_version"], pipeline.SCHEMA_VERSION)

    def test_the_synthetic_directory_is_never_where_observed_data_lives(self):
        # A consumer that globs one directory for data must not be able to pick up
        # a fabricated string by accident, and a consumer who reads only the path
        # must be able to tell what they are holding.
        self.assertEqual(pipeline.SYNTHETIC_DIR, "synthetic")
        for directory in (pipeline.DATA_DIR, pipeline.LEGACY_DIR):
            self.assertNotEqual(pipeline.SYNTHETIC_DIR, directory)

    def test_records_are_grouped_into_the_file_their_template_names(self):
        # Not by anything the record says, so a string cannot land in a file that
        # disagrees with the one its generation was written for.
        grouped = synthetic.by_category(self.generated)
        self.assertEqual(sorted(grouped), ["desktop", "mobile", "tablet"])
        self.assertEqual(len(grouped["mobile"]), 1)
        self.assertEqual(grouped["mobile"][0].synthesized_from, "chrome-android")
        self.assertEqual(len(grouped["tablet"]), 1)
        self.assertEqual(grouped["tablet"][0].synthesized_from, "chrome-android-tablet")


class PublishedCorpusTests(unittest.TestCase):
    """The files on disk, not the generator that wrote them.

    Everything above tests the generator against its own expectations. This reads
    what is actually published, which is what a consumer downloads, and is the only
    test that would notice the two datasets having drifted into sharing a string.
    """

    @staticmethod
    def published(directory):
        found = {}
        if not os.path.isdir(directory):
            return found
        for name in sorted(os.listdir(directory)):
            if name.endswith(".json"):
                with open(os.path.join(directory, name), encoding="utf-8") as handle:
                    payload = json.load(handle)
                found[name] = payload
        return found

    def setUp(self):
        self.observed = self.published(pipeline.DATA_DIR)
        self.synthetic = self.published(pipeline.SYNTHETIC_DIR)

    def strings(self, files):
        return {row["user_agent"] for payload in files.values() for row in payload["user_agents"]}

    def test_the_two_datasets_are_published_separately(self):
        # Per-category filenames deliberately repeat across the two directories:
        # both datasets are cut by Device Category, and `synthetic/desktop.json`
        # reads as clearly as `data/desktop.json` does. What must differ is the
        # directory and the `kind` every file declares, so a consumer following
        # either path learns which dataset it is holding.
        if not self.observed:
            self.skipTest("no published dataset in this checkout")
        self.assertTrue(self.synthetic, "no Synthetic dataset is published")
        self.assertNotEqual(pipeline.SYNTHETIC_DIR, pipeline.DATA_DIR)
        self.assertNotEqual(pipeline.SYNTHETIC_DIR, pipeline.LEGACY_DIR)
        for name, payload in self.synthetic.items():
            with self.subTest(file=name):
                self.assertEqual(payload["kind"], SYNTHETIC)
        for name, payload in self.observed.items():
            with self.subTest(file=name):
                self.assertEqual(payload["kind"], OBSERVED)


    def test_no_published_string_is_in_both_datasets(self):
        # The acceptance criterion, checked against what is actually on disk rather
        # than against what the generator would produce today. Only this test would
        # notice a hand-edited file, a bad merge, or two runs disagreeing.
        if not self.observed or not self.synthetic:
            self.skipTest("no published datasets in this checkout")
        both = self.strings(self.observed) & self.strings(self.synthetic)
        self.assertEqual(both, set(), f"published in both datasets: {sorted(both)}")

    def test_no_published_synthetic_string_carries_a_frequency(self):
        # A count on a Synthetic record is a claim about traffic that does not
        # exist, and it is the claim a consumer is most likely to act on.
        if not self.synthetic:
            self.skipTest("no Synthetic dataset in this checkout")
        for name, payload in self.synthetic.items():
            for row in payload["user_agents"]:
                with self.subTest(file=name):
                    self.assertIsNone(row["count"])
                    self.assertIsNone(row["percentage"])
                    self.assertIsNone(row["count_source"])
                    self.assertEqual(row["sources"], [])

    def test_every_published_record_declares_the_kind_of_its_file(self):
        # A file that says `kind: synthetic` and a record inside it that says
        # `observed` is a file whose contents disagree with its own name. Both
        # directories are walked separately: merging them by filename would let
        # `data/bot.json` and `synthetic/bot.json` collide on the key and check only
        # whichever sorted last.
        for directory, expected in (
            (pipeline.DATA_DIR, OBSERVED),
            (pipeline.LEGACY_DIR, OBSERVED),
            (pipeline.SYNTHETIC_DIR, SYNTHETIC),
        ):
            for name, payload in self.published(directory).items():
                with self.subTest(file=f"{directory}/{name}"):
                    if directory == pipeline.LEGACY_DIR:
                        # The legacy projection is a bare list of strings, by design:
                        # its keys have not changed since v1 and a consumer reads it
                        # with `jq .user_agents[0]`. It holds only strings the
                        # ordering source measured, which is to say only Observed
                        # ones — asserted rather than assumed, below.
                        self.assertIsInstance(payload["user_agents"], list)
                        continue
                    self.assertEqual(payload["kind"], expected)
                    for row in payload["user_agents"]:
                        self.assertEqual(row["kind"], expected)

    def test_the_legacy_projection_holds_only_observed_strings(self):
        # `common/` is the one file with no `kind` on its records, so the claim that
        # it is Observed-only is enforced here instead of being left to the shape of
        # the file. Nothing that is Synthetic can appear: a Synthetic record carries
        # no count, and this file publishes only measured strings.
        synthetic_strings = self.strings(self.synthetic)
        for name, payload in self.published(pipeline.LEGACY_DIR).items():
            with self.subTest(file=name):
                for user_agent in payload["user_agents"]:
                    self.assertNotIn(user_agent, synthetic_strings)

    def test_published_synthetic_strings_survive_both_parsers(self):
        # The acceptance criteria, against the committed files rather than a fresh
        # generation. Everything else in this class tests the generator against its
        # own expectations; only this reads what a consumer downloads, so it is the
        # only one that would notice a hand-edited file, a bad merge, or a build
        # that published strings no parser could place.
        if not self.synthetic:
            self.skipTest("no Synthetic dataset in this checkout")
        strings = tuple(
            row["user_agent"]
            for payload in self.synthetic.values()
            for row in payload["user_agents"]
        )
        for parser in fidelity.PARSERS:
            with self.subTest(parser=parser):
                parsed = fidelity.parse(parser, strings)
                self.assertEqual(set(parsed), set(strings))
                for payload in self.synthetic.values():
                    for row in payload["user_agents"]:
                        got = parsed[row["user_agent"]]
                        self.assertIsNotNone(got.browser_family, row["user_agent"])
                        self.assertEqual(
                            str(got.browser_major), row["browser"].rsplit(" ", 1)[1]
                        )


if __name__ == "__main__":
    unittest.main()
