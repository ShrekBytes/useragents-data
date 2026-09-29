"""Browser family detection and version extraction."""

import unittest

from uadata import browsers

CHROME_WIN = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
)
EDGE_WIN = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36 Edg/154.0.4258.37"
)
OPERA_WIN = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 OPR/136.0.6008.52"
)
SAMSUNG_ANDROID = (
    "Mozilla/5.0 (Linux; Android 13; SM-S901B) AppleWebKit/537.36 "
    "(KHTML, like Gecko) SamsungBrowser/30.0 Chrome/143.0.0.0 Mobile Safari/537.36"
)
FIREFOX_LINUX = "Mozilla/5.0 (X11; Linux x86_64; rv:156.0) Gecko/20100101 Firefox/156.0"
SAFARI_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/27.0 Safari/605.1.15"
)
BOT = "python-requests/2.34.2"


class DetectTests(unittest.TestCase):
    def test_families(self):
        for ua, expected in [
            (CHROME_WIN, "chrome"),
            (EDGE_WIN, "edge"),
            (OPERA_WIN, "opera"),
            (SAMSUNG_ANDROID, "samsung"),
            (FIREFOX_LINUX, "firefox"),
            (SAFARI_MAC, "safari"),
        ]:
            with self.subTest(ua=ua[:40]):
                self.assertEqual(browsers.detect(ua), expected)

    def test_chromium_forks_are_not_read_as_chrome(self):
        # The ordering in FAMILIES exists for this. Reading Edge as Chrome would
        # let a dataset full of stale Edge strings look current.
        self.assertEqual(browsers.major(EDGE_WIN, "edge"), 154)
        self.assertIsNone(browsers.major(EDGE_WIN, "chrome"))
        self.assertIsNone(browsers.major(OPERA_WIN, "chrome"))
        self.assertIsNone(browsers.major(SAMSUNG_ANDROID, "chrome"))

    def test_unknown_is_none(self):
        self.assertIsNone(browsers.detect(BOT))
        self.assertIsNone(browsers.major(BOT, "chrome"))


class MaxMajorTests(unittest.TestCase):
    def test_takes_newest(self):
        uas = [CHROME_WIN, FIREFOX_LINUX, EDGE_WIN]
        self.assertEqual(browsers.max_major(uas, "chrome"), 155)
        self.assertEqual(browsers.max_major(uas, "edge"), 154)
        self.assertEqual(browsers.max_major(uas, "firefox"), 156)

    def test_absent_family_is_none(self):
        self.assertIsNone(browsers.max_major([BOT], "chrome"))

    def test_edge_only_dataset_does_not_look_current(self):
        # Guards the original failure mode: max() over the wrong family.
        self.assertIsNone(browsers.max_major([EDGE_WIN, OPERA_WIN], "chrome"))

    def test_majors_reports_every_family(self):
        found = browsers.majors([EDGE_WIN, FIREFOX_LINUX])
        self.assertEqual(set(found), set(browsers.FAMILY_NAMES))
        self.assertEqual(found["edge"], 154)
        self.assertEqual(found["firefox"], 156)
        self.assertIsNone(found["safari"])

    def test_majors_accepts_a_generator_once(self):
        # Would silently yield all-None if the iterable were consumed per family.
        self.assertEqual(browsers.majors(u for u in [EDGE_WIN])["edge"], 154)


if __name__ == "__main__":
    unittest.main()
