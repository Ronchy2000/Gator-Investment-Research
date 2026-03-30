import unittest
from unittest.mock import patch

from scripts import pre_crawl_check


class BuildCoarseProbePlanTests(unittest.TestCase):
    def test_initial_dense_window_covers_first_gap(self):
        dense_end = 851 + pre_crawl_check.INITIAL_DENSE_PROBE_WINDOW - 1
        self.assertEqual(dense_end, 900)


class CoarseProbeBoundaryTests(unittest.TestCase):
    def test_coarse_probe_finds_article_after_missing_start_id(self):
        checked_ids = []

        def fake_check(article_id: int, _driver) -> bool:
            checked_ids.append(article_id)
            return article_id == 852

        with patch.object(pre_crawl_check, "check_article_exists", side_effect=fake_check):
            with patch.object(pre_crawl_check.time, "sleep", return_value=None):
                boundary = pre_crawl_check.coarse_probe_boundary(
                    driver=object(),
                    start_id=851,
                    max_id=1000,
                    step=50,
                    original_boundary=850,
                )

        self.assertEqual(boundary, 852)
        self.assertEqual(checked_ids[:3], [851, 852, 853])
        self.assertIn(901, checked_ids)

    def test_dense_startup_scan_does_not_stop_after_five_initial_misses(self):
        checked_ids = []

        def fake_check(article_id: int, _driver) -> bool:
            checked_ids.append(article_id)
            return article_id == 856

        with patch.object(pre_crawl_check, "check_article_exists", side_effect=fake_check):
            with patch.object(pre_crawl_check.time, "sleep", return_value=None):
                boundary = pre_crawl_check.coarse_probe_boundary(
                    driver=object(),
                    start_id=851,
                    max_id=1000,
                    step=50,
                    original_boundary=850,
                )

        self.assertEqual(boundary, 856)
        self.assertEqual(checked_ids[:6], [851, 852, 853, 854, 855, 856])


if __name__ == "__main__":
    unittest.main()
