#!/usr/bin/env python3
"""Tests for display/replaces.py — app-replacement display and savings math."""

import io
import sys
import os
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from display.replaces import (
    _APPS,
    CLEAN_SHOT_PRICE_MO,
    total_app_cost_mo,
    monthly_savings,
    annual_savings,
    display_replaces,
    get_tts_summary,
)


class TestAppCatalog(unittest.TestCase):
    def test_at_least_ten_apps(self):
        self.assertGreaterEqual(len(_APPS), 10)

    def test_all_tuples_are_three_elements(self):
        for entry in _APPS:
            self.assertEqual(len(entry), 3, entry)

    def test_all_prices_positive(self):
        for _, name, price in _APPS:
            self.assertGreater(price, 0, f"{name} price must be > 0")

    def test_all_categories_nonempty(self):
        for cat, _, _ in _APPS:
            self.assertTrue(cat.strip(), "Category must not be blank")

    def test_all_names_nonempty(self):
        for _, name, _ in _APPS:
            self.assertTrue(name.strip(), "App name must not be blank")

    def test_no_duplicate_names(self):
        names = [name for _, name, _ in _APPS]
        self.assertEqual(len(names), len(set(names)), "Duplicate app names found")

    def test_clean_shot_price_positive(self):
        self.assertGreater(CLEAN_SHOT_PRICE_MO, 0)


class TestSavingsMath(unittest.TestCase):
    def test_total_mo_equals_sum(self):
        expected = sum(p for _, _, p in _APPS)
        self.assertAlmostEqual(total_app_cost_mo(), expected, places=2)

    def test_monthly_savings_positive(self):
        self.assertGreater(monthly_savings(), 0)

    def test_apps_cost_more_than_clean_shot(self):
        self.assertGreater(total_app_cost_mo(), CLEAN_SHOT_PRICE_MO)

    def test_annual_savings_is_12x_monthly(self):
        self.assertAlmostEqual(annual_savings(), monthly_savings() * 12, places=2)

    def test_annual_savings_over_thousand(self):
        self.assertGreater(annual_savings(), 1000)

    def test_5yr_savings_over_five_thousand(self):
        self.assertGreater(annual_savings() * 5, 5000)


class TestFullDisplay(unittest.TestCase):
    def _run(self, short=False):
        with patch("sys.stdout", new_callable=io.StringIO) as mock:
            display_replaces({}, short=short)
        return mock.getvalue()

    def test_full_runs_without_error(self):
        out = self._run(short=False)
        self.assertTrue(len(out) > 0)

    def test_full_contains_section_headers(self):
        out = self._run(short=False)
        self.assertIn("APPS THIS REPLACES", out)
        self.assertIn("THE MATH", out)
        self.assertIn("DATA USAGE", out)
        self.assertIn("TIME SAVED", out)
        self.assertIn("WORKS EVERYWHERE", out)

    def test_full_contains_savings_numbers(self):
        out = self._run(short=False)
        self.assertIn("YOUR SAVINGS", out)
        self.assertIn("Monthly", out)
        self.assertIn("Annual", out)
        self.assertIn("5 Years", out)

    def test_full_contains_cleanshothq(self):
        out = self._run(short=False)
        self.assertIn("cleanshothq.com", out)

    def test_full_lists_all_apps(self):
        out = self._run(short=False)
        for _, name, _ in _APPS:
            self.assertIn(name, out, f"App '{name}' missing from full display")

    def test_full_shows_app_prices(self):
        out = self._run(short=False)
        self.assertIn("$", out)
        self.assertIn("/mo", out)

    def test_full_shows_data_comparison(self):
        out = self._run(short=False)
        self.assertIn("2G", out)
        self.assertIn("50KB", out)

    def test_full_shows_connectivity(self):
        out = self._run(short=False)
        self.assertIn("Rural highways", out)
        self.assertIn("Dead zones", out)


class TestShortDisplay(unittest.TestCase):
    def _run(self):
        with patch("sys.stdout", new_callable=io.StringIO) as mock:
            display_replaces({}, short=True)
        return mock.getvalue()

    def test_short_runs_without_error(self):
        out = self._run()
        self.assertTrue(len(out) > 0)

    def test_short_contains_headline(self):
        out = self._run()
        self.assertIn("CLEAN SHOT SAVES YOU", out)

    def test_short_contains_cta(self):
        out = self._run()
        self.assertIn("cleanshothq.com", out)

    def test_short_mentions_2g(self):
        out = self._run()
        self.assertIn("2G", out)

    def test_short_fits_within_15_nonempty_lines(self):
        out = self._run()
        nonempty = [l for l in out.split("\n") if l.strip()]
        self.assertLessEqual(len(nonempty), 15)

    def test_short_shows_app_count(self):
        out = self._run()
        self.assertIn(str(len(_APPS)), out)

    def test_short_shows_savings(self):
        out = self._run()
        self.assertIn("yr saved", out)


class TestTtsSummary(unittest.TestCase):
    def test_nonempty(self):
        s = get_tts_summary()
        self.assertGreater(len(s), 30)

    def test_under_300_chars(self):
        s = get_tts_summary()
        self.assertLessEqual(len(s), 300)

    def test_mentions_app_count(self):
        s = get_tts_summary()
        self.assertIn(str(len(_APPS)), s)

    def test_mentions_savings(self):
        s = get_tts_summary()
        self.assertIn("dollars a year", s)

    def test_mentions_cleanshothq(self):
        s = get_tts_summary()
        self.assertIn("cleanshothq.com", s)

    def test_mentions_2g(self):
        s = get_tts_summary()
        self.assertIn("2G", s)

    def test_mentions_free_trial(self):
        s = get_tts_summary()
        self.assertIn("30 days", s)


if __name__ == "__main__":
    unittest.main()
