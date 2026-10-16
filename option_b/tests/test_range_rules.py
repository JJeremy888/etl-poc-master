"""Tests for range_rules module.

**Validates: Requirements 3** — Range Rule Correctness Property.
"""

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from datetime import date

from option_b.engine.range_rules import compile_date_greater_than, compile_date_lte


class TestDateGreaterThan:
    """Unit tests for date_greater_than rule."""

    def test_target_after_compare_passes(self, spark):
        rule = {"target_field": "END_DATE", "compare_field": "START_DATE", "severity": "SEVERE"}
        df = spark.createDataFrame([("20250101", "20200101")], ["END_DATE", "START_DATE"])
        result = df.withColumn("VAL", compile_date_greater_than(rule))
        assert result.collect()[0]["VAL"] is None

    def test_target_before_compare_fails(self, spark):
        rule = {"target_field": "END_DATE", "compare_field": "START_DATE", "severity": "SEVERE"}
        df = spark.createDataFrame([("20190101", "20200101")], ["END_DATE", "START_DATE"])
        result = df.withColumn("VAL", compile_date_greater_than(rule))
        val = result.collect()[0]["VAL"]
        assert val is not None
        assert "SEVERE:" in val

    def test_equal_dates_fails(self, spark):
        rule = {"target_field": "END_DATE", "compare_field": "START_DATE", "severity": "SEVERE"}
        df = spark.createDataFrame([("20200101", "20200101")], ["END_DATE", "START_DATE"])
        result = df.withColumn("VAL", compile_date_greater_than(rule))
        assert result.collect()[0]["VAL"] is not None

    def test_blank_target_passes(self, spark):
        """Blank target skips check (other rules handle blank)."""
        rule = {"target_field": "END_DATE", "compare_field": "START_DATE", "severity": "SEVERE"}
        df = spark.createDataFrame([("", "20200101")], ["END_DATE", "START_DATE"])
        result = df.withColumn("VAL", compile_date_greater_than(rule))
        assert result.collect()[0]["VAL"] is None

    def test_invalid_date_skips(self, spark):
        """Invalid date format skips check."""
        rule = {"target_field": "END_DATE", "compare_field": "START_DATE", "severity": "SEVERE"}
        df = spark.createDataFrame([("BADDATE1", "20200101")], ["END_DATE", "START_DATE"])
        result = df.withColumn("VAL", compile_date_greater_than(rule))
        assert result.collect()[0]["VAL"] is None


class TestDateLte:
    """Unit tests for date_lte rule."""

    def test_target_before_compare_passes(self, spark):
        rule = {"target_field": "APP_DATE", "compare_field": "ISSUE_DATE", "severity": "SEVERE"}
        df = spark.createDataFrame([("20190101", "20200101")], ["APP_DATE", "ISSUE_DATE"])
        result = df.withColumn("VAL", compile_date_lte(rule))
        assert result.collect()[0]["VAL"] is None

    def test_target_equal_compare_passes(self, spark):
        rule = {"target_field": "APP_DATE", "compare_field": "ISSUE_DATE", "severity": "SEVERE"}
        df = spark.createDataFrame([("20200101", "20200101")], ["APP_DATE", "ISSUE_DATE"])
        result = df.withColumn("VAL", compile_date_lte(rule))
        assert result.collect()[0]["VAL"] is None

    def test_target_after_compare_fails(self, spark):
        rule = {"target_field": "APP_DATE", "compare_field": "ISSUE_DATE", "severity": "SEVERE"}
        df = spark.createDataFrame([("20210101", "20200101")], ["APP_DATE", "ISSUE_DATE"])
        result = df.withColumn("VAL", compile_date_lte(rule))
        val = result.collect()[0]["VAL"]
        assert val is not None
        assert "SEVERE:" in val


class TestRangeRuleCorrectnessProperty:
    """**Validates: Requirements 3** — Range Rule Correctness Property.

    Property: For any two valid dates, date_greater_than passes iff target > compare,
    and date_lte passes iff target <= compare.
    """

    @given(
        d1=st.dates(min_value=date(1900, 1, 1), max_value=date(2099, 12, 31)),
        d2=st.dates(min_value=date(1900, 1, 1), max_value=date(2099, 12, 31)),
    )
    @settings(max_examples=100, deadline=None)
    def test_date_greater_than_correct_for_any_dates(self, spark, d1, d2):
        """date_greater_than: passes iff target_date > compare_date."""
        target_str = d1.strftime("%Y%m%d")
        compare_str = d2.strftime("%Y%m%d")

        rule = {"target_field": "T", "compare_field": "C", "severity": "SEVERE"}
        df = spark.createDataFrame([(target_str, compare_str)], ["T", "C"])
        result = df.withColumn("VAL", compile_date_greater_than(rule)).collect()[0]["VAL"]

        if d1 > d2:
            assert result is None, f"{d1} > {d2} should pass"
        else:
            assert result is not None, f"{d1} <= {d2} should fail"

    @given(
        d1=st.dates(min_value=date(1900, 1, 1), max_value=date(2099, 12, 31)),
        d2=st.dates(min_value=date(1900, 1, 1), max_value=date(2099, 12, 31)),
    )
    @settings(max_examples=100, deadline=None)
    def test_date_lte_correct_for_any_dates(self, spark, d1, d2):
        """date_lte: passes iff target_date <= compare_date."""
        target_str = d1.strftime("%Y%m%d")
        compare_str = d2.strftime("%Y%m%d")

        rule = {"target_field": "T", "compare_field": "C", "severity": "SEVERE"}
        df = spark.createDataFrame([(target_str, compare_str)], ["T", "C"])
        result = df.withColumn("VAL", compile_date_lte(rule)).collect()[0]["VAL"]

        if d1 <= d2:
            assert result is None, f"{d1} <= {d2} should pass"
        else:
            assert result is not None, f"{d1} > {d2} should fail"
