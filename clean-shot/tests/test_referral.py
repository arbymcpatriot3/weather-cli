#!/usr/bin/env python3
# tests/test_referral.py — Clean Shot: referral engine tests

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.referral import get_tier, calc_discount_pct, is_free_tier, is_ambassador


def test_tiers():
    assert get_tier(0)  == "Road Scout"
    assert get_tier(1)  == "Road Scout"
    assert get_tier(2)  == "Captain"
    assert get_tier(5)  == "Commander"
    assert get_tier(10) == "Legend"
    assert get_tier(15) == "Elite"
    assert get_tier(25) == "Ambassador"
    assert get_tier(99) == "Ambassador"
    print("✓ get_tier")


def test_discount():
    assert calc_discount_pct(0)  == 0.0
    assert calc_discount_pct(3)  == 30.0
    assert calc_discount_pct(10) == 100.0
    assert calc_discount_pct(15) == 100.0   # capped at 100%
    print("✓ calc_discount_pct")


def test_free_tier():
    assert not is_free_tier(9)
    assert is_free_tier(10)
    assert is_free_tier(20)
    print("✓ is_free_tier")


def test_ambassador():
    assert not is_ambassador(10)
    assert is_ambassador(11)
    assert is_ambassador(50)
    print("✓ is_ambassador")


if __name__ == "__main__":
    test_tiers()
    test_discount()
    test_free_tier()
    test_ambassador()
    print("All referral tests passed.")
