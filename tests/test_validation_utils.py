# WARNING: These tests target the DEPRECATED codebase (_deprecated_src_do_not_use/). See option_b/tests/ for active tests.
"""Unit tests for validation_utils.py — all 8 helper functions."""

import pandas as pd
import pytest

from _deprecated_src_do_not_use.validation_utils import (
    is_not_blank,
    is_exact_length,
    is_max_length,
    is_in_allowed_values,
    is_valid_date,
    is_numeric,
    is_date_greater_than,
    is_date_lte,
)


class TestIsNotBlank:
    def test_valid_non_blank(self):
        s = pd.Series(["AB", "hello", "X"])
        result = is_not_blank(s)
        assert result.all()

    def test_blank_values(self):
        s = pd.Series(["", "   ", None])
        result = is_not_blank(s)
        assert not result.any()

    def test_mixed(self):
        s = pd.Series(["AB", "", "X", None, "  "])
        result = is_not_blank(s)
        assert list(result) == [True, False, True, False, False]


class TestIsExactLength:
    def test_exact_match(self):
        s = pd.Series(["AB", "CD", "EF"])
        assert is_exact_length(s, 2).all()

    def test_too_short(self):
        s = pd.Series(["A"])
        assert not is_exact_length(s, 2).iloc[0]

    def test_too_long(self):
        s = pd.Series(["ABC"])
        assert not is_exact_length(s, 2).iloc[0]

    def test_with_whitespace_trimmed(self):
        s = pd.Series(["AB ", " AB"])
        assert is_exact_length(s, 2).all()


class TestIsMaxLength:
    def test_within_limit(self):
        s = pd.Series(["AB", "A", ""])
        assert is_max_length(s, 15).all()

    def test_exceeds_limit(self):
        s = pd.Series(["ABCDEFGHIJKLMNOP"])  # 16 chars
        assert not is_max_length(s, 15).iloc[0]

    def test_at_boundary(self):
        s = pd.Series(["ABCDEFGHIJKLMNO"])  # 15 chars
        assert is_max_length(s, 15).iloc[0]


class TestIsInAllowedValues:
    def test_valid_values(self):
        s = pd.Series(["A", "W", "B"])
        assert is_in_allowed_values(s, ["A", "W", "B", "T"]).all()

    def test_invalid_value(self):
        s = pd.Series(["X"])
        assert not is_in_allowed_values(s, ["A", "W", "B"]).iloc[0]

    def test_empty_list(self):
        s = pd.Series(["A"])
        assert not is_in_allowed_values(s, []).iloc[0]

    def test_whitespace_stripped(self):
        s = pd.Series([" A "])
        assert is_in_allowed_values(s, ["A"]).iloc[0]


class TestIsValidDate:
    def test_valid_dates(self):
        s = pd.Series(["20260101", "19991231", "20240229"])
        assert is_valid_date(s).all()

    def test_invalid_month(self):
        s = pd.Series(["20261301"])
        assert not is_valid_date(s).iloc[0]

    def test_invalid_day(self):
        s = pd.Series(["20260231"])  # Feb 31
        assert not is_valid_date(s).iloc[0]

    def test_non_numeric_string(self):
        s = pd.Series(["ABCDEFGH"])
        assert not is_valid_date(s).iloc[0]

    def test_wrong_format(self):
        s = pd.Series(["01/01/2026", "2026-01-01"])
        assert not is_valid_date(s).any()

    def test_all_zeros(self):
        s = pd.Series(["00000000"])
        assert not is_valid_date(s).iloc[0]


class TestIsNumeric:
    def test_integers(self):
        s = pd.Series(["42", "0", "100"])
        assert is_numeric(s).all()

    def test_floats(self):
        s = pd.Series(["3.14", "0.5"])
        assert is_numeric(s).all()

    def test_non_numeric(self):
        s = pd.Series(["abc", "12x", ""])
        result = is_numeric(s)
        assert not result.iloc[0]
        assert not result.iloc[1]


class TestIsDateGreaterThan:
    def test_a_after_b(self):
        a = pd.Series(["20260201"])
        b = pd.Series(["20260101"])
        assert is_date_greater_than(a, b).iloc[0]

    def test_a_before_b(self):
        a = pd.Series(["20260101"])
        b = pd.Series(["20260201"])
        assert not is_date_greater_than(a, b).iloc[0]

    def test_equal_dates(self):
        a = pd.Series(["20260101"])
        b = pd.Series(["20260101"])
        assert not is_date_greater_than(a, b).iloc[0]

    def test_invalid_date_returns_false(self):
        a = pd.Series(["INVALID1"])
        b = pd.Series(["20260101"])
        assert not is_date_greater_than(a, b).iloc[0]


class TestIsDateLte:
    def test_a_before_b(self):
        a = pd.Series(["20260101"])
        b = pd.Series(["20260201"])
        assert is_date_lte(a, b).iloc[0]

    def test_equal_dates(self):
        a = pd.Series(["20260101"])
        b = pd.Series(["20260101"])
        assert is_date_lte(a, b).iloc[0]

    def test_a_after_b(self):
        a = pd.Series(["20260301"])
        b = pd.Series(["20260101"])
        assert not is_date_lte(a, b).iloc[0]

    def test_invalid_date_returns_false(self):
        a = pd.Series(["20260101"])
        b = pd.Series(["BADDATE!"])
        assert not is_date_lte(a, b).iloc[0]
