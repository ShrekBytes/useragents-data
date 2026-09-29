"""The version manifest, driven by canned vendor payloads rather than the network.

Every entry in the manifest is a third party who can change their URL, change
their shape, or disappear without telling us. These fixtures pin how we read each
one — which channel, which field, which title is a beta — so that a change to that
reading is a failing test rather than a check that quietly stopped asserting
anything.

What they do not do is predict the vendors. A payload shaped in a way we never
imagined still gets through here, and is caught at runtime as a named error in
`manifest.errors` and a freshness check that skips.
"""

import unittest

from tests import FakeSession, Response
from uadata import manifest


def chromiumdash(major=155):
    return [{"channel": "Stable", "platform": "Windows", "version": f"{major}.0.0.0"}]


def firefox(latest=156, esr=140):
    return {"LATEST_FIREFOX_VERSION": f"{latest}.0", "FIREFOX_ESR": f"{esr}.0"}


def edge(*releases, product="Stable"):
    """`edge(("Windows", "154.0.4258.37"), ("MacOS", "154.0.4258.37"))`.

    One entry per release, because the real payload lists every platform and
    architecture a build shipped to rather than one version per platform.
    """
    return [
        {
            "Product": product,
            "Releases": [
                {
                    "ReleaseId": index + 1,
                    "Platform": platform,
                    "Architecture": "x64",
                    "ProductVersion": version,
                    "PublishedTime": "2026-09-24T19:36:00",
                }
                for index, (platform, version) in enumerate(releases)
            ],
        }
    ]


def safari(*sections):
    """The documentation index Apple serves, one section per Safari major.

    `safari((27, "27 Release Notes", "27.2 Beta Release Notes"), (26, "26.6 Release
    Notes"))` — the beta is the whole difficulty, and is why this takes a fixture.
    A note of `None` is an identifier the index names but no longer resolves,
    which is what a renamed or withdrawn article looks like.
    """
    topic_sections = []
    references = {}
    for major, *titles in sections:
        identifiers = []
        for index, title in enumerate(titles):
            identifier = f"doc://com.apple.Safari-Release-Notes/safari-{major}-{index}"
            identifiers.append(identifier)
            if title is not None:
                references[identifier] = {"title": f"Safari {title}"}
        topic_sections.append(
            {
                "title": f"Version {major}",
                "identifiers": identifiers,
                "anchor": f"Version-{major}",
            }
        )
    return {"topicSections": topic_sections, "references": references}


def routes(**overrides):
    """Every vendor's URL -> payload, overridable one at a time.

    ChromiumDash is keyed per platform, because that is the URL it is actually
    asked for.
    """
    return {
        **{
            manifest.CHROMIUMDASH.format(platform=p): Response(chromiumdash())
            for p in manifest.PLATFORMS
        },
        manifest.FIREFOX_VERSIONS: Response(firefox()),
        manifest.EDGE_PRODUCTS: Response(
            edge(
                ("Windows", "154.0.4258.37"),
                ("MacOS", "154.0.4258.37"),
                ("Linux", "154.0.4258.37"),
            )
        ),
        manifest.SAFARI_RELEASE_NOTES: Response(
            safari((27, "27 Release Notes", "27.2 Beta Release Notes"))
        ),
        **overrides,
    }


class EdgeTests(unittest.TestCase):
    def fetch(self, payload):
        return manifest.fetch_manifest(
            FakeSession(routes(**{manifest.EDGE_PRODUCTS: Response(payload)}))
        )

    def test_it_reads_the_stable_channel_for_every_desktop_platform(self):
        # The `Edg/` token carries the whole product version, so the manifest
        # entry is the same number the dataset holds: 154.0.4258.37 on the stable
        # channel, major 154 for what we compare.
        versions = self.fetch(edge(("Windows", "154.0.4258.37"))).versions
        self.assertEqual(versions["edge_windows"], 154)

    def test_it_ignores_the_channels_that_are_not_shipping(self):
        # Beta, Dev and Canary all publish higher majors within days of the stable
        # release. Reading any of them would leave the build permanently red.
        payload = [
            {"Product": name, "Releases": [{"Platform": "Windows", "ProductVersion": v}]}
            for name, v in [
                ("Beta", "156.0.0.0"),
                ("Dev", "157.0.0.0"),
                ("Canary", "158.0.0.0"),
                ("EdgeUpdate", "1.3.271.7"),
            ]
        ] + edge(("Windows", "154.0.4258.37"))
        self.assertEqual(self.fetch(payload).versions["edge_windows"], 154)

    def test_it_takes_the_newest_release_per_platform(self):
        # One platform ships several builds, one per architecture, and the list is
        # not ordered. Taking whichever came first would read a 153 x86 build as
        # current on a run where the 154 x64 build had already shipped.
        versions = self.fetch(
            edge(
                ("Windows", "153.0.3626.0"),
                ("Windows", "154.0.4258.37"),
                ("MacOS", "152.0.1.0"),
            )
        ).versions
        self.assertEqual((versions["edge_windows"], versions["edge_macos"]), (154, 152))

    def test_it_claims_no_version_for_platforms_that_are_not_in_the_dataset(self):
        # Edge on iOS and Android is `EdgiOS/` and `EdgA/`, which are not the
        # `edge` family. An entry for them would assert freshness about strings
        # this repository does not hold.
        versions = self.fetch(
            edge(("Windows", "154.0.4258.37"), ("iOS", "155.0.0.0"), ("Android", "155.0.0.0"))
        ).versions
        self.assertEqual(sorted(k for k in versions if k.startswith("edge")), ["edge_windows"])

    def test_a_missing_stable_channel_is_an_error_not_an_empty_manifest(self):
        # An empty answer is indistinguishable from "the manifest is fine and the
        # dataset is stale", which is the exact confusion this check exists to
        # prevent. It has to be a named failure instead.
        result = self.fetch([{"Product": "Beta", "Releases": []}])
        self.assertNotIn("edge_windows", result.versions)
        self.assertTrue(any(e.startswith("edge:") for e in result.errors), result.errors)


class SafariTests(unittest.TestCase):
    def fetch(self, payload):
        return manifest.fetch_manifest(
            FakeSession(routes(**{manifest.SAFARI_RELEASE_NOTES: Response(payload)}))
        )

    def test_it_is_the_newest_major_that_has_shipped(self):
        versions = self.fetch(
            safari((27, "27 Release Notes", "27.2 Beta Release Notes"), (26, "26.6 Release Notes"))
        ).versions
        self.assertEqual(versions["safari"], 27)

    def test_a_beta_is_not_a_shipped_version(self):
        # Apple publishes the beta's release notes in the same index as the
        # shipping ones, so the obvious reading — "the newest version in the
        # index" — is 28 on the day the 28 beta appears, and would then fail every
        # run for the months before 28 actually ships.
        versions = self.fetch(
            safari((28, "28 Beta Release Notes"), (27, "27 Release Notes", "27.2 Beta Release Notes"))
        ).versions
        self.assertEqual(versions["safari"], 27)

    def test_a_section_whose_notes_we_cannot_read_is_not_shipping(self):
        # The conservative direction: if we cannot tell a beta from a release, we
        # do not claim the version. A skipped check is visible, a wrong one is not.
        versions = self.fetch(safari((28, None), (27, "27 Release Notes"))).versions
        self.assertEqual(versions["safari"], 27)

    def test_an_index_with_no_shipping_release_is_an_error(self):
        result = self.fetch(safari((28, "28 Beta Release Notes")))
        self.assertNotIn("safari", result.versions)
        self.assertTrue(any(e.startswith("safari:") for e in result.errors), result.errors)

    def test_an_index_it_cannot_read_is_an_error(self):
        result = self.fetch({})
        self.assertNotIn("safari", result.versions)
        self.assertTrue(any(e.startswith("safari:") for e in result.errors), result.errors)


class ManifestTests(unittest.TestCase):
    def test_every_vendor_contributes(self):
        result = manifest.fetch_manifest(FakeSession(routes()))
        self.assertEqual(result.errors, [])
        self.assertEqual(
            result.versions,
            {
                "windows": 155,
                "mac": 155,
                "linux": 155,
                "android": 155,
                "firefox": 156,
                "firefox_esr": 140,
                "edge_windows": 154,
                "edge_macos": 154,
                "edge_linux": 154,
                "safari": 27,
            },
        )

    def test_a_vendor_that_changes_shape_is_recorded_and_the_rest_survive(self):
        # A vendor we can no longer read must not cost us the vendors we can, and
        # must not be dropped quietly: that product's freshness check is skipped
        # and says so, which is a different statement from "fresh".
        result = manifest.fetch_manifest(
            FakeSession(
                routes(
                    **{
                        manifest.EDGE_PRODUCTS: Response([{"Product": "Beta", "Releases": []}]),
                        manifest.SAFARI_RELEASE_NOTES: Response({}),
                    }
                )
            )
        )
        self.assertEqual(
            sorted(result.versions),
            ["android", "firefox", "firefox_esr", "linux", "mac", "windows"],
        )
        self.assertEqual(sorted(e.split(":")[0] for e in result.errors), ["edge", "safari"])

    def test_one_chromiumdash_platform_failing_does_not_cost_the_others(self):
        # Chrome is the one vendor we ask per platform, so its failures are per
        # platform. A dead Mac channel must not cost us the Windows version, which
        # is the one that decides what the dataset has to be holding.
        result = manifest.fetch_manifest(
            FakeSession(routes(**{manifest.CHROMIUMDASH.format(platform="Mac"): Response([])}))
        )
        self.assertNotIn("mac", result.versions)
        self.assertEqual(result.versions["windows"], 155)
        self.assertEqual([e.split(":")[0] for e in result.errors], ["chrome/Mac"])

    def test_chrome_is_asked_once_per_platform_and_every_other_vendor_once(self):
        # ChromiumDash publishes one channel per platform, so it takes four
        # requests. Anything more would be a retry nobody asked for. Order is not
        # part of the contract, so it is not asserted.
        session = FakeSession(routes())
        manifest.fetch_manifest(session)
        self.assertEqual(
            sorted(session.requested),
            sorted(
                [manifest.CHROMIUMDASH.format(platform=p) for p in manifest.PLATFORMS]
                + [
                    manifest.FIREFOX_VERSIONS,
                    manifest.EDGE_PRODUCTS,
                    manifest.SAFARI_RELEASE_NOTES,
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()
